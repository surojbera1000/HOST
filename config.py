"""Configuration loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, fallback: str = "") -> str:
    return (os.environ.get(name) or fallback).strip()


def _list(name: str) -> list[str]:
    return [p.strip() for p in _env(name).split(",") if p.strip()]


BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
GRIZZLY_API_KEY = _env("GRIZZLY_API_KEY")
GRIZZLY_BASE_URL = _env("GRIZZLY_BASE_URL", "https://api.grizzlysms.com/stubs/handler_api.php")
DATABASE_PATH = _env("DATABASE_PATH", "./data/bot.sqlite")

# Telegram numeric user IDs that are admins (get notifications + /admin in the bot).
ADMIN_TELEGRAM_IDS = [int(x) for x in _list("ADMIN_TELEGRAM_IDS") if x.lstrip("-").isdigit()]

# Web admin panel
ADMIN_PANEL_PORT = int(_env("ADMIN_PANEL_PORT", "8080") or "8080")
ADMIN_PANEL_PASSWORD = _env("ADMIN_PANEL_PASSWORD")

# Gmail that receives FamApp payment emails (for automatic deposits)
GMAIL_USER = _env("GMAIL_USER")
GMAIL_APP_PASSWORD = _env("GMAIL_APP_PASSWORD").replace(" ", "")
GMAIL_POLL_SECONDS = int(_env("GMAIL_POLL_SECONDS", "15") or "15")
_fam = _list("FAMPAY_SENDER_DOMAINS")
FAMPAY_DOMAINS = _fam if _fam else ["famapp.in"]
REQUIRE_DKIM = _env("GMAIL_REQUIRE_DKIM", "true") != "false"

SUPPORT_USERNAME = _env("SUPPORT_USERNAME", "OverrMaxx").lstrip("@")


def assert_config() -> None:
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not GRIZZLY_API_KEY:
        missing.append("GRIZZLY_API_KEY")
    if not ADMIN_PANEL_PASSWORD:
        missing.append("ADMIN_PANEL_PASSWORD")
    if missing:
        raise SystemExit(
            "Missing required env vars: " + ", ".join(missing) + ". Copy .env.example to .env and fill them in."
        )


def gmail_configured() -> bool:
    return bool(GMAIL_USER and GMAIL_APP_PASSWORD)
