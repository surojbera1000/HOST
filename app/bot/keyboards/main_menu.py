"""Inline keyboards — colourful styled main menu and navigation.

Button colours use the Bot API 9.4 ``style`` field:
  - "primary" -> blue
  - "success" -> green
  - "danger"  -> red
Older Telegram clients simply ignore the style and show default buttons.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Host a New Bot",
                    callback_data="menu:host",
                    style="success",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📂 My Hosted Bots",
                    callback_data="menu:mybots",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="📊 Statistics",
                    callback_data="menu:stats",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔗 GitHub Auth",
                    callback_data="menu:github",
                    style="primary",
                ),
                InlineKeyboardButton(
                    text="📖 Documentation",
                    callback_data="menu:docs",
                    style="primary",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💎 Plans & Pricing",
                    callback_data="menu:plans",
                    style="success",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🆘 Support",
                    callback_data="menu:support",
                    style="danger",
                ),
            ],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Back to Menu",
                    callback_data="menu:home",
                    style="primary",
                )
            ]
        ]
    )
