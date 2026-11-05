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
