"""Offline tests — no network, temp SQLite DB, Telegram API stubbed. Run: python3 tests/test_offline.py"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB_PATH = os.path.join(tempfile.gettempdir(), f"miku-bot-test-{int(time.time()*1000)}.sqlite")
os.environ["DATABASE_PATH"] = DB_PATH
os.environ["GRIZZLY_API_KEY"] = "test"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
os.environ["ADMIN_PANEL_PASSWORD"] = "x"
os.environ["FAMPAY_SENDER_DOMAINS"] = "famapp.in"

import db  # noqa: E402
import tg  # noqa: E402
from pricing import make_pricer  # noqa: E402
from gmail_poll import parse_email, process_alert  # noqa: E402
from payments import create_payment  # noqa: E402
from users import get_or_create_user  # noqa: E402
from wallet import apply_balance  # noqa: E402

db.init()

passed = 0


def ok(name):
    global passed
    passed += 1
    print("  ok:", name)


# 1. Default ₹40 WhatsApp margin
price = make_pricer()
assert db.get_setting_number("usd_inr_rate") == 100
assert price("wa", "22", 0.5)[0] == 9000, "WhatsApp $0.50 -> ₹90 (₹50 cost + ₹40)"
assert price("wa", "6", 0.092)[0] == __import__("math").ceil((9.2 + 40) * 100), "WhatsApp $0.092 -> ₹49.20"
assert price("tg", "6", 0.09)[0] == 900, "Telegram $0.09 -> ₹9 (no margin)"
ok("default ₹40 WhatsApp margin, Telegram unchanged")

# 2. Admin can change the margin
db.execute("UPDATE price_rules SET value = 25 WHERE service='wa' AND country='*'")
assert make_pricer()("wa", "22", 0.5)[0] == 7500, "margin ₹25 -> ₹75"
db.execute("UPDATE price_rules SET value = 40 WHERE service='wa' AND country='*'")
ok("admin can change the WhatsApp margin")


def famapp(mid, amount, txn, frm="no-reply@famapp.in", auth=None):
    if auth is None:
        auth = ("Authentication-Results: mx.google.com;\r\n       dkim=pass header.i=@famapp.in header.s=s1;\r\n"
                f"       spf=pass smtp.mailfrom={frm}")
    html = (f"<html><body><p>Hey Poonam,</p><p>You have successfully received</p><h1>&#8377;{amount}</h1>"
            f"<p>from RAJ</p><p>Transaction ID :</p><p>{txn}</p></body></html>")
    raw = "\r\n".join([
        auth,
        f"From: FamApp <{frm}>",
        "To: me@gmail.com",
        f"Message-ID: <{mid}@famapp.in>",
        "Subject: You received money",
        time.strftime("Date: %a, %d %b %Y %H:%M:%S +0000", time.gmtime()),
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        html,
    ])
    return raw.encode()


def bal(uid):
    return db.one("SELECT balance_paise b FROM users WHERE id=?", (uid,))["b"]


# 3. Automatic deposit matching
u = get_or_create_user({"id": 111, "username": "alice", "first_name": "Alice"})[0]
pay1 = create_payment(u["id"], 100)
rupees = f"{pay1['amount_paise']/100:.2f}".rstrip("0")
assert process_alert(parse_email(famapp("m1", rupees, "FMPIB0001"))), "matching email credits deposit"
assert bal(u["id"]) == pay1["amount_paise"], "wallet credited exact amount"
process_alert(parse_email(famapp("m1", rupees, "FMPIB0001")))  # duplicate email
pay2 = create_payment(u["id"], 100)
r2 = f"{pay2['amount_paise']/100:.2f}".rstrip("0")
process_alert(parse_email(famapp("m2", r2, "FMPIB0001")))  # reused txn id
assert bal(u["id"]) == pay1["amount_paise"], "transaction ID cannot be reused"
process_alert(parse_email(famapp("m3", r2, "FMPIB9", frm="x@evil.com", auth="X-Fake: 1")))  # spoof
assert bal(u["id"]) == pay1["amount_paise"], "spoofed email ignored"
process_alert(parse_email(famapp("m4", "77.00", "FMPIB0004")))  # wrong amount
assert bal(u["id"]) == pay1["amount_paise"], "unknown amount left for admin"
ok("automatic deposit matching (credit once, no reuse, spoof/wrong-amount rejected)")

# 4. Unique deposit amounts
u2 = get_or_create_user({"id": 222})[0]
seen = set()
for _ in range(3):
    p = create_payment(u2["id"], 100)
    assert p["amount_paise"] not in seen, "each open ₹100 deposit gets a unique amount"
    seen.add(p["amount_paise"])
ok("concurrent same-amount deposits get unique amounts")

# 5. Wallet never negative
u3 = get_or_create_user({"id": 333})[0]
with db.tx() as c:
    assert apply_balance(c, u3["id"], 5000, "admin", None, "t") is True
with db.tx() as c:
    assert apply_balance(c, u3["id"], -9000, "order", None, "t") is False
assert bal(u3["id"]) == 5000, "balance unchanged after refused debit"
ok("wallet cannot go negative")

# 6. Bot /start shows coloured menu (stub tg.send_message)
sent = []
tg.send_message = lambda chat_id, text, keyboard=None: (sent.append({"text": text, "kb": keyboard}) or {"message_id": 1, "chat": {"id": chat_id}})
import handlers  # noqa: E402

handlers.handle_update({"update_id": 1, "message": {"message_id": 1, "chat": {"id": 999}, "from": {"id": 999, "first_name": "Bob"}, "text": "/start"}})
assert sent, "sent a message on /start"
assert "Welcome to Miku OTP" in sent[-1]["text"]
blob = str(sent[-1]["kb"])
assert "primary" in blob and "success" in blob, "coloured buttons present"
assert "buy" in blob and "dep" in blob, "buy + deposit buttons present"
ok("bot /start shows coloured menu")

print(f"\nAll {passed} test groups passed")
for ext in ("", "-wal", "-shm"):
    try:
        os.remove(DB_PATH + ext)
    except OSError:
        pass
