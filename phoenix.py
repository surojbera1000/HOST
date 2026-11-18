"""Phoenix Store reseller API client (WhatsApp number rental, India only). Bearer auth."""
import time
from typing import Optional

import requests

import config

INDIA_ID = "22"
_cache: dict[str, tuple[float, object]] = {}


class PhoenixError(Exception):
    def __init__(self, code: str, message: Optional[str] = None, http: int = 0):
        super().__init__(message or code)
        self.code = code
        self.http = http


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.PHOENIX_API_KEY}", "Accept": "application/json"}


def _call(method: str, path: str, params: Optional[dict] = None) -> dict:
    if not config.PHOENIX_API_KEY:
        raise PhoenixError("unauthorized", "PHOENIX_API_KEY is not set")
    url = config.PHOENIX_BASE_URL + path
    try:
        r = requests.request(method, url, headers=_headers(), params=params, timeout=30)
    except requests.RequestException as e:
        raise PhoenixError("upstream_error", str(e), 502)
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not r.ok:
        err = {}
        if isinstance(data, dict) and isinstance(data.get("errors"), list) and data["errors"]:
            err = data["errors"][0]
        raise PhoenixError(err.get("code", f"http_{r.status_code}"), err.get("message", r.text[:200]), r.status_code)
    return data if isinstance(data, dict) else {}


def _cached(key: str, ttl_ms: float, fn):
    hit = _cache.get(key)
    nowt = time.time() * 1000
    if hit and nowt - hit[0] < ttl_ms:
        return hit[1]
    value = fn()
    _cache[key] = (nowt, value)
    return value


def get_balance_usd() -> float:
    return float(_call("GET", "/balance").get("balance", 0.0))


def wa_params() -> dict:
    return _cached("wa_params", 5 * 60_000, lambda: _call("GET", "/whatsapp/params"))


def cancel_lock_seconds() -> int:
    try:
        return int(wa_params().get("cancel_lock_seconds", 120))
    except Exception:  # noqa: BLE001
        return 120


def wa_india(fresh: bool = False) -> Optional[dict]:
    """Returns {'count', 'price'} for India (country_id 22), or None if not listed."""
    def load():
        data = _call("GET", "/whatsapp", {"page": 1, "per_page": 40})
        for it in data.get("items", []):
            if str(it.get("country_id")) == INDIA_ID:
                return {"count": int(it.get("count", 0)), "price": float(it.get("price", 0.0))}
        return None

    if fresh:
        return load()
    return _cached("wa_india", 60_000, load)


def wa_buy() -> dict:
    """POST /whatsapp/22/buy -> order dict {order_ref, phone, price_usd, expires_in_seconds, ...}."""
    data = _call("POST", f"/whatsapp/{INDIA_ID}/buy")
    order = data.get("order", {})
    item = data.get("item", {})
    return {
        "order_ref": order.get("order_ref"),
        "phone": (order.get("phone") or item.get("whatsapp_phone") or "").lstrip("+"),
        "price_usd": float(order.get("price_usd", item.get("price", 0.0))),
        "expires_in_seconds": int(order.get("expires_in_seconds", 1200)),
        "status": order.get("status", "wa_pending"),
    }


def wa_code(order_ref: str) -> dict:
    """GET /whatsapp/{order_ref}/code -> {ok, codes:[{code}], status}."""
    data = _call("GET", f"/whatsapp/{order_ref}/code")
    return {
        "ok": bool(data.get("ok")),
        "codes": [c.get("code") for c in data.get("codes", []) if c.get("code")],
        "status": data.get("status", ""),
    }


def wa_cancel(order_ref: str) -> dict:
    return _call("POST", f"/whatsapp/{order_ref}/cancel")


def friendly_error(code: str) -> str:
    return {
        "insufficient_balance": "Store balance is low. Please try again later.",
        "out_of_stock": "No WhatsApp numbers available right now. Try again shortly.",
        "country_not_supported": "Only India WhatsApp numbers are available.",
        "rate_limit": "Too many requests. Please wait a moment.",
        "purchase_failed": "Could not get a number. You were refunded. Try again.",
        "upstream_error": "Service is busy. Please try again in a moment.",
        "forbidden": "This action is not allowed.",
        "not_found": "Not found.",
    }.get(code, "Provider error. Please try again.")
