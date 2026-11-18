"""Minimal Telegram Bot API client (raw HTTP) with coloured buttons (Bot API 9.4) and copy buttons."""
from typing import Any, Optional

import requests

import config
import premium

_API = None


def _base() -> str:
    global _API
    if _API is None:
        _API = f"https://api.telegram.org/bot{config.BOT_TOKEN}"
    return _API


class TgError(Exception):
    def __init__(self, code: int, description: str):
        super().__init__(f"Telegram {code}: {description}")
        self.code = code
        self.description = description


def call(method: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> Any:
    r = requests.post(f"{_base()}/{method}", json=params or {}, timeout=timeout or (70 if method == "getUpdates" else 30))
    data = r.json()
    if not data.get("ok"):
        raise TgError(data.get("error_code", r.status_code), data.get("description", "unknown"))
    return data.get("result")


# ---------- keyboard builders ----------

def btn(text: str, data: str, style: Optional[str] = None) -> dict:
    b = {"text": text, "callback_data": data}
    if style:
        b["style"] = style
    return b


def url_btn(text: str, url: str) -> dict:
    return {"text": text, "url": url}


def copy_btn(text: str, value: str) -> dict:
    return {"text": text, "copy_text": {"text": value}}


def kb(rows: list[list[dict]]) -> Optional[dict]:
    rows = [r for r in rows if r]
    return {"inline_keyboard": rows} if rows else None


def _safe(method: str, params: dict) -> Optional[object]:
    """Call Telegram; treat 'not modified' as success; on a bad reply_markup, retry without it."""
    try:
        return call(method, params)
    except TgError as e:
        d = e.description.lower()
        if "not modified" in d:
            return None
        if "reply markup" in d and params.get("reply_markup") is not None:
            p2 = dict(params)
            p2.pop("reply_markup", None)
            return call(method, p2)
        raise


def send_message(chat_id: int, text: str, keyboard: Optional[dict] = None) -> dict:
    base = {"chat_id": chat_id, "link_preview_options": {"is_disabled": True}, "reply_markup": keyboard}
    conv = premium.convert(text) if premium.enabled() else None
    if conv:
        try:
            return _safe("sendMessage", {**base, "text": conv[0], "entities": conv[1]})
        except TgError:
            pass  # fall back to HTML
    return _safe("sendMessage", {**base, "text": text, "parse_mode": "HTML"})


def edit_message(chat_id: int, message_id: int, text: str, keyboard: Optional[dict] = None) -> None:
    base = {"chat_id": chat_id, "message_id": message_id, "link_preview_options": {"is_disabled": True}, "reply_markup": keyboard}
    conv = premium.convert(text) if premium.enabled() else None
    if conv:
        try:
            _safe("editMessageText", {**base, "text": conv[0], "entities": conv[1]})
            return
        except TgError:
            pass  # fall through to HTML
    _safe("editMessageText", {**base, "text": text, "parse_mode": "HTML"})


def edit_caption(chat_id: int, message_id: int, caption: str, keyboard: Optional[dict] = None) -> None:
    _safe(
        "editMessageCaption",
        {"chat_id": chat_id, "message_id": message_id, "caption": caption, "parse_mode": "HTML", "reply_markup": keyboard},
    )


def send_photo(chat_id: int, photo: bytes, caption: str, keyboard: Optional[dict] = None) -> dict:
    import json as _json

    data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = _json.dumps(keyboard)
    r = requests.post(f"{_base()}/sendPhoto", data=data, files={"photo": ("qr.png", photo, "image/png")}, timeout=30)
    res = r.json()
    if not res.get("ok"):
        raise TgError(res.get("error_code", r.status_code), res.get("description", "unknown"))
    return res["result"]


def answer_callback(cq_id: str, text: Optional[str] = None, alert: bool = False) -> None:
    try:
        call("answerCallbackQuery", {"callback_query_id": cq_id, "text": text, "show_alert": alert})
    except TgError:
        pass
