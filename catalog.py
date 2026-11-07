"""Services and country price lists for the bot."""
import grizzly
from pricing import make_pricer

# Service codes shown first, in this order.
POPULAR = ["wa", "tg", "go", "ig", "fb", "lf", "fu", "am", "tw", "ds", "nf", "ub", "bye", "mb", "ot"]


def popular_services() -> list[dict]:
    by_code = {s["code"]: s for s in grizzly.get_services()}
    out = []
    for code in POPULAR:
        s = by_code.get(code)
        if s:
            out.append({"code": s["code"], "name": s["name"]})
    return out


def search_services(query: str) -> list[dict]:
    qn = query.strip().lower()
    if not qn:
        return []
    res = [s for s in grizzly.get_services() if qn in s["name"].lower() or s["code"] == qn]
    res.sort(key=lambda s: 0 if s["name"].lower().startswith(qn) else 1)
    return [{"code": s["code"], "name": s["name"]} for s in res[:24]]


def service_name(services: list[dict], code: str) -> str:
    for s in services:
        if s["code"] == code:
            return s["name"]
    return code


def country_options(service: str) -> list[dict]:
    prices = grizzly.get_service_prices(service)
    countries = grizzly.get_countries()
    price = make_pricer()
    out = []
    for p in prices:
        if p["count"] <= 0 or p["country"] not in countries:
            continue
        price_paise, hidden = price(service, p["country"], p["cost_usd"])
        if hidden:
            continue
        out.append({"country": p["country"], "name": countries[p["country"]], "count": p["count"], "price_paise": price_paise})
    out.sort(key=lambda c: c["price_paise"])
    return out
