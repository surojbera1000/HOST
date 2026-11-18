"""Telegram update handling: menu, WhatsApp buy flow, deposits, orders."""
import json
import threading
import time

import catalog
import db
import orders as orders_mod
import payments as pay
import phoenix
import tg
import users
from format_utils import esc, inr
from notify import notify_admins
from render import deposit_caption, deposit_keyboard, main_menu, order_view

# Per-user session for free-text input (custom deposit amount).
_sessions: dict[int, tuple[str, float]] = {}
_slock = threading.Lock()


def _set_session(tid: int, mode: str) -> None:
    with _slock:
        _sessions[tid] = (mode, time.time())


def _take_session(tid: int):
    with _slock:
        s = _sessions.pop(tid, None)
    if not s or time.time() - s[1] > 300:
        return None
    return s[0]


def handle_update(u: dict) -> None:
    try:
        if "message" in u:
            _on_message(u["message"])
        elif "callback_query" in u:
            _on_callback(u["callback_query"])
    except Exception as e:  # noqa: BLE001
        print("[bot] update error", e)


# ---------- messages ----------

def _on_message(msg: dict) -> None:
    frm = msg.get("from")
    text = (msg.get("text") or "").strip()
    if not frm or not text:
        return
    chat_id = msg["chat"]["id"]
    user, is_new = users.get_or_create_user(frm)
    if is_new:
        uname = ("@" + frm["username"]) if frm.get("username") else ""
        notify_admins(f"\U0001F195 New bot user: {esc(frm.get('first_name', ''))} {esc(uname)} (id {frm['id']})")

    if text.startswith("/start"):
        _sessions.pop(frm["id"], None)
        t, k = main_menu(user, users.is_admin(frm["id"]))
        tg.send_message(chat_id, t, k)
        return
    if text == "/balance":
        tg.send_message(chat_id, f"\U0001F4B0 Your balance: <b>{inr(user['balance_paise'])}</b>")
        return
    if text == "/admin" and users.is_admin(frm["id"]):
        _send_admin_stats(chat_id)
        return

    sess = _take_session(frm["id"])
    if sess == "amount":
        digits = "".join(c for c in text if c.isdigit())
        _start_deposit(user, chat_id, int(digits) if digits else 0)
        return
    if sess and sess.startswith("utr:"):
        _submit_transaction_id(user, chat_id, int(sess.split(":")[1]), text)
        return

    t, k = main_menu(user, users.is_admin(frm["id"]))
    tg.send_message(chat_id, t, k)


# ---------- callbacks ----------

def _on_callback(cq: dict) -> None:
    data = cq.get("data") or ""
    msg = cq.get("message")
    frm = cq["from"]
    user, _ = users.get_or_create_user(frm)
    if not msg:
        tg.answer_callback(cq["id"])
        return
    chat_id = msg["chat"]["id"]
    message_id = msg["message_id"]

    if user["blocked"]:
        tg.answer_callback(cq["id"], "Your account is blocked. Contact support.", True)
        return

    def ack(text=None, alert=False):
        tg.answer_callback(cq["id"], text, alert)

    def edit(text, keyboard=None):
        tg.edit_message(chat_id, message_id, text, keyboard)

    parts = data.split(":")
    cmd = parts[0]
    args = parts[1:]
    try:
        if cmd == "noop":
            ack()
        elif cmd in ("mm", "bal"):
            fresh = users.user_by_telegram_id(frm["id"])
            t, k = main_menu(fresh, users.is_admin(frm["id"]))
            edit(t, k)
            ack()
        elif cmd == "adm":
            if not users.is_admin(frm["id"]):
                ack("Admin only.", True)
            else:
                _admin(edit, ack, args)
        elif cmd == "dpid":
            _set_session(frm["id"], f"utr:{args[0]}")
            tg.send_message(chat_id, "\U0001F9FE Send me the <b>Transaction ID</b> from your payment app "
                            "(for example <code>FMPIB6903479891</code> or a 12-digit UTR).")
            ack()
        elif cmd == "buy":
            _show_wa_confirm(edit, user)
            ack()
        elif cmd == "bx":
            ack("Getting your number\u2026")
            _do_buy(frm, chat_id, message_id)
        elif cmd == "dep":
            _show_deposit_menu(edit)
            ack()
        elif cmd == "da":
            ack("Creating your QR\u2026")
            _start_deposit(user, chat_id, int(args[0]))
        elif cmd == "dc":
            _set_session(frm["id"], "amount")
            edit("\U0001F4B0 <b>Add money</b>\n\nSend the amount in \u20b9 (whole number), for example <b>100</b>.")
            ack()
        elif cmd == "dcl":
            p = pay.get_payment(int(args[0]))
            if p and p["user_id"] == user["id"]:
                pay.cancel_payment(p["id"])
                p = pay.get_payment(p["id"])
                tg.edit_caption(chat_id, message_id, "\U0001F6AB Deposit cancelled.", deposit_keyboard(p))
            ack("Cancelled")
        elif cmd == "ords":
            _show_orders(edit, user)
            ack()
        elif cmd == "op":
            _open_order(chat_id, message_id, user, int(args[0]))
            ack()
        elif cmd == "chk":
            _check_now(chat_id, message_id, user, int(args[0]), ack)
        elif cmd == "ccl":
            _do_cancel(chat_id, message_id, user, int(args[0]), ack)
        elif cmd == "don":
            _do_done(chat_id, message_id, user, int(args[0]), ack)
        else:
            ack()
    except (orders_mod.OrderError, pay.PaymentError) as e:
        ack(str(e), True)
    except Exception as e:  # noqa: BLE001
        print("[bot] callback error", data, e)
        ack("Something went wrong. Try again.", True)


