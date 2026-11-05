"""Keyboards used in the Host-a-New-Bot flow."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="host:cancel",
                    style="danger",
                )
            ]
        ]
    )


def report_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚙️ Continue to Configuration",
                    callback_data="host:configure",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Menu",
                    callback_data="menu:home",
                    style="primary",
                )
            ],
        ]
    )


def collect_kb() -> InlineKeyboardMarkup:
    """Shown while asking for each env variable."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Skip this one",
                    callback_data="host:skip",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="host:cancel",
                    style="danger",
                ),
            ]
        ]
    )


def summary_kb() -> InlineKeyboardMarkup:
    """Shown on the deployment summary screen."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Confirm & Deploy",
                    callback_data="host:deploy",
                    style="success",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Edit a Variable",
                    callback_data="host:edit",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="host:cancel",
                    style="danger",
                ),
            ],
        ]
    )


def deployed_kb() -> InlineKeyboardMarkup:
    """Shown after a deploy attempt (success or failure)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📂 My Bots",
                    callback_data="menu:mybots",
                    style="success",
                ),
                InlineKeyboardButton(
                    text="🏠 Menu",
                    callback_data="menu:home",
                    style="primary",
                ),
            ]
        ]
    )


def retry_kb() -> InlineKeyboardMarkup:
    """Shown when a deploy fails, to let the user go back or home."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📂 My Bots",
                    callback_data="menu:mybots",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="🏠 Menu",
                    callback_data="menu:home",
                    style="primary",
                ),
            ]
        ]
    )


def edit_list_kb(keys: list[str]) -> InlineKeyboardMarkup:
    """One button per variable, so the user can pick which to re-enter."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"✏️ {key}",
                callback_data=f"host:editvar:{key}",
                style="primary",
            )
        ]
        for key in keys
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Back to Summary",
                callback_data="host:summary",
                style="success",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
