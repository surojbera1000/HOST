"""Pricing rules. Default price = cost(USD) × USD→INR rate, then an optional rule."""
import math

import db


def get_price_rules() -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM price_rules ORDER BY service, country")]


def make_pricer():
    """
    Returns price(service, country, cost_usd) -> (price_paise, hidden).
    Rule priority: service+country > service+'*' > '*'+country > global markup.
    Modes:
      default : cost × rate
      markup  : cost × rate × (1 + value%/100)
      plus    : cost × rate + value ₹        (the ₹40 WhatsApp margin)
      fixed   : value ₹ (flat total)
    """
    rate = db.get_setting_number("usd_inr_rate")
    global_markup = db.get_setting_number("global_markup_pct")
    rules = {}
    for r in get_price_rules():
        rules[f"{r['service']}|{r['country']}"] = r

    def price(service: str, country: str, cost_usd: float):
        rule = (
            rules.get(f"{service}|{country}")
            or rules.get(f"{service}|*")
            or rules.get(f"*|{country}")
        )
        hidden = bool(rule and rule["hidden"])
        base = cost_usd * rate
        if rule and rule["mode"] == "fixed" and rule["value"] > 0:
            rupees = rule["value"]
        elif rule and rule["mode"] == "plus":
            rupees = base + rule["value"]
        elif rule and rule["mode"] == "markup":
            rupees = base * (1 + rule["value"] / 100)
        else:
            rupees = base * (1 + global_markup / 100)
        return max(1, math.ceil(rupees * 100)), hidden

    return price
