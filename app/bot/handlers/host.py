"""Host a New Bot flow.

Phase 2: ask for a repo URL and analyze it.
Phase 3: collect env variables step by step, encrypt them, let the user
review/edit, then confirm and save the bot (ready for the Phase 4 deployer).
"""
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.host import (
    cancel_kb,
    collect_kb,
    deployed_kb,
    edit_list_kb,
    report_kb,
    retry_kb,
    summary_kb,
)
from app.bot.keyboards.main_menu import main_menu_kb
from app.bot.states import HostBot
from app.bot import texts
from app.core.logging import get_logger
from app.core.security import encrypt
from app.db.models import BotStatus, Deployment, EnvVar, HostedBot
from app.services.analyzer import analyze_repo
from app.services.deployer import deploy_bot
from app.services.github import GitHubError, parse_repo_url

router = Router(name="host")
log = get_logger("host")

# Substrings that mark a variable as sensitive (affects the "saved" label only;
# every value is encrypted and every value-message is deleted regardless).
_SENSITIVE_HINTS = (
    "TOKEN", "HASH", "SECRET", "PASSWORD", "PASS", "API_KEY", "APIKEY",
    "SESSION", "KEY", "URI", "URL", "API_ID",
)


def is_sensitive(key: str) -> bool:
    k = key.upper()
    return any(h in k for h in _SENSITIVE_HINTS)


