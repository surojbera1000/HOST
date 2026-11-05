"""FSM state groups for multi-step Telegram conversations."""
from aiogram.fsm.state import State, StatesGroup


class HostBot(StatesGroup):
    waiting_for_repo = State()   # Phase 2: waiting for the GitHub repo URL
    collecting_env = State()     # Phase 3: asking for env variables one by one
    editing_env = State()        # Phase 3: re-entering a single variable's value
