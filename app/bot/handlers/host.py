"""Host a New Bot flow — ask for a repo URL and run the analysis."""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.host import cancel_kb, report_kb
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states import HostBot
from app.bot.texts import (
    ASK_REPO,
    ANALYZING,
    CONFIGURE_SOON,
    INVALID_URL,
    WELCOME,
)
from app.core.logging import get_logger
from app.services.analyzer import analyze_repo
from app.services.github import GitHubError, parse_repo_url

router = Router(name="host")
log = get_logger("host")


@router.callback_query(F.data == "menu:host")
async def start_host(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HostBot.waiting_for_repo)
    await cb.message.edit_text(ASK_REPO, reply_markup=cancel_kb())
    await cb.answer()


@router.callback_query(F.data == "host:cancel")
async def cancel_host(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text(WELCOME, reply_markup=main_menu_kb())
    await cb.answer("Cancelled")


@router.callback_query(F.data == "host:configure")
async def configure(cb: CallbackQuery) -> None:
    await cb.message.edit_text(CONFIGURE_SOON, reply_markup=main_menu_kb())
    await cb.answer()


@router.message(HostBot.waiting_for_repo, F.text)
async def receive_repo(message: Message, state: FSMContext) -> None:
    url = message.text.strip()

    if parse_repo_url(url) is None:
        await message.answer(INVALID_URL, reply_markup=cancel_kb())
        return

    status = await message.answer(ANALYZING)
    try:
        result = await analyze_repo(url)
    except GitHubError as exc:
        await status.edit_text(f"❌ {exc}", reply_markup=cancel_kb())
        return
    except Exception:  # noqa: BLE001 - surface a friendly message, log the rest
        log.exception("analysis_failed", repo=url)
        await status.edit_text(
            "❌ Something went wrong while analyzing the repo. Please try again.",
            reply_markup=cancel_kb(),
        )
        return

    await state.clear()
    await state.update_data(repo_url=url)
    log.info("analysis_done", repo=result.repo_full, env_count=len(result.env_vars))
    await status.edit_text(result.to_report(), reply_markup=report_kb())
