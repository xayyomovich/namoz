from aiogram.fsm.state import State, StatesGroup
from aiogram import Dispatcher


class LocationState(StatesGroup):
    waiting_for_location = State()


def register_states(dp: Dispatcher):
    """Register FSM states with the Dispatcher."""
    # No additional registration needed for states in aiogram 3.x, as states are automatically available
    # This function can be empty or used for future state-related setup
    pass