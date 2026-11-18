"""Offline tests — no network, temp SQLite DB, Telegram API stubbed. Run: python3 tests/test_offline.py"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DB_PATH = os.path.join(tempfile.gettempdir(), f"miku-bot-test-{int(time.time()*1000)}.sqlite")
os.environ["DATABASE_PATH"] = DB_PATH
os.environ["PHOENIX_API_KEY"] = "phx_test"
os.environ["TELEGRAM_BOT_TOKEN"] = "test:token"
os.environ["ADMIN_PANEL_PASSWORD"] = "x"
os.environ["FAMPAY_SENDER_DOMAINS"] = "famapp.in"

import json  # noqa: E402

import db  # noqa: E402
import tg  # noqa: E402
from pricing import make_pricer  # noqa: E402
from gmail_poll import parse_email, process_alert  # noqa: E402
import payments as pay  # noqa: E402
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

# 7. WhatsApp order lifecycle (Phoenix stubbed)
import phoenix  # noqa: E402
import orders as omod  # noqa: E402

phoenix.wa_india = lambda fresh=False: {"count": 1540, "price": 0.1821}
phoenix.cancel_lock_seconds = lambda: 0  # allow immediate cancel in the test
_fake = {"codes": [], "status": "wa_pending"}
_refs = {"n": 0}


def _fake_buy():
    _refs["n"] += 1
    return {"order_ref": f"REF{_refs['n']:04d}", "phone": "919876543210", "price_usd": 0.1821, "expires_in_seconds": 1200, "status": "wa_pending"}


phoenix.wa_buy = _fake_buy
phoenix.wa_code = lambda ref: dict(_fake)
phoenix.wa_cancel = lambda ref: {"status": "refunded"}

wu = get_or_create_user({"id": 444, "first_name": "Wa"})[0]
# price = 0.1821*100*100 paise + ₹40 margin = ceil(1821)+... actually plus mode: cost*rate + 40
exp_price = __import__("math").ceil((0.1821 * 100 + 40) * 100)
with db.tx() as c:
    apply_balance(c, wu["id"], 30000, "admin", None, "load")
order = omod.buy_whatsapp(wu["id"])
assert order["status"] == "waiting" and order["phone"] == "919876543210", "WA buy -> waiting with number"
assert order["price_paise"] == exp_price, f"WA price = cost*rate + ₹40 ({order['price_paise']} vs {exp_price})"
assert bal(wu["id"]) == 30000 - exp_price, "wallet charged my price"
# no OTP yet
assert omod.check_order(omod.get_order(order["id"]), 0) is None
# OTP arrives
_fake["codes"] = ["123456"]
_fake["status"] = "delivered"
assert omod.check_order(omod.get_order(order["id"]), 0) == "code"
assert json.loads(omod.get_order(order["id"])["codes"])[-1] == "123456", "OTP stored"
omod.finish_order(omod.get_order(order["id"]))
assert omod.get_order(order["id"])["status"] == "completed"
ok("WhatsApp buy -> waiting -> OTP -> done")

# refund on timeout
_fake["codes"] = []
_fake["status"] = "wa_pending"
o2 = omod.buy_whatsapp(wu["id"])
db.execute("UPDATE orders SET expires_at = ? WHERE id = ?", (db.now() - 60_000, o2["id"]))
assert omod.check_order(omod.get_order(o2["id"]), 0) == "closed"
assert omod.get_order(o2["id"])["status"] == "cancelled", "timed-out order cancelled"
assert bal(wu["id"]) == 30000 - exp_price, "refunded on timeout"
ok("WhatsApp auto-refund on timeout")

# cancel + refund
_fake["status"] = "wa_pending"
o3 = omod.buy_whatsapp(wu["id"])
omod.cancel_order(omod.get_order(o3["id"]))
assert omod.get_order(o3["id"])["status"] == "cancelled"
assert bal(wu["id"]) == 30000 - exp_price, "refunded on cancel"
ok("WhatsApp cancel + refund")

# 10. Transaction ID claim — one-time use
from payments import claim_transaction_id, create_payment as _cp  # noqa: E402

cu = get_or_create_user({"id": 555, "first_name": "Claim"})[0]
p1 = _cp(cu["id"], 100)
db.execute(
    "INSERT INTO emails (message_id, from_addr, received_at, amount_paise, utr, dkim_ok, status, created_at) "
    "VALUES (?, 'no-reply@famapp.in', ?, ?, 'FMPIBCLAIM1', 1, 'unmatched', ?)",
    (f"em-{db.now()}", db.now(), p1["amount_paise"], db.now()),
)
paid = claim_transaction_id(cu["id"], p1["id"], "FMPIBCLAIM1")
assert paid and bal(cu["id"]) == p1["amount_paise"], "claim with matching trusted email credits"
try:
    p2 = _cp(cu["id"], 100)
    claim_transaction_id(cu["id"], p2["id"], "FMPIBCLAIM1")
    raise AssertionError("should reject reused Transaction ID")
except pay.PaymentError as e:
    assert "already used" in str(e).lower()
try:
    claim_transaction_id(cu["id"], p2["id"], "nope")
    raise AssertionError("should reject bad format")
except pay.PaymentError:
    pass
ok("Transaction ID claim credits once, rejects reuse + bad format")

# 11. Claim then email arrives later -> credited via claimed match
p3 = _cp(cu["id"], 100)
before3 = bal(cu["id"])
assert claim_transaction_id(cu["id"], p3["id"], "FMPIBLATER9") is None, "no email yet -> pending claim"
r3 = f"{p3['amount_paise']/100:.2f}".rstrip("0")
process_alert(parse_email(famapp("mlate", r3, "FMPIBLATER9")))
assert bal(cu["id"]) == before3 + p3["amount_paise"], "late email credits the claimed deposit"
ok("claimed Transaction ID credited when the email lands")

# 12. Premium emoji converter (bold + custom emoji with UTF-16 offsets)
import premium  # noqa: E402

premium._map = {"\U0001F525": "555"}  # 🔥 -> fake custom_emoji_id
txt, ents = premium.convert("\U0001F525 <b>OTP</b> &amp; go")
assert txt == "\U0001F525 OTP & go", f"plain text: {txt!r}"
ce = [e for e in ents if e["type"] == "custom_emoji"][0]
assert ce["offset"] == 0 and ce["length"] == 2 and ce["custom_emoji_id"] == "555"
bold = [e for e in ents if e["type"] == "bold"][0]
assert bold["offset"] == 3 and bold["length"] == 3, f"bold: {bold}"
premium._map = {}
ok("premium emoji converter (bold + custom emoji offsets)")

# 13. Stats totals + user stats
import stats  # noqa: E402

tot = stats.totals()
assert set(tot) == {"orders_total", "orders_done", "orders_cancel", "deducted_paise", "added_paise"}
assert tot["orders_done"] >= 1 and tot["orders_cancel"] >= 2, "WA lifecycle reflected in totals"
assert tot["added_paise"] > 0, "deposits counted"
us = stats.user_stats(wu["id"])
assert us["orders_done"] >= 1 and us["spent_paise"] > 0, "user spent on the completed order"
ok("stats totals + user profile numbers")

print(f"\nAll {passed} test groups passed")
for ext in ("", "-wal", "-shm"):
    try:
        os.remove(DB_PATH + ext)
    except OSError:
        pass
