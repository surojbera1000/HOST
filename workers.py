"""Background threads: OTP polling, deposit expiry, Gmail auto-deposit."""
import json
import threading
import time

import config
import db
from format_utils import inr
from gmail_poll import poll_gmail
from notify import notify_admins
from orders import active_orders, check_order, get_order
from payments import expire_old_payments
from render import deposit_caption, deposit_keyboard, order_view
import tg


def _every(name: str, seconds: float, job) -> None:
    def loop():
        while True:
            try:
                job()
            except Exception as e:  # noqa: BLE001
                print(f"[worker:{name}]", e)
            time.sleep(seconds)

    threading.Thread(target=loop, name=name, daemon=True).start()


def _render_order(o: dict) -> None:
    if not o.get("chat_id") or not o.get("message_id"):
        return
    t, k = order_view(o, db.now())
    try:
        tg.edit_message(o["chat_id"], o["message_id"], t, k)
    except Exception as e:  # noqa: BLE001
        print("[worker] render order", o["id"], e)


def _orders_job() -> None:
    for o in active_orders():
        try:
            result = check_order(o, 20_000)
            if result in ("code", "closed"):
                fresh = get_order(o["id"])
                _render_order(fresh)
                if result == "code" and fresh.get("chat_id"):
                    codes = json.loads(fresh["codes"])
                    if codes:
                        try:
                            tg.send_message(fresh["chat_id"], f"\U0001F525 <b>OTP received:</b> <code>{codes[-1]}</code>")
                        except Exception:  # noqa: BLE001
                            pass
        except Exception as e:  # noqa: BLE001
            print("[worker:orders]", o["id"], e)


def _deposits_job() -> None:
    expiring = db.q("SELECT * FROM payments WHERE status = 'pending' AND expires_at < ? AND message_id IS NOT NULL", (db.now(),))
    expire_old_payments()
    for row in expiring:
        p = dict(db.one("SELECT * FROM payments WHERE id = ?", (row["id"],)))
        if p["status"] != "paid" and p.get("chat_id") and p.get("message_id"):
            try:
                tg.edit_caption(p["chat_id"], p["message_id"], deposit_caption(p, db.now()), deposit_keyboard(p))
            except Exception:  # noqa: BLE001
                pass


def _gmail_job() -> None:
    for paid in poll_gmail():
        p = dict(db.one("SELECT * FROM payments WHERE id = ?", (paid["id"],)))
        if p.get("chat_id") and p.get("message_id"):
            try:
                tg.edit_caption(p["chat_id"], p["message_id"], deposit_caption(p, db.now()), deposit_keyboard(p))
                tg.send_message(p["chat_id"], f"\u2705 <b>{inr(p['amount_paise'])} added to your wallet.</b>")
            except Exception:  # noqa: BLE001
                pass
        notify_admins(f"\U0001F4B0 Deposit credited: {inr(p['amount_paise'])} (payment #{p['id']})")
    db.set_state("gmail_last_run", str(db.now()))


def start_workers() -> None:
    _every("orders", 10, _orders_job)
    _every("deposits", 60, _deposits_job)
    if config.gmail_configured():
        _every("gmail", config.GMAIL_POLL_SECONDS, _gmail_job)
    else:
        print("[workers] GMAIL_USER / GMAIL_APP_PASSWORD not set — automatic deposits are OFF")
    print("[workers] started")
