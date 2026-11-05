"""Application entry point — bot চালু করে।

চালানো: python -m app.main
"""
import asyncio

from app.bot.handlers import register_handlers
from app.bot.loader import bot, dp
from app.core.logging import configure_logging, get_logger
from app.db.mongo import close_db, init_db

log = get_logger("main")


async def main() -> None:
    configure_logging()
    log.info("starting_platform")

    # 1) Database
    await init_db()

    # 2) Handlers রেজিস্টার
    register_handlers(dp)

    # 3) Polling শুরু
    log.info("bot_polling_started")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await close_db()
        await bot.session.close()
        log.info("shutdown_complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
