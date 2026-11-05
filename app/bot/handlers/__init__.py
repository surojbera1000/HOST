"""সব handler router এক জায়গায় রেজিস্টার করা হয়।"""
from aiogram import Dispatcher

from app.bot.handlers import admin, menu, start


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(admin.router)
