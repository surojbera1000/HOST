"""FSM state groups for multi-step Telegram conversations."""
from aiogram.fsm.state import State, StatesGroup


class HostBot(StatesGroup):
    waiting_for_repo = State()   # Phase 2: waiting for the GitHub repo URL
