"""Register all handler routers in one place."""
from aiogram import Dispatcher

from app.bot.handlers import admin, host, menu, start


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(host.router)
    dp.include_router(menu.router)
    dp.include_router(admin.router)
