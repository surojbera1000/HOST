"""GrizzlySMS handler API client (sms-activate compatible). The API key stays on the server."""
import re
import time
from typing import Optional

import requests

import config

_cache: dict[str, tuple[float, object]] = {}


class GrizzlyError(Exception):
    def __init__(self, code: str, message: Optional[str] = None):
        super().__init__(message or code)
        self.code = code


def _call(params: dict) -> str:
    if not config.GRIZZLY_API_KEY:
        raise GrizzlyError("NO_KEY", "GRIZZLY_API_KEY is not set")
    p = {"api_key": config.GRIZZLY_API_KEY}
    p.update({k: v for k, v in params.items() if v is not None and v != ""})
    r = requests.get(config.GRIZZLY_BASE_URL, params=p, timeout=20, headers={"User-Agent": "MikuOTPBot/1.0"})
    if not r.ok:
        raise GrizzlyError(f"HTTP_{r.status_code}", r.text[:200])
    return r.text.strip()


def _json(text: str):
    import json

    try:
        return json.loads(text)
    except ValueError:
        raise GrizzlyError(text[:60] or "EMPTY_RESPONSE")


def _cached(key: str, ttl_ms: float, fn):
    hit = _cache.get(key)
    now = time.time() * 1000
    if hit and now - hit[0] < ttl_ms:
        return hit[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def get_balance_usd() -> float:
    text = _call({"action": "getBalance"})
    m = re.match(r"^ACCESS_BALANCE:([\d.]+)$", text)
    if not m:
        raise GrizzlyError(text)
    return float(m.group(1))


def get_services() -> list[dict]:
    def load():
        data = _json(_call({"action": "getServicesList"}))
        return data.get("services", []) if isinstance(data, dict) else []

    return _cached("services", 60 * 60_000, load)


def get_countries() -> dict[str, str]:
    def load():
        data = _json(_call({"action": "getCountries"}))
        out = {}
        for c in data.values():
            out[str(c["id"])] = c["eng"]
        return out

    return _cached("countries", 60 * 60_000, load)


def get_service_prices(service: str, fresh: bool = False) -> list[dict]:
    def load():
        data = _json(_call({"action": "getPrices", "service": service}))
        out = []
        for country, services in data.items():
            p = services.get(service) if isinstance(services, dict) else None
            if p:
                out.append({"country": country, "cost_usd": float(p["cost"]), "count": int(p["count"])})
        return out

    if fresh:
        return load()
    return _cached(f"prices:{service}", 60_000, load)


def get_number(service: str, country: str, max_price: float) -> tuple[str, str]:
    text = _call({"action": "getNumber", "service": service, "country": country, "maxPrice": max_price})
    m = re.match(r"^ACCESS_NUMBER:(\d+):(\d+)$", text)
    if not m:
        raise GrizzlyError(text)
    return m.group(1), m.group(2)


def get_status(activation_id: str) -> dict:
    text = _call({"action": "getStatus", "id": activation_id})
    if text in ("STATUS_WAIT_CODE", "STATUS_WAIT_RESEND") or text.startswith("STATUS_WAIT_RETRY"):
        return {"state": "wait"}
    if text.startswith("STATUS_OK:"):
        return {"state": "code", "code": text[10:]}
    if text == "STATUS_CANCEL":
        return {"state": "cancelled"}
    return {"state": "unknown", "raw": text}


def set_status(activation_id: str, status: int) -> str:
    """status: 1=ready, 3=another SMS, 6=finish, 8=cancel"""
    return _call({"action": "setStatus", "id": activation_id, "status": status})


def friendly_error(code: str) -> str:
    if code.startswith("NO_NUMBERS"):
        return "No numbers available right now. Try another country."
    if code.startswith("NO_BALANCE"):
        return "This service is temporarily unavailable. Please try again later."
    if code.startswith("EARLY_CANCEL_DENIED"):
        return "You can cancel only a few minutes after purchase. Please wait."
    if code.startswith("BAD_SERVICE") or "prohibited" in code:
        return "This service is not available right now."
    if code.startswith("WRONG_MAX_PRICE"):
        return "Price changed. Please go back and try again."
    return "Provider error. Please try again."
