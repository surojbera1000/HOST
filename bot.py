"""Entry point. Run with:  python3 bot.py

Starts the web admin panel, background workers, and the Telegram long-polling loop.
"""
import time

import config
import db
import tg
from admin import start_admin_panel
from handlers import handle_update
from workers import start_workers


def _set_commands() -> None:
    try:
        tg.call("setMyCommands", {"commands": [
            {"command": "start", "description": "Open the menu"},
            {"command": "balance", "description": "Show your balance"},
        ]})
    except Exception as e:  # noqa: BLE001
        print("[bot] setMyCommands", e)


def _poll_loop() -> None:
    try:
        tg.call("deleteWebhook", {"drop_pending_updates": False})
    except Exception:  # noqa: BLE001
        pass
    offset = int(db.get_state("tg_offset") or 0)
    print("[bot] long-polling started")
    while True:
        try:
            updates = tg.call("getUpdates", {"offset": offset, "timeout": 50, "allowed_updates": ["message", "callback_query"]})
            for u in updates or []:
                offset = u["update_id"] + 1
                handle_update(u)
            if updates:
                db.set_state("tg_offset", str(offset))
        except Exception as e:  # noqa: BLE001
            print("[bot] poll error", e)
            time.sleep(3)


def main() -> None:
    config.assert_config()
    db.init()
    start_admin_panel()
    start_workers()
    _set_commands()
    _poll_loop()


if __name__ == "__main__":
    main()
