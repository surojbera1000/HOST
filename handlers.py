"""Telegram update handling: menu, buy flow, deposits, orders."""
import json
import threading
import time

import catalog
import config
import db
import grizzly
import orders as orders_mod
import payments as pay
import tg
import users
from format_utils import esc, flag, inr
from notify import notify_admins
from render import deposit_caption, deposit_keyboard, main_menu, order_view

# Simple per-user session for free-text input (search / custom amount).
_sessions: dict[int, tuple[str, float]] = {}
_slock = threading.Lock()
COUNTRIES_PER_PAGE = 8


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
        t, k = main_menu(user)
        tg.send_message(chat_id, t, k)
        return
    if text == "/balance":
        tg.send_message(chat_id, f"\U0001F4B0 Your balance: <b>{inr(user['balance_paise'])}</b>")
        return
    if text == "/admin" and users.is_admin(frm["id"]):
        _send_admin_stats(chat_id)
        return

    mode = _take_session(frm["id"])
    if mode == "search":
        _show_service_search(chat_id, text)
        return
    if mode == "amount":
        digits = "".join(c for c in text if c.isdigit())
        _start_deposit(user, chat_id, int(digits) if digits else 0)
        return

    t, k = main_menu(user)
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
            t, k = main_menu(fresh)
            edit(t, k)
            ack()
        elif cmd == "buy":
            _show_services(edit)
            ack()
        elif cmd == "ss":
            _set_session(frm["id"], "search")
            edit("\U0001F50D <b>Search app</b>\n\nSend me the app name (for example: <i>WhatsApp</i>, <i>Telegram</i>, <i>Instagram</i>).")
            ack()
        elif cmd == "sv":
            _show_countries(edit, args[0], 0)
            ack()
        elif cmd == "ct":
            _show_countries(edit, args[0], int(args[1]))
            ack()
        elif cmd == "cf":
            _show_confirm(edit, user, args[0], args[1])
            ack()
        elif cmd == "bx":
            ack("Getting your number\u2026")
            _do_buy(frm, chat_id, message_id, args[0], args[1])
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
        elif cmd == "rty":
            _do_retry(user, int(args[0]), ack)
        elif cmd == "don":
            _do_done(chat_id, message_id, user, int(args[0]), ack)
        else:
            ack()
    except (orders_mod.OrderError, pay.PaymentError) as e:
        ack(str(e), True)
    except Exception as e:  # noqa: BLE001
        print("[bot] callback error", data, e)
        ack("Something went wrong. Try again.", True)


# ---------- buy flow ----------

def _show_services(edit) -> None:
    services = catalog.popular_services()
    rows = []
    for i in range(0, len(services), 2):
        rows.append([tg.btn(_clip(s["name"]), f"sv:{s['code']}") for s in services[i:i + 2]])
    rows.append([tg.btn("\U0001F50D Search other app", "ss", "primary")])
    rows.append([tg.btn("\U0001F3E0 Menu", "mm")])
    edit("\U0001F4F1 <b>Choose an app</b>\n\nPick the app you want a number for:", tg.kb(rows))


