"""SQLite layer. One connection shared across threads, guarded by a lock."""
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT,
  balance_paise INTEGER NOT NULL DEFAULT 0 CHECK (balance_paise >= 0),
  blocked INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  delta_paise INTEGER NOT NULL,
  balance_after INTEGER NOT NULL,
  kind TEXT NOT NULL,
  ref TEXT,
  note TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_user ON ledger(user_id, id);
CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  activation_id TEXT UNIQUE,
  phone TEXT,
  service TEXT NOT NULL,
  service_name TEXT NOT NULL,
  country TEXT NOT NULL,
  country_name TEXT NOT NULL,
  cost_usd REAL NOT NULL,
  price_paise INTEGER NOT NULL,
  status TEXT NOT NULL,
  codes TEXT NOT NULL DEFAULT '[]',
  error TEXT,
  chat_id INTEGER,
  message_id INTEGER,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  checked_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id, id);
CREATE INDEX IF NOT EXISTS orders_status ON orders(status);
CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  amount_paise INTEGER NOT NULL,
  status TEXT NOT NULL,
  utr TEXT UNIQUE,
  chat_id INTEGER,
  message_id INTEGER,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  paid_at INTEGER
);
CREATE INDEX IF NOT EXISTS payments_user ON payments(user_id, id);
CREATE INDEX IF NOT EXISTS payments_status ON payments(status);
CREATE TABLE IF NOT EXISTS emails (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL UNIQUE,
  from_addr TEXT,
  subject TEXT,
  received_at INTEGER,
  amount_paise INTEGER,
  utr TEXT,
  dkim_ok INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  reason TEXT,
  payment_id INTEGER,
  snippet TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '*',
  mode TEXT NOT NULL,
  value REAL NOT NULL DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0,
  UNIQUE (service, country)
);
"""

DEFAULT_SETTINGS: dict[str, str] = {
    "usd_inr_rate": "100",
    "global_markup_pct": "0",
    "min_topup_inr": "10",
    "max_topup_inr": "5000",
    "payment_window_min": "10",
    "order_timeout_min": "20",
    "upi_id": "Poonambhai@fam",
    "upi_name": "Miku OTP",
    "welcome_text": "",
}

_conn: Optional[sqlite3.Connection] = None
_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    path = os.path.abspath(config.DATABASE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.executescript(_SCHEMA)
    return conn


def init() -> None:
    global _conn
    if _conn is None:
        _conn = _connect()
        _migrate(_conn)
        _seed()


def _migrate(d: sqlite3.Connection) -> None:
    cols = [r["name"] for r in d.execute("PRAGMA table_info(payments)").fetchall()]
    if "claimed_utr" not in cols:
        d.execute("ALTER TABLE payments ADD COLUMN claimed_utr TEXT")
        d.commit()


def conn() -> sqlite3.Connection:
    if _conn is None:
        init()
    assert _conn is not None
    return _conn


def now() -> int:
    return int(time.time() * 1000)


# ---------- query helpers (all acquire the lock) ----------

def q(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchall()


def one(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    with _lock:
        return conn().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        return cur


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Hold the lock for a whole transaction. Use the yielded connection for all writes."""
    with _lock:
        c = conn()
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


# ---------- settings ----------

def get_setting(key: str) -> str:
    row = one("SELECT value FROM settings WHERE key = ?", (key,))
    if row is not None:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, "")


def get_setting_number(key: str) -> float:
    try:
        return float(get_setting(key))
    except (TypeError, ValueError):
        return float(DEFAULT_SETTINGS.get(key, "0"))


def get_settings() -> dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    for row in q("SELECT key, value FROM settings"):
        if not row["key"].startswith("_"):
            out[row["key"]] = row["value"]
    return out


def set_setting(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def get_state(key: str) -> Optional[str]:
    row = one("SELECT value FROM settings WHERE key = ?", ("_" + key,))
    return row["value"] if row else None


def set_state(key: str, value: Any) -> None:
    set_setting("_" + key, value)


def _seed() -> None:
    """One-time defaults: the ₹40 WhatsApp margin the owner asked for (admin can change/delete)."""
    if get_state("seeded_v1") == "1":
        return
    execute(
        "INSERT INTO price_rules (service, country, mode, value, hidden) VALUES ('wa', '*', 'plus', 40, 0) "
        "ON CONFLICT(service, country) DO NOTHING"
    )
    set_state("seeded_v1", "1")
