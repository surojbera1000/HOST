"""Wallet balance changes with a ledger. Call inside db.tx() when combined with other writes."""
import sqlite3
from typing import Optional

import db


def apply_balance(
    conn: sqlite3.Connection,
    user_id: int,
    delta_paise: int,
    kind: str,
    ref: Optional[str],
    note: Optional[str] = None,
) -> bool:
    """Atomically change balance + write ledger. Returns False (no change) if a debit would go negative."""
    if not isinstance(delta_paise, int):
        raise ValueError("delta_paise must be int")
    cur = conn.execute(
        "UPDATE users SET balance_paise = balance_paise + ? WHERE id = ? AND balance_paise + ? >= 0",
        (delta_paise, user_id, delta_paise),
    )
    if cur.rowcount != 1:
        return False
    bal = conn.execute("SELECT balance_paise FROM users WHERE id = ?", (user_id,)).fetchone()["balance_paise"]
    conn.execute(
        "INSERT INTO ledger (user_id, delta_paise, balance_after, kind, ref, note, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, delta_paise, bal, kind, ref, note, db.now()),
    )
    return True


def balance_of(user_id: int) -> int:
    row = db.one("SELECT balance_paise FROM users WHERE id = ?", (user_id,))
    return row["balance_paise"] if row else 0
