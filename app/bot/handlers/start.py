"""/start — ইউজার রেজিস্টার + main menu দেখানো।"""
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.texts import WELCOME
from app.db.models import User

router = Router(name="start")


async def ensure_user(message: Message) -> User:
    """ইউজার না থাকলে database-এ তৈরি করা হয়।"""
    tg = message.from_user
    user = await User.find_one(User.telegram_id == tg.id)
    if user is None:
        user = User(
            telegram_id=tg.id,
            username=tg.username,
            full_name=tg.full_name,
        )
        await user.insert()
    return user


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await ensure_user(message)
    await message.answer(WELCOME, reply_markup=main_menu_kb())