# ---------- WhatsApp buy flow ----------

def _show_wa_confirm(edit, user) -> None:
    try:
        opt = catalog.india_option()
    except Exception:  # noqa: BLE001
        edit("Could not load the price. Please try again.", tg.kb([[tg.btn("\U0001F504 Retry", "buy"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    if not opt:
        edit("\U0001F6AB No WhatsApp numbers available right now. Please try again shortly.",
             tg.kb([[tg.btn("\U0001F504 Retry", "buy"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    enough = user["balance_paise"] >= opt["price_paise"]
    text = (
        "\U0001F4F2 <b>WhatsApp number — India \U0001F1EE\U0001F1F3</b>\n\n"
        f"Price: <b>{inr(opt['price_paise'])}</b>\n"
        f"In stock: {opt['count']}\n"
        f"Your balance: {inr(user['balance_paise'])}\n\n"
        + ("\u2705 Buy, then request the OTP in WhatsApp. No OTP in time = full refund."
           if enough else "\u274C Not enough balance. Add money first.")
    )
    if enough:
        rows = [[tg.btn(f"\u2705 Buy for {inr(opt['price_paise'])}", "bx", "success")],
                [tg.btn("\U0001F3E0 Menu", "mm")]]
    else:
        rows = [[tg.btn("\U0001F4B0 Add money", "dep", "success")], [tg.btn("\U0001F3E0 Menu", "mm")]]
    edit(text, tg.kb(rows))


def _do_buy(frm, chat_id, message_id) -> None:
    user = users.user_by_telegram_id(frm["id"])
    try:
        order = orders_mod.buy_whatsapp(user["id"])
    except orders_mod.OrderError as e:
        tg.edit_message(chat_id, message_id, f"\u274C {esc(str(e))}", tg.kb([[tg.btn("\U0001F504 Retry", "buy"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    orders_mod.set_order_message(order["id"], chat_id, message_id)
    t, k = order_view(order, db.now())
    tg.edit_message(chat_id, message_id, t, k)


# ---------- orders ----------

def _show_orders(edit, user) -> None:
    rows = db.q("SELECT * FROM orders WHERE user_id = ? AND status != 'buying' ORDER BY id DESC LIMIT 10", (user["id"],))
    if not rows:
        edit("\U0001F9FE You have no numbers yet.", tg.kb([[tg.btn("\U0001F4F2 Buy WhatsApp number", "buy", "primary"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    buttons = []
    for r in rows:
        o = dict(r)
        tag = {"received": "\U0001F525 OTP", "waiting": "\u23F3 waiting", "completed": "\u2705"}.get(o["status"], "\u21A9\uFE0F")
        num = f"+{o['phone']}" if o["phone"] else o["service_name"]
        buttons.append([tg.btn(f"\U0001F4F2 {num} \u00b7 {tag}", f"op:{o['id']}")])
    buttons.append([tg.btn("\U0001F3E0 Menu", "mm")])
    edit("\U0001F9FE <b>My numbers</b>\n\nTap one to open:", tg.kb(buttons))


def _open_order(chat_id, message_id, user, order_id) -> None:
    o = orders_mod.get_order(order_id)
    if not o or not orders_mod.order_belongs_to(o, user["id"]):
        tg.edit_message(chat_id, message_id, "Order not found.", tg.kb([[tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    orders_mod.set_order_message(o["id"], chat_id, message_id)
    t, k = order_view(o, db.now())
    tg.edit_message(chat_id, message_id, t, k)


def _check_now(chat_id, message_id, user, order_id, ack) -> None:
    o = orders_mod.get_order(order_id)
    if not o or not orders_mod.order_belongs_to(o, user["id"]):
        ack("Order not found.", True)
        return
    orders_mod.set_order_message(o["id"], chat_id, message_id)
    before = len(json.loads(o["codes"]))
    if o["status"] in ("waiting", "received"):
        try:
            orders_mod.check_order(o, 0)
        except Exception as e:  # noqa: BLE001
            print("[bot] checkNow", e)
    fresh = orders_mod.get_order(order_id)
    t, k = order_view(fresh, db.now())
    tg.edit_message(chat_id, message_id, t, k)
    after = len(json.loads(fresh["codes"]))
    ack("OTP received!" if after > before else ("No OTP yet. Keep waiting." if fresh["status"] == "waiting" else "Updated"))


def _do_cancel(chat_id, message_id, user, order_id, ack) -> None:
    o = orders_mod.get_order(order_id)
    if not o or not orders_mod.order_belongs_to(o, user["id"]):
        ack("Order not found.", True)
        return
    orders_mod.set_order_message(o["id"], chat_id, message_id)
    try:
        updated = orders_mod.cancel_order(o)
        t, k = order_view(updated, db.now())
        tg.edit_message(chat_id, message_id, t, k)
        ack("Cancelled and refunded")
    except orders_mod.OrderError as e:
        ack(str(e), True)
        fresh = orders_mod.get_order(order_id)
        t, k = order_view(fresh, db.now())
        tg.edit_message(chat_id, message_id, t, k)


def _do_done(chat_id, message_id, user, order_id, ack) -> None:
    o = orders_mod.get_order(order_id)
    if not o or not orders_mod.order_belongs_to(o, user["id"]):
        ack("Order not found.", True)
        return
    if o["status"] == "received":
        orders_mod.finish_order(o)
    fresh = orders_mod.get_order(order_id)
    t, k = order_view(fresh, db.now())
    tg.edit_message(chat_id, message_id, t, k)
    ack("Done")


# ---------- deposits ----------

def _show_deposit_menu(edit) -> None:
    amounts = [20, 50, 100, 200, 500, 1000]
    rows = []
    for i in range(0, len(amounts), 3):
        rows.append([tg.btn(f"\u20b9{a}", f"da:{a}", "success") for a in amounts[i:i + 3]])
    rows.append([tg.btn("\u270F\uFE0F Other amount", "dc")])
    rows.append([tg.btn("\U0001F3E0 Menu", "mm")])
    edit(f"\U0001F4B0 <b>Add money</b>\n\nChoose an amount to pay by UPI (min \u20b9{int(db.get_setting_number('min_topup_inr'))}):", tg.kb(rows))


def _submit_transaction_id(user, chat_id, payment_id, raw) -> None:
    try:
        paid = pay.claim_transaction_id(user["id"], payment_id, raw)
    except pay.PaymentError as e:
        tg.send_message(chat_id, f"\u274C {esc(str(e))}", tg.kb([[tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    if paid:
        tg.send_message(chat_id, f"\u2705 <b>{inr(paid['amount_paise'])} added to your wallet.</b>", tg.kb([[tg.btn("\U0001F3E0 Menu", "mm")]]))
    else:
        tg.send_message(
            chat_id,
            "\u2705 Got it. We'll verify your payment when the bank email arrives — usually within a minute. "
            "Your wallet updates automatically.",
            tg.kb([[tg.btn("\U0001F9FE My numbers", "ords"), tg.btn("\U0001F3E0 Menu", "mm")]]),
        )


def _start_deposit(user, chat_id, rupees) -> None:
    try:
        payment = pay.create_payment(user["id"], rupees)
    except pay.PaymentError as e:
        tg.send_message(chat_id, f"\u274C {esc(str(e))}", tg.kb([[tg.btn("\U0001F4B0 Try again", "dep", "success"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    png = pay.qr_png(payment["amount_paise"])
    sent = tg.send_photo(chat_id, png, deposit_caption(payment, db.now()), deposit_keyboard(payment))
    pay.set_payment_message(payment["id"], chat_id, sent["message_id"])


# ---------- in-bot admin panel ----------

def _admin(edit, ack, args) -> None:
    sub = args[0] if args else "menu"
    if sub == "menu":
        edit("\U0001F6E0\uFE0F <b>Admin panel</b>\n\nChoose an action:", tg.kb([
            [tg.btn("\U0001F4CA Stats", "adm:stats", "primary")],
            [tg.btn("\U0001F4B0 Pending deposits", "adm:dep", "success")],
            [tg.btn("\U0001F9FE Recent orders", "adm:ord")],
            [tg.btn("\U0001F3E0 Menu", "mm")],
        ]))
        ack()
    elif sub == "stats":
        edit(_stats_text(), tg.kb([[tg.btn("\u2B05\uFE0F Back", "adm")]]))
        ack()
    elif sub == "dep":
        _admin_deposits(edit)
        ack()
    elif sub == "ord":
        _admin_orders(edit)
        ack()
    elif sub == "ok":
        paid = pay.credit_payment(int(args[1]), _claimed_utr(int(args[1])), None)
        ack("Credited" if paid else "Already credited / cannot credit", True)
        _admin_deposits(edit)
    elif sub == "no":
        pay.cancel_payment(int(args[1]))
        ack("Rejected")
        _admin_deposits(edit)
    else:
        ack()


def _claimed_utr(payment_id):
    p = pay.get_payment(payment_id)
    return p["claimed_utr"] if p else None


def _stats_text() -> str:
    start = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) * 1000)
    users_n = db.one("SELECT COUNT(*) n FROM users")["n"]
    sales = db.one("SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s, COALESCE(SUM(cost_usd),0) c FROM orders WHERE status IN ('received','completed') AND created_at >= ?", (start,))
    topups = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?", (start,))
    rate = db.get_setting_number("usd_inr_rate")
    profit = sales["s"] - round(sales["c"] * rate * 100)
    try:
        bal = f"${phoenix.get_balance_usd():.2f}"
    except Exception:  # noqa: BLE001
        bal = "unavailable"
    return (
        "\U0001F4CA <b>Today</b>\n"
        f"Users: {users_n}\n"
        f"Numbers sold: {sales['n']} ({inr(sales['s'])})\n"
        f"Profit: {inr(profit)}\n"
        f"Deposits: {inr(topups['s'])}\n"
        f"Phoenix balance: {bal}"
    )


def _admin_deposits(edit) -> None:
    rows = db.q(
        "SELECT p.*, u.telegram_id, u.username FROM payments p JOIN users u ON u.id = p.user_id "
        "WHERE p.status IN ('pending', 'expired') ORDER BY p.id DESC LIMIT 12"
    )
    if not rows:
        edit("\U0001F4B0 <b>Pending deposits</b>\n\nNone right now.", tg.kb([[tg.btn("\U0001F504 Refresh", "adm:dep"), tg.btn("\u2B05\uFE0F Back", "adm")]]))
        return
    lines, btns = [], []
    for r in rows:
        who = ("@" + r["username"]) if r["username"] else str(r["telegram_id"])
        claim = f" \u00b7 ID {esc(r['claimed_utr'])}" if r["claimed_utr"] else ""
        lines.append(f"#{r['id']} {inr(r['amount_paise'])} {esc(who)}{claim} [{r['status']}]")
        btns.append([tg.btn(f"\u2705 Approve #{r['id']}", f"adm:ok:{r['id']}", "success"), tg.btn(f"\u274C #{r['id']}", f"adm:no:{r['id']}", "danger")])
    btns.append([tg.btn("\U0001F504 Refresh", "adm:dep"), tg.btn("\u2B05\uFE0F Back", "adm")])
    edit("\U0001F4B0 <b>Pending deposits</b>\n\n" + "\n".join(lines) + "\n\nApprove only after you confirm the money in your account.", tg.kb(btns))


def _admin_orders(edit) -> None:
    rows = db.q(
        "SELECT o.id, o.phone, o.price_paise, o.status, o.created_at, u.username, u.telegram_id "
        "FROM orders o JOIN users u ON u.id = o.user_id WHERE o.status != 'buying' ORDER BY o.id DESC LIMIT 10"
    )
    if not rows:
        edit("\U0001F9FE <b>Recent orders</b>\n\nNone yet.", tg.kb([[tg.btn("\u2B05\uFE0F Back", "adm")]]))
        return
    lines = []
    for r in rows:
        who = ("@" + r["username"]) if r["username"] else str(r["telegram_id"])
        num = f"+{r['phone']}" if r["phone"] else "\u2014"
        lines.append(f"#{r['id']} {num} {inr(r['price_paise'])} [{r['status']}] {esc(who)}")
    edit("\U0001F9FE <b>Recent orders</b>\n\n" + "\n".join(lines), tg.kb([[tg.btn("\U0001F504 Refresh", "adm:ord"), tg.btn("\u2B05\uFE0F Back", "adm")]]))


def _send_admin_stats(chat_id) -> None:
    start = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) * 1000)
    users_n = db.one("SELECT COUNT(*) n FROM users")["n"]
    sales = db.one("SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s FROM orders WHERE status IN ('received','completed') AND created_at >= ?", (start,))
    topups = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?", (start,))
    try:
        bal = f"${phoenix.get_balance_usd():.2f}"
    except Exception:  # noqa: BLE001
        bal = "unavailable"
    tg.send_message(
        chat_id,
        "\U0001F4CA <b>Today</b>\n"
        f"Users: {users_n}\n"
        f"Numbers sold: {sales['n']} ({inr(sales['s'])})\n"
        f"Deposits: {inr(topups['s'])}\n"
        f"Phoenix balance: {bal}\n\n"
        "Full controls: open the web admin panel.",
    )
