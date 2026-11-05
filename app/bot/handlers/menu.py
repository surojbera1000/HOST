"""Main menu-র inline button callback handler।"""
from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.main_menu import back_kb, main_menu_kb
from app.bot import texts
from app.db.models import BotStatus, HostedBot

router = Router(name="menu")


@router.callback_query(F.data == "menu:home")
async def go_home(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.WELCOME, reply_markup=main_menu_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:host")
async def host_new(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.HOST_NEW, reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:mybots")
async def my_bots(cb: CallbackQuery) -> None:
    bots = await HostedBot.find(HostedBot.owner_id == cb.from_user.id).to_list()
    if not bots:
        await cb.message.edit_text(texts.MY_BOTS_EMPTY, reply_markup=back_kb())
    else:
        lines = ["📂 <b>আপনার Hosted Bots</b>\n"]
        for b in bots:
            icon = "🟢" if b.status == BotStatus.RUNNING else "⏹"
            lines.append(f"{icon} <b>{b.name}</b> — {b.status.value}")
        await cb.message.edit_text("\n".join(lines), reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:stats")
async def stats(cb: CallbackQuery) -> None:
    bots = await HostedBot.find(HostedBot.owner_id == cb.from_user.id).to_list()
    total = len(bots)
    running = sum(1 for b in bots if b.status == BotStatus.RUNNING)
    stopped = total - running
    await cb.message.edit_text(
        texts.STATS.format(total=total, running=running, stopped=stopped),
        reply_markup=back_kb(),
    )
    await cb.answer()


@router.callback_query(F.data == "menu:github")
async def github_auth(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.GITHUB_AUTH, reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:docs")
async def docs(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.DOCS, reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:plans")
async def plans(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.PLANS, reply_markup=back_kb())
    await cb.answer()


@router.callback_query(F.data == "menu:support")
async def support(cb: CallbackQuery) -> None:
    await cb.message.edit_text(texts.SUPPORT, reply_markup=back_kb())
    await cb.answer()
