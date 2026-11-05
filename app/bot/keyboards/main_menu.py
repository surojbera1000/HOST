"""Inline keyboards — রঙিন emoji সহ main menu ও navigation।"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Host a New Bot", callback_data="menu:host")
    kb.button(text="📂 My Hosted Bots", callback_data="menu:mybots")
    kb.button(text="📊 Hosting Statistics", callback_data="menu:stats")
    kb.button(text="🔗 GitHub Authentication", callback_data="menu:github")
    kb.button(text="📖 Documentation", callback_data="menu:docs")
    kb.button(text="💎 Plans & Pricing", callback_data="menu:plans")
    kb.button(text="🆘 Support", callback_data="menu:support")
    # layout: 2,2,2,1
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:home")]
        ]
    )
