"""Buying numbers, polling for OTP, cancel + refund."""
import json
from typing import Optional

import db
import grizzly
from pricing import make_pricer
from wallet import apply_balance

CANCEL_AFTER_MS = 5 * 60_000  # GrizzlySMS refuses cancellation before this


class OrderError(Exception):
    pass


def get_order(oid: int) -> Optional[dict]:
    row = db.one("SELECT * FROM orders WHERE id = ?", (oid,))
    return dict(row) if row else None


def codes_of(o: dict) -> list[str]:
    return json.loads(o["codes"])


def order_belongs_to(o: dict, user_id: int) -> bool:
    return o["user_id"] == user_id


def set_order_message(oid: int, chat_id: int, message_id: int) -> None:
    db.execute("UPDATE orders SET chat_id = ?, message_id = ? WHERE id = ?", (chat_id, message_id, oid))


def refund_order(order_id: int, status: str, error: Optional[str]) -> None:
    """Cancel locally and refund once."""
    with db.tx() as c:
        cur = c.execute(
            "UPDATE orders SET status = ?, error = ?, updated_at = ? WHERE id = ? AND status IN ('buying', 'waiting')",
            (status, error, db.now(), order_id),
        )
        if cur.rowcount != 1:
            return
        o = dict(c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
        apply_balance(c, o["user_id"], o["price_paise"], "refund", f"order:{o['id']}", f"Refund: {o['service_name']}")


def buy_number(user_id: int, service: str, country: str) -> dict:
    services = grizzly.get_services()
    countries = grizzly.get_countries()
    prices = grizzly.get_service_prices(service, fresh=True)
    svc = next((s for s in services if s["code"] == service), None)
    entry = next((p for p in prices if p["country"] == country), None)
    if not svc or not entry or country not in countries:
        raise OrderError("This service is not available.")
    if entry["count"] <= 0:
        raise OrderError("No numbers available right now. Try another country.")

    price_paise, hidden = make_pricer()(service, country, entry["cost_usd"])
    if hidden:
        raise OrderError("This service is not available.")

    t = db.now()
    timeout = int(db.get_setting_number("order_timeout_min") * 60_000)

    # 1) Reserve money + create order atomically.
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO orders (user_id, service, service_name, country, country_name, cost_usd, price_paise, "
            "status, created_at, expires_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'buying', ?, ?, ?)",
            (user_id, service, svc["name"], country, countries[country], entry["cost_usd"], price_paise, t, t + timeout, t),
        )
        order_id = cur.lastrowid
        if not apply_balance(c, user_id, -price_paise, "order", f"order:{order_id}", f"Number: {svc['name']}"):
            raise OrderError("Not enough balance. Please add money first.")

    # 2) Buy from GrizzlySMS, never over the priced cost.
    try:
        activation_id, phone = grizzly.get_number(service, country, entry["cost_usd"])
        t2 = db.now()
        db.execute(
            "UPDATE orders SET activation_id = ?, phone = ?, status = 'waiting', created_at = ?, expires_at = ?, "
            "updated_at = ? WHERE id = ?",
            (activation_id, phone, t2, t2 + timeout, t2, order_id),
        )
        return get_order(order_id)
    except grizzly.GrizzlyError as e:
        print("[order] getNumber failed", order_id, e.code)
        refund_order(order_id, "failed", e.code)
        raise OrderError(grizzly.friendly_error(e.code))
    except Exception as e:  # noqa: BLE001
        print("[order] getNumber error", order_id, e)
        refund_order(order_id, "failed", "NETWORK_ERROR")
        raise OrderError("Could not get a number. You were refunded. Try again.")


def add_code(o: dict, code: str) -> bool:
    codes = codes_of(o)
    if codes and codes[-1] == code:
        return False
    codes.append(code)
    cur = db.execute(
        "UPDATE orders SET codes = ?, status = 'received', updated_at = ? WHERE id = ? AND codes = ? "
        "AND status IN ('waiting', 'received')",
        (json.dumps(codes), db.now(), o["id"], o["codes"]),
    )
    return cur.rowcount == 1


def _cancelled(res: str) -> bool:
    return res in ("ACCESS_CANCEL", "NO_ACTIVATION", "STATUS_CANCEL")


def cancel_order(o: dict) -> dict:
    if o["status"] != "waiting":
        raise OrderError("This order can't be cancelled.")
    if db.now() < o["created_at"] + CANCEL_AFTER_MS:
        raise OrderError("You can cancel about 5 minutes after purchase. Please wait a little.")
    res = grizzly.set_status(o["activation_id"], 8)
    if _cancelled(res):
        refund_order(o["id"], "cancelled", None)
        return get_order(o["id"])
    try:
        st = grizzly.get_status(o["activation_id"])
        if st["state"] == "code":
            add_code(o, st["code"])
    except grizzly.GrizzlyError:
        pass
    raise OrderError(grizzly.friendly_error(res))


def request_another_sms(o: dict) -> None:
    if o["status"] != "received":
        raise OrderError("No OTP received yet.")
    res = grizzly.set_status(o["activation_id"], 3)
    if not res.startswith("ACCESS_RETRY_GET") and not res.startswith("ACCESS_READY"):
        raise OrderError(grizzly.friendly_error(res))


def finish_order(o: dict) -> None:
    try:
        grizzly.set_status(o["activation_id"], 6)
    except grizzly.GrizzlyError as e:
        print("[order] finish", e.code)
    db.execute("UPDATE orders SET status = 'completed', updated_at = ? WHERE id = ? AND status = 'received'", (db.now(), o["id"]))


def check_order(o: dict, min_gap_ms: int) -> Optional[str]:
    """Returns 'code', 'closed', or None. min_gap_ms avoids double API hits."""
    t = db.now()
    claim = db.execute("UPDATE orders SET checked_at = ? WHERE id = ? AND checked_at < ?", (t, o["id"], t - min_gap_ms))
    if claim.rowcount != 1:
        return None
    st = grizzly.get_status(o["activation_id"])
    got = st["state"] == "code" and add_code(o, st["code"])
    fresh = get_order(o["id"])
    if st["state"] == "cancelled" and fresh["status"] == "waiting":
        refund_order(o["id"], "cancelled", "Cancelled by provider")
        return "closed"
    if got:
        return "code"
    if db.now() < fresh["expires_at"]:
        return None
    if fresh["status"] == "received":
        finish_order(fresh)
        return "closed"
    if fresh["status"] == "waiting":
        try:
            res = grizzly.set_status(o["activation_id"], 8)
        except grizzly.GrizzlyError:
            res = "ERROR"
        if _cancelled(res) or db.now() > fresh["expires_at"] + 10 * 60_000:
            refund_order(o["id"], "cancelled", "No OTP received in time")
            return "closed"
    return None


def active_orders() -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM orders WHERE status IN ('waiting', 'received') ORDER BY id LIMIT 300")]
