"""Deposits: unique-amount UPI requests, auto-credited when the matching email arrives."""
import io
import secrets
from typing import Optional

import qrcode

import db
from wallet import apply_balance


class PaymentError(Exception):
    pass


def upi_link(amount_paise: int) -> str:
    return (
        f"upi://pay?pa={db.get_setting('upi_id')}"
        f"&pn={db.get_setting('upi_name').replace(' ', '%20')}"
        f"&am={amount_paise / 100:.2f}&cu=INR"
    )


def qr_png(amount_paise: int) -> bytes:
    img = qrcode.make(upi_link(amount_paise))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def expire_old_payments() -> None:
    db.execute("UPDATE payments SET status = 'expired' WHERE status = 'pending' AND expires_at < ?", (db.now(),))


def _unique_amount_paise(base_rupees: int) -> int:
    """Each open deposit gets rupees + random paise so the exact amount identifies it."""
    base = base_rupees * 100
    since = db.now() - 60 * 60_000
    used = {
        r["amount_paise"]
        for r in db.q(
            "SELECT amount_paise FROM payments WHERE amount_paise BETWEEN ? AND ? "
            "AND (status = 'pending' OR created_at >= ?)",
            (base, base + 99, since),
        )
    }
    free = [base + p for p in range(1, 100) if base + p not in used]
    if not free:
        raise PaymentError("Too many deposits of this amount right now. Try a slightly different amount.")
    return free[secrets.randbelow(len(free))]


def create_payment(user_id: int, amount_rupees: int) -> dict:
    mn = int(db.get_setting_number("min_topup_inr"))
    mx = int(db.get_setting_number("max_topup_inr"))
    if not isinstance(amount_rupees, int) or amount_rupees < mn or amount_rupees > mx:
        raise PaymentError(f"Enter a whole amount between \u20b9{mn} and \u20b9{mx}.")
    expire_old_payments()
    open_n = db.one("SELECT COUNT(*) n FROM payments WHERE user_id = ? AND status = 'pending'", (user_id,))["n"]
    if open_n >= 3:
        raise PaymentError("You already have open deposits. Finish or cancel them first.")
    amount_paise = _unique_amount_paise(amount_rupees)
    t = db.now()
    window = int(db.get_setting_number("payment_window_min") * 60_000)
    cur = db.execute(
        "INSERT INTO payments (user_id, amount_paise, status, created_at, expires_at) VALUES (?, ?, 'pending', ?, ?)",
        (user_id, amount_paise, t, t + window),
    )
    return dict(db.one("SELECT * FROM payments WHERE id = ?", (cur.lastrowid,)))


def get_payment(pid: int) -> Optional[dict]:
    row = db.one("SELECT * FROM payments WHERE id = ?", (pid,))
    return dict(row) if row else None


def cancel_payment(pid: int) -> None:
    db.execute("UPDATE payments SET status = 'cancelled' WHERE id = ? AND status = 'pending'", (pid,))


def set_payment_message(pid: int, chat_id: int, message_id: int) -> None:
    db.execute("UPDATE payments SET chat_id = ?, message_id = ? WHERE id = ?", (chat_id, message_id, pid))


def credit_payment(payment_id: int, utr: Optional[str], email_id: Optional[int]) -> Optional[dict]:
    """Mark paid + credit wallet exactly once. Returns paid row, or None if already paid / UTR reused."""
    with db.tx() as c:
        if utr:
            if c.execute("SELECT id FROM payments WHERE utr = ?", (utr,)).fetchone():
                return None
        cur = c.execute(
            "UPDATE payments SET status = 'paid', utr = ?, paid_at = ? "
            "WHERE id = ? AND status IN ('pending', 'expired', 'cancelled')",
            (utr, db.now(), payment_id),
        )
        if cur.rowcount != 1:
            return None
        p = dict(c.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)).fetchone())
        apply_balance(c, p["user_id"], p["amount_paise"], "topup", f"payment:{p['id']}", f"UPI {utr or 'deposit'}")
        if email_id:
            c.execute("UPDATE emails SET status = 'matched', reason = NULL, payment_id = ? WHERE id = ?", (p["id"], email_id))
        return p
