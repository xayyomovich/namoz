from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher


class LocationState(StatesGroup):
    waiting_for_location = State()


def register_states(dp: Dispatcher):
    """Register FSM states (optional in aiogram 3.x, but kept for structure)."""
    pass