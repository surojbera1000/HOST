"""Builds message text + keyboards (shared by the bot and the background workers)."""
import json

import config
import db
from format_utils import countdown, esc, flag, inr
from orders import CANCEL_AFTER_MS
from tg import btn, copy_btn, kb, url_btn


def _support_url() -> str:
    return f"https://t.me/{config.SUPPORT_USERNAME}"


def main_menu(user: dict) -> tuple[str, dict]:
    text = (
        "\U0001F44B <b>Welcome to Miku OTP</b>\n"
        "Buy a phone number, get the OTP here. No OTP? Your money comes back.\n\n"
        f"\U0001F4B0 <b>Balance:</b> {inr(user['balance_paise'])}"
    )
    return text, kb([
        [btn("\U0001F4F1  Buy a number", "buy", "primary")],
        [btn("\U0001F4B0  Add money", "dep", "success"), btn("\U0001F9FE  My numbers", "ords")],
        [btn("\U0001F504  Refresh", "mm"), url_btn("\U0001F4AC  Support", _support_url())],
    ])


def order_view(o: dict, now_ms: int) -> tuple[str, dict]:
    codes = json.loads(o["codes"])
    last = codes[-1] if codes else None
    head = f"{flag(o['country_name'])} <b>{esc(o['service_name'])}</b> \u00b7 {esc(o['country_name'])} \u00b7 {inr(o['price_paise'])}"
    number = f"+{o['phone']}" if o["phone"] else "\u2014"

    if o["status"] == "received" and last:
        earlier = codes[:-1]
        text = (
            f"{head}\n\n"
            f"\U0001F4F1 Number: <code>{esc(number)}</code>\n\n"
            f"\U0001F525 <b>YOUR OTP</b>\n<code>{esc(last)}</code>"
        )
        if earlier:
            text += "\n\nEarlier: " + ", ".join(f"<code>{esc(c)}</code>" for c in earlier)
        return text, kb([
            [copy_btn("\U0001F4CB Copy OTP", last), copy_btn("\U0001F4CB Copy number", number)],
            [btn("\U0001F501 Get another OTP", f"rty:{o['id']}"), btn("\u2705 Done", f"don:{o['id']}", "success")],
            [btn("\U0001F3E0 Menu", "mm")],
        ])

    if o["status"] == "waiting":
        left = o["expires_at"] - now_ms
        cancel_in = o["created_at"] + CANCEL_AFTER_MS - now_ms
        cancel_row = (
            [btn(f"\U0001F6AB Cancel in {countdown(cancel_in)}", "noop")]
            if cancel_in > 0
            else [btn("\U0001F6AB Cancel & refund", f"ccl:{o['id']}", "danger")]
        )
        text = (
            f"{head}\n\n"
            f"\U0001F4F1 Number: <code>{esc(number)}</code>\n"
            f"\u23F3 <b>Waiting for OTP\u2026</b>\n"
            f"\u23F1 Time left: {countdown(left)}\n\n"
            "Use this number in the app now. The OTP appears here by itself."
        )
        return text, kb([
            [copy_btn("\U0001F4CB Copy number", number)],
            [btn("\U0001F504 Check OTP now", f"chk:{o['id']}", "primary")],
            cancel_row,
            [btn("\U0001F3E0 Menu", "mm")],
        ])

    refunded = o["status"] in ("cancelled", "failed")
    body = "\u2705 Completed." if o["status"] == "completed" else (f"\u21A9\uFE0F {esc(o['error'] or 'Cancelled')} \u00b7 refunded." if refunded else "")
    text = f"{head}\n\n{body}"
    if codes:
        text += "\n\nOTP: " + ", ".join(f"<code>{esc(c)}</code>" for c in codes)
    return text, kb([[btn("\U0001F4F1 Buy another", "buy", "primary"), btn("\U0001F3E0 Menu", "mm")]])


def deposit_caption(p: dict, now_ms: int) -> str:
    if p["status"] == "paid":
        s = f"\u2705 <b>{inr(p['amount_paise'])} added to your wallet!</b>"
        if p["utr"]:
            s += f"\nTransaction ID: <code>{esc(p['utr'])}</code>"
        return s
    if p["status"] != "pending" or p["expires_at"] <= now_ms:
        return "\u23F0 This deposit timed out. If you already paid, it will still be added automatically within a minute."
    return (
        "\U0001F4B0 <b>Add money</b>\n\n"
        f"Pay exactly <b>{inr(p['amount_paise'])}</b> to:\n"
        f"<code>{esc(db.get_setting('upi_id'))}</code>\n\n"
        f"\u23F1 Pay within <b>{countdown(p['expires_at'] - now_ms)}</b>\n\n"
        "1\uFE0F\u20E3 Scan the QR in any UPI app (GPay, PhonePe, Paytm, FamApp)\n"
        "2\uFE0F\u20E3 Pay the <b>exact</b> amount, including paise\n"
        "3\uFE0F\u20E3 Stay here \u2014 money is added automatically"
    )


def deposit_keyboard(p: dict) -> dict:
    if p["status"] == "pending":
        return kb([
            [copy_btn(f"\U0001F4CB Copy \u20b9{p['amount_paise'] / 100:.2f}", f"{p['amount_paise'] / 100:.2f}")],
            [btn("\U0001F6AB Cancel", f"dcl:{p['id']}", "danger")],
            [url_btn("\U0001F4AC Support", _support_url())],
        ])
    return kb([[btn("\U0001F4B0 Add again", "dep", "success"), btn("\U0001F3E0 Menu", "mm")]])
