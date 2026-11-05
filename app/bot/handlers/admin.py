"""/admin — basic admin panel for OWNER_ID only."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot import texts
from app.config import get_settings
from app.db.models import BotStatus, HostedBot, User

router = Router(name="admin")
settings = get_settings()


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if message.from_user.id != settings.owner_id:
        await message.answer(texts.NOT_ADMIN)
        return

    users = await User.count()
    bots = await HostedBot.find_all().to_list()
    running = sum(1 for b in bots if b.status == BotStatus.RUNNING)
    failed = sum(1 for b in bots if b.status == BotStatus.FAILED)

    await message.answer(
        texts.ADMIN_PANEL.format(
            users=users, bots=len(bots), running=running, failed=failed
        )
    )
