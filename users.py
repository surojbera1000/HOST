"""Telegram user → account mapping."""
from typing import Optional

import config
import db


def get_or_create_user(frm: dict) -> tuple[dict, bool]:
    """Returns (user, is_new)."""
    tid = frm["id"]
    row = db.one("SELECT * FROM users WHERE telegram_id = ?", (tid,))
    if row:
        u = dict(row)
        if u.get("username") != frm.get("username") or u.get("first_name") != frm.get("first_name"):
            db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE id = ?",
                (frm.get("username"), frm.get("first_name"), u["id"]),
            )
            u["username"] = frm.get("username")
            u["first_name"] = frm.get("first_name")
        return u, False
    cur = db.execute(
        "INSERT INTO users (telegram_id, username, first_name, created_at) VALUES (?, ?, ?, ?)",
        (tid, frm.get("username"), frm.get("first_name"), db.now()),
    )
    return dict(db.one("SELECT * FROM users WHERE id = ?", (cur.lastrowid,))), True


def user_by_telegram_id(tid: int) -> Optional[dict]:
    row = db.one("SELECT * FROM users WHERE telegram_id = ?", (tid,))
    return dict(row) if row else None


def is_admin(tid: int) -> bool:
    return tid in config.ADMIN_TELEGRAM_IDS
