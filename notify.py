"""Send messages to admin Telegram accounts."""
import config
import tg


def notify_admins(text: str) -> None:
    for admin_id in config.ADMIN_TELEGRAM_IDS:
        try:
            tg.send_message(admin_id, text)
        except Exception as e:  # noqa: BLE001
            print("[notify] admin", admin_id, e)
