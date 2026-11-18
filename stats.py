"""Aggregate numbers for the admin panel and user profiles."""
import db


def totals() -> dict:
    """All-time totals across everyone."""
    o = db.one(
        "SELECT COUNT(*) t, "
        "COALESCE(SUM(status IN ('received','completed')),0) done, "
        "COALESCE(SUM(status IN ('cancelled','failed')),0) cancel, "
        "COALESCE(SUM(CASE WHEN status IN ('received','completed') THEN price_paise ELSE 0 END),0) spent "
        "FROM orders WHERE status != 'buying'"
    )
    added = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid'")["s"]
    return {
        "orders_total": o["t"] or 0,
        "orders_done": o["done"] or 0,
        "orders_cancel": o["cancel"] or 0,
        "deducted_paise": o["spent"] or 0,
        "added_paise": added or 0,
    }


def user_stats(user_id: int) -> dict:
    o = db.one(
        "SELECT COUNT(*) t, "
        "COALESCE(SUM(status IN ('received','completed')),0) done, "
        "COALESCE(SUM(status IN ('cancelled','failed')),0) cancel, "
        "COALESCE(SUM(CASE WHEN status IN ('received','completed') THEN price_paise ELSE 0 END),0) spent "
        "FROM orders WHERE status != 'buying' AND user_id = ?",
        (user_id,),
    )
    added = db.one("SELECT COALESCE(SUM(amount_paise),0) s FROM payments WHERE status = 'paid' AND user_id = ?", (user_id,))["s"]
    return {
        "orders_total": o["t"] or 0,
        "orders_done": o["done"] or 0,
        "orders_cancel": o["cancel"] or 0,
        "spent_paise": o["spent"] or 0,
        "added_paise": added or 0,
    }
