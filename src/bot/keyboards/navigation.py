from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton


def get_navigation_keyboard():
    """Build navigation keyboard for prayer times."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Yesterday", callback_data="yesterday"),
        InlineKeyboardButton(text="Today", callback_data="today"),
        InlineKeyboardButton(text="Tomorrow ➡️", callback_data="tomorrow")
    )
    builder.row(
        InlineKeyboardButton(text="Full Times", callback_data="full_times"),
        InlineKeyboardButton(text="Toggle Reminders", callback_data="toggle_reminders")
    )
    return builder.as_markup()