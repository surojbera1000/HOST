"""Buying WhatsApp numbers (Phoenix, India), polling for OTP, cancel + refund."""
import json
from typing import Optional

import catalog
import db
import phoenix
from pricing import make_pricer
from wallet import apply_balance

WA_SERVICE = "wa"
INDIA_ID = phoenix.INDIA_ID


class OrderError(Exception):
    pass


def get_order(oid: int) -> Optional[dict]:
    row = db.one("SELECT * FROM orders WHERE id = ?", (oid,))
    return dict(row) if row else None


def codes_of(o: dict) -> list:
    return json.loads(o["codes"])


def order_belongs_to(o: dict, user_id: int) -> bool:
    return o["user_id"] == user_id


def set_order_message(oid: int, chat_id: int, message_id: int) -> None:
    db.execute("UPDATE orders SET chat_id = ?, message_id = ? WHERE id = ?", (chat_id, message_id, oid))


def cancel_after_ms() -> int:
    return phoenix.cancel_lock_seconds() * 1000


def refund_order(order_id: int, status: str, error: Optional[str]) -> None:
    with db.tx() as c:
        cur = c.execute(
            "UPDATE orders SET status = ?, error = ?, updated_at = ? WHERE id = ? AND status IN ('buying', 'waiting', 'received')",
            (status, error, db.now(), order_id),
        )
        if cur.rowcount != 1:
            return
        o = dict(c.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone())
        apply_balance(c, o["user_id"], o["price_paise"], "refund", f"order:{o['id']}", f"Refund: {o['service_name']}")


def _pending_exists() -> bool:
    """Phoenix allows only one pending WhatsApp order per API key at a time."""
    row = db.one("SELECT COUNT(*) n FROM orders WHERE service = ? AND status IN ('buying', 'waiting')", (WA_SERVICE,))
    return row["n"] > 0


def buy_whatsapp(user_id: int) -> dict:
    opt = catalog.india_option(fresh=True)
    if not opt:
        raise OrderError("No WhatsApp numbers available right now. Try again shortly.")
    price_paise = opt["price_paise"]
    if _pending_exists():
        raise OrderError("A WhatsApp order is being processed right now. Please try again in a minute.")

    t = db.now()
    # 1) Reserve the money + create the order.
    with db.tx() as c:
        cur = c.execute(
            "INSERT INTO orders (user_id, service, service_name, country, country_name, cost_usd, price_paise, "
            "status, created_at, expires_at, updated_at) VALUES (?, 'wa', 'WhatsApp', ?, 'India', ?, ?, 'buying', ?, ?, ?)",
            (user_id, INDIA_ID, opt["cost_usd"], price_paise, t, t + 1200_000, t),
        )
        order_id = cur.lastrowid
        if not apply_balance(c, user_id, -price_paise, "order", f"order:{order_id}", "WhatsApp number (India)"):
            raise OrderError("Not enough balance. Please add money first.")

    # 2) Buy from Phoenix.
    try:
        res = phoenix.wa_buy()
    except phoenix.PhoenixError as e:
        print("[order] wa_buy failed", order_id, e.code)
        refund_order(order_id, "failed", e.code)
        raise OrderError(phoenix.friendly_error(e.code))
    except Exception as e:  # noqa: BLE001
        print("[order] wa_buy error", order_id, e)
        refund_order(order_id, "failed", "ERROR")
        raise OrderError("Could not get a number. You were refunded. Try again.")

    t2 = db.now()
    db.execute(
        "UPDATE orders SET activation_id = ?, phone = ?, status = 'waiting', created_at = ?, expires_at = ?, "
        "updated_at = ? WHERE id = ?",
        (res["order_ref"], res["phone"], t2, t2 + res["expires_in_seconds"] * 1000, t2, order_id),
    )
    return get_order(order_id)


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


def cancel_order(o: dict) -> dict:
    if o["status"] != "waiting":
        raise OrderError("This order can't be cancelled.")
    if db.now() < o["created_at"] + cancel_after_ms():
        raise OrderError("You can cancel a couple of minutes after purchase. Please wait a little.")
    try:
        phoenix.wa_cancel(o["activation_id"])
    except phoenix.PhoenixError as e:
        if e.code not in ("not_found",):
            raise OrderError(phoenix.friendly_error(e.code))
    refund_order(o["id"], "cancelled", None)
    return get_order(o["id"])


def finish_order(o: dict) -> None:
    db.execute("UPDATE orders SET status = 'completed', updated_at = ? WHERE id = ? AND status = 'received'", (db.now(), o["id"]))


def check_order(o: dict, min_gap_ms: int) -> Optional[str]:
    """Poll Phoenix for the OTP. Returns 'code', 'closed', or None."""
    t = db.now()
    claim = db.execute("UPDATE orders SET checked_at = ? WHERE id = ? AND checked_at <= ?", (t, o["id"], t - min_gap_ms))
    if claim.rowcount != 1:
        return None
    try:
        res = phoenix.wa_code(o["activation_id"])
    except phoenix.PhoenixError:
        return None
    if res["codes"]:
        if add_code(o, res["codes"][-1]):
            return "code"
        return None
    if res["status"] == "refunded":
        refund_order(o["id"], "cancelled", "No OTP received — refunded")
        return "closed"
    fresh = get_order(o["id"])
    if fresh["status"] == "waiting" and db.now() > fresh["expires_at"] + 30_000:
        refund_order(o["id"], "cancelled", "No OTP received in time")
        return "closed"
    return None


def active_orders() -> list:
    return [dict(r) for r in db.q("SELECT * FROM orders WHERE status IN ('waiting', 'received') ORDER BY id LIMIT 300")]