# ----------------------------------------------------------------------------
# Step 1 — ask for the repo URL
# ----------------------------------------------------------------------------
@router.callback_query(F.data == "menu:host")
async def start_host(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(HostBot.waiting_for_repo)
    await cb.message.edit_text(texts.ASK_REPO, reply_markup=cancel_kb())
    await cb.answer()


@router.callback_query(F.data == "host:cancel")
async def cancel_host(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb.message.edit_text(texts.WELCOME, reply_markup=main_menu_kb())
    await cb.answer("Cancelled")


# ----------------------------------------------------------------------------
# Step 2 — analyze the repo
# ----------------------------------------------------------------------------
@router.message(HostBot.waiting_for_repo, F.text)
async def receive_repo(message: Message, state: FSMContext) -> None:
    url = message.text.strip()

    if parse_repo_url(url) is None:
        await message.answer(texts.INVALID_URL, reply_markup=cancel_kb())
        return

    status = await message.answer(texts.ANALYZING)
    try:
        result = await analyze_repo(url)
    except GitHubError as exc:
        await status.edit_text(f"❌ {exc}", reply_markup=cancel_kb())
        return
    except Exception:  # noqa: BLE001
        log.exception("analysis_failed", repo=url)
        await status.edit_text(
            "❌ Something went wrong while analyzing the repo. Please try again.",
            reply_markup=cancel_kb(),
        )
        return

    # Persist the analysis in FSM data for the configuration step.
    await state.set_state(None)
    await state.update_data(
        repo_url=url,
        bot_name=result.repo,
        owner=result.owner,
        repo=result.repo,
        branch=result.branch or "main",
        language=result.language,
        framework=result.framework,
        entrypoint=result.entrypoint,
        startup_cmd=result.startup_cmd,
        env_keys=result.env_vars,
        env_values={},     # key -> encrypted value
        env_skipped=[],     # keys the user chose to skip
        env_index=0,
        # the message we keep editing throughout the flow
        prompt_chat=status.chat.id,
        prompt_msg=status.message_id,
    )
    log.info("analysis_done", repo=result.repo_full, env_count=len(result.env_vars))
    await status.edit_text(result.to_report(), reply_markup=report_kb())


# ----------------------------------------------------------------------------
# Step 3 — collect env variables one by one
# ----------------------------------------------------------------------------
async def _ask_current(cb_or_bot, data: dict) -> None:
    """Edit the tracked message to ask for the current env variable."""
    keys = data["env_keys"]
    idx = data["env_index"]
    key = keys[idx]
    hint = "  🔒" if is_sensitive(key) else ""
    text = texts.ASK_ENV.format(index=idx + 1, total=len(keys), key=key, hint=hint)
    await _edit_tracked(cb_or_bot, data, text, collect_kb())


async def _edit_tracked(bot, data: dict, text: str, kb) -> None:
    await bot.edit_message_text(
        text,
        chat_id=data["prompt_chat"],
        message_id=data["prompt_msg"],
        reply_markup=kb,
    )


def _summary_text(data: dict) -> str:
    keys = data["env_keys"]
    values = data["env_values"]
    skipped = set(data["env_skipped"])
    lines = [
        "📝 <b>Ready to go live!</b>\n",
        f"🤖 <b>Bot:</b> {data['bot_name']}",
        f"📦 <b>Source:</b> <code>{data['owner']}/{data['repo']}</code>",
        f"▶️ <b>Start command:</b> <code>{data.get('startup_cmd') or 'auto'}</code>\n",
        "🔑 <b>Your settings:</b>",
    ]
    if not keys:
        lines.append("<i>None needed.</i>")
    for key in keys:
        if key in values:
            mark = "🔒 set" if is_sensitive(key) else "✅ set"
        elif key in skipped:
            mark = "⏭ skipped"
        else:
            mark = "⬜ not set"
        lines.append(f"  • <code>{key}</code> — {mark}")
    lines.append("\nLooks right? Tap <b>🚀 Confirm &amp; Deploy</b> to launch your bot.")
    return "\n".join(lines)


@router.callback_query(F.data == "host:configure")
async def configure(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    # keep the tracked message pointing at this one
    data["prompt_chat"] = cb.message.chat.id
    data["prompt_msg"] = cb.message.message_id
    await state.update_data(prompt_chat=data["prompt_chat"], prompt_msg=data["prompt_msg"])

    if not data.get("env_keys"):
        await cb.message.edit_text(texts.NO_ENV_DETECTED, reply_markup=summary_kb())
        await cb.answer()
        return

    await state.set_state(HostBot.collecting_env)
    await state.update_data(env_index=0)
    data = await state.get_data()
    await _ask_current(cb.message.bot, data)
    await cb.answer()


@router.message(HostBot.collecting_env, F.text)
async def receive_env_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    keys = data["env_keys"]
    idx = data["env_index"]
    key = keys[idx]
    value = message.text.strip()

    # Store encrypted; never keep plaintext anywhere.
    values = dict(data["env_values"])
    values[key] = encrypt(value)

    # Delete the user's message so the raw value doesn't linger in the chat.
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    idx += 1
    await state.update_data(env_values=values, env_index=idx)
    data = await state.get_data()

    if idx < len(keys):
        await _ask_current(message.bot, data)
    else:
        await state.set_state(None)
        await _edit_tracked(message.bot, data, _summary_text(data), summary_kb())


@router.callback_query(HostBot.collecting_env, F.data == "host:skip")
async def skip_var(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    keys = data["env_keys"]
    idx = data["env_index"]
    key = keys[idx]

    skipped = list(data["env_skipped"])
    skipped.append(key)
    idx += 1
    await state.update_data(env_skipped=skipped, env_index=idx)
    data = await state.get_data()

    if idx < len(keys):
        await _ask_current(cb.message.bot, data)
    else:
        await state.set_state(None)
        await cb.message.edit_text(_summary_text(data), reply_markup=summary_kb())
    await cb.answer("Skipped")


# ----------------------------------------------------------------------------
# Step 4 — review / edit
# ----------------------------------------------------------------------------
@router.callback_query(F.data == "host:summary")
async def show_summary(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    data = await state.get_data()
    await cb.message.edit_text(_summary_text(data), reply_markup=summary_kb())
    await cb.answer()


@router.callback_query(F.data == "host:edit")
async def edit_menu(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    keys = data.get("env_keys", [])
    if not keys:
        await cb.answer("Nothing to edit", show_alert=True)
        return
    await cb.message.edit_text(texts.EDIT_INTRO, reply_markup=edit_list_kb(keys))
    await cb.answer()


@router.callback_query(F.data.startswith("host:editvar:"))
async def edit_var(cb: CallbackQuery, state: FSMContext) -> None:
    key = cb.data.split("host:editvar:", 1)[1]
    await state.update_data(
        editing_key=key,
        prompt_chat=cb.message.chat.id,
        prompt_msg=cb.message.message_id,
    )
    await state.set_state(HostBot.editing_env)
    await cb.message.edit_text(texts.EDIT_ASK.format(key=key), reply_markup=cancel_kb())
    await cb.answer()


@router.message(HostBot.editing_env, F.text)
async def receive_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data["editing_key"]
    value = message.text.strip()

    values = dict(data["env_values"])
    values[key] = encrypt(value)
    # if it was previously skipped, un-skip it
    skipped = [k for k in data["env_skipped"] if k != key]

    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass

    await state.update_data(env_values=values, env_skipped=skipped)
    await state.set_state(None)
    data = await state.get_data()
    await _edit_tracked(message.bot, data, _summary_text(data), summary_kb())


# ----------------------------------------------------------------------------
# Step 5 — confirm & save (deployment engine lands in Phase 4)
# ----------------------------------------------------------------------------
@router.callback_query(F.data == "host:deploy")
async def deploy(cb: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    env_encrypted = data.get("env_values", {})

    env_vars = [
        EnvVar(key=key, value_encrypted=enc, is_sensitive=is_sensitive(key))
        for key, enc in env_encrypted.items()
    ]
    bot = HostedBot(
        owner_id=cb.from_user.id,
        name=data.get("bot_name", "Untitled Bot"),
        repo_url=data.get("repo_url"),
        branch=data.get("branch", "main"),
        language=data.get("language"),
        framework=data.get("framework"),
        entrypoint=data.get("entrypoint"),
        startup_cmd=data.get("startup_cmd"),
        env_vars=env_vars,
        status=BotStatus.DEPLOYING,
    )
    await bot.insert()
    log.info("bot_saved", owner=cb.from_user.id, repo=data.get("repo_url"), vars=len(env_vars))

    await state.clear()
    await cb.answer("Deploying…")
    await cb.message.edit_text(texts.DEPLOYING)

    deployment = Deployment(bot_id=str(bot.id), status=BotStatus.DEPLOYING)
    await deployment.insert()

    # Run the actual container deployment (clone -> install -> start).
    result = await deploy_bot(
        bot_id=str(bot.id),
        repo_url=bot.repo_url or "",
        branch=bot.branch,
        startup_cmd=bot.startup_cmd or "python main.py",
        env_encrypted=env_encrypted,
    )

    # Persist the outcome.
    from datetime import datetime, timezone
    deployment.logs = result.logs
    deployment.finished_at = datetime.now(timezone.utc)

    if result.success:
        bot.status = BotStatus.RUNNING
        bot.container_id = result.container_id
        deployment.status = BotStatus.RUNNING
        await bot.save()
        await deployment.save()
        await cb.message.edit_text(
            texts.DEPLOY_SUCCESS.format(name=bot.name),
            reply_markup=deployed_kb(),
        )
    elif result.status == "failed":
        bot.status = BotStatus.FAILED
        bot.container_id = result.container_id
        deployment.status = BotStatus.FAILED
        deployment.error_summary = result.error
        await bot.save()
        await deployment.save()
        import html
        logs_tail = html.escape((result.logs or "")[-1200:] or "(no output)")
        await cb.message.edit_text(
            texts.DEPLOY_FAILED.format(
                name=bot.name,
                reason=result.error or "The bot exited unexpectedly.",
                logs=logs_tail,
            ),
            reply_markup=retry_kb(),
        )
    else:  # "error" — infrastructure problem
        bot.status = BotStatus.FAILED
        deployment.status = BotStatus.FAILED
        deployment.error_summary = result.error
        await bot.save()
        await deployment.save()
        await cb.message.edit_text(
            texts.DEPLOY_ERROR.format(reason=result.error or "Unknown error."),
            reply_markup=retry_kb(),
        )