def _show_service_search(chat_id: int, query: str) -> None:
    found = catalog.search_services(query)
    if not found:
        tg.send_message(chat_id, f"No app found for \u201c{esc(query)}\u201d. Try another name.",
                        tg.kb([[tg.btn("\U0001F50D Search again", "ss"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    rows = []
    for i in range(0, len(found), 2):
        rows.append([tg.btn(_clip(s["name"]), f"sv:{s['code']}") for s in found[i:i + 2]])
    rows.append([tg.btn("\U0001F3E0 Menu", "mm")])
    tg.send_message(chat_id, f"\U0001F50D Results for \u201c{esc(query)}\u201d:", tg.kb(rows))


def _show_countries(edit, service: str, page: int) -> None:
    services = catalog.popular_services()
    name = catalog.service_name(services, service)
    try:
        lst = catalog.country_options(service)
    except Exception:  # noqa: BLE001
        edit("Could not load prices. Please try again.", tg.kb([[tg.btn("\U0001F504 Retry", f"sv:{service}"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    if not lst:
        edit(f"No numbers available for <b>{esc(name)}</b> right now.", tg.kb([[tg.btn("\u2B05\uFE0F Back", "buy"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    pages = (len(lst) + COUNTRIES_PER_PAGE - 1) // COUNTRIES_PER_PAGE
    p = max(0, min(page, pages - 1))
    rows = []
    for c in lst[p * COUNTRIES_PER_PAGE:(p + 1) * COUNTRIES_PER_PAGE]:
        cnt = f"{c['count'] // 1000}k" if c["count"] > 999 else str(c["count"])
        rows.append([tg.btn(f"{flag(c['name'])} {c['name']} \u00b7 {inr(c['price_paise'])} \u00b7 {cnt}", f"cf:{service}:{c['country']}")])
    nav = []
    if p > 0:
        nav.append(tg.btn("\u2B05\uFE0F Prev", f"ct:{service}:{p - 1}"))
    if p < pages - 1:
        nav.append(tg.btn("Next \u27A1\uFE0F", f"ct:{service}:{p + 1}"))
    if nav:
        rows.append(nav)
    rows.append([tg.btn("\u2B05\uFE0F Apps", "buy"), tg.btn("\U0001F3E0 Menu", "mm")])
    edit(f"<b>{esc(name)}</b> \u2014 choose a country\n<i>Cheapest first \u00b7 page {p + 1}/{pages}</i>", tg.kb(rows))


def _show_confirm(edit, user, service, country) -> None:
    lst = catalog.country_options(service)
    c = next((x for x in lst if x["country"] == country), None)
    name = catalog.service_name(catalog.popular_services(), service)
    if not c:
        edit("That option is gone. Please pick again.", tg.kb([[tg.btn("\u2B05\uFE0F Back", f"sv:{service}"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    enough = user["balance_paise"] >= c["price_paise"]
    text = (
        "\U0001F9FE <b>Confirm purchase</b>\n\n"
        f"App: <b>{esc(name)}</b>\n"
        f"Country: {flag(c['name'])} <b>{esc(c['name'])}</b>\n"
        f"Price: <b>{inr(c['price_paise'])}</b>\n"
        f"Your balance: {inr(user['balance_paise'])}\n\n"
        + ("\u2705 If no OTP comes, you can cancel and get a refund." if enough else "\u274C Not enough balance. Add money first.")
    )
    if enough:
        rows = [[tg.btn(f"\u2705 Buy for {inr(c['price_paise'])}", f"bx:{service}:{country}", "success")],
                [tg.btn("\u2B05\uFE0F Back", f"sv:{service}"), tg.btn("\U0001F3E0 Menu", "mm")]]
    else:
        rows = [[tg.btn("\U0001F4B0 Add money", "dep", "success")],
                [tg.btn("\u2B05\uFE0F Back", f"sv:{service}"), tg.btn("\U0001F3E0 Menu", "mm")]]
    edit(text, tg.kb(rows))


def _do_buy(frm, chat_id, message_id, service, country) -> None:
    user = users.user_by_telegram_id(frm["id"])
    try:
        order = orders_mod.buy_number(user["id"], service, country)
    except orders_mod.OrderError as e:
        tg.edit_message(chat_id, message_id, f"\u274C {esc(str(e))}", tg.kb([[tg.btn("\u2B05\uFE0F Back", f"sv:{service}"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    orders_mod.set_order_message(order["id"], chat_id, message_id)
    t, k = order_view(order, db.now())
    tg.edit_message(chat_id, message_id, t, k)


# ---------- orders ----------

def _show_orders(edit, user) -> None:
    rows = db.q("SELECT * FROM orders WHERE user_id = ? AND status != 'buying' ORDER BY id DESC LIMIT 10", (user["id"],))
    if not rows:
        edit("\U0001F9FE You have no numbers yet.", tg.kb([[tg.btn("\U0001F4F1 Buy a number", "buy", "primary"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    buttons = []
    for r in rows:
        o = dict(r)
        tag = {"received": "\U0001F525 OTP", "waiting": "\u23F3 waiting", "completed": "\u2705"}.get(o["status"], "\u21A9\uFE0F")
        buttons.append([tg.btn(f"{flag(o['country_name'])} {o['service_name']} \u00b7 {tag}", f"op:{o['id']}")])
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


def _do_retry(user, order_id, ack) -> None:
    o = orders_mod.get_order(order_id)
    if not o or not orders_mod.order_belongs_to(o, user["id"]):
        ack("Order not found.", True)
        return
    try:
        orders_mod.request_another_sms(o)
        ack("Asked for another OTP. Wait a moment.")
    except orders_mod.OrderError as e:
        ack(str(e), True)


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


def _start_deposit(user, chat_id, rupees) -> None:
    try:
        payment = pay.create_payment(user["id"], rupees)
    except pay.PaymentError as e:
        tg.send_message(chat_id, f"\u274C {esc(str(e))}", tg.kb([[tg.btn("\U0001F4B0 Try again", "dep", "success"), tg.btn("\U0001F3E0 Menu", "mm")]]))
        return
    png = pay.qr_png(payment["amount_paise"])
    sent = tg.send_photo(chat_id, png, deposit_caption(payment, db.now()), deposit_keyboard(payment))
    pay.set_payment_message(payment["id"], chat_id, sent["message_id"])


# ---------- admin ----------

def _send_admin_stats(chat_id) -> None:
    start = int(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)) * 1000)
    users_n = db.one("SELECT COUNT(*) n FROM users")["n"]
    sales = db.one("SELECT COUNT(*) n, COALESCE(SUM(price_paise),0) s FROM orders WHERE status IN ('received','completed') AND created_at >= ?", (start,))
    topups = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND paid_at >= ?", (start,))
    try:
        bal = f"${grizzly.get_balance_usd():.2f}"
    except Exception:  # noqa: BLE001
        bal = "unavailable"
    tg.send_message(
        chat_id,
        "\U0001F4CA <b>Today</b>\n"
        f"Users: {users_n}\n"
        f"Numbers sold: {sales['n']} ({inr(sales['s'])})\n"
        f"Deposits: {inr(topups['s'])}\n"
        f"GrizzlySMS balance: {bal}\n\n"
        "Full controls: open the web admin panel.",
    )


def _clip(name: str) -> str:
    return name if len(name) <= 20 else name[:19] + "\u2026"
