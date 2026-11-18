"""WhatsApp (India) option for the bot, with the final customer price."""
import phoenix
from pricing import make_pricer

WA_SERVICE = "wa"
INDIA_ID = phoenix.INDIA_ID


def india_option(fresh: bool = False):
    """Returns {'count', 'price_paise'} for India WhatsApp, or None if out of stock / hidden."""
    info = phoenix.wa_india(fresh=fresh)
    if not info or info["count"] <= 0:
        return None
    price_paise, hidden = make_pricer()(WA_SERVICE, INDIA_ID, info["price"])
    if hidden:
        return None
    return {"count": info["count"], "price_paise": price_paise, "cost_usd": info["price"]}
