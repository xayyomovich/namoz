from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.bot.states.location import LocationState
from src.bot.keyboards.navigation import get_navigation_keyboard
from src.bot.utils import reminders
from src.bot.utils.reminders import schedule_reminders
from src.scraping.prayer_times import scrape_prayer_times
from datetime import datetime


async def start_command(message: types.Message):
    """Handle /start command (green interface)."""
    chat_id = message.chat.id
    # Call scrape_prayer_times synchronously, not with await
    times = scrape_prayer_times(chat_id)

    if not times:
        await message.answer("Error fetching prayer times. Try again later.")
        return

    # Get current time to determine next prayer
    current_time = datetime.now().strftime("%H:%M")
    next_prayer = None
    next_time = None

    for prayer, time in times['prayer_times'].items():
        if time > current_time:
            next_prayer = prayer
            next_time = time
            break
    if not next_prayer:  # If no future prayer today, use tomorrow's Fajr
        times_erta = scrape_prayer_times(chat_id, day_type='erta')
        if not times_erta:
            await message.answer("Error fetching tomorrow's prayer times.")
            return
        next_prayer = 'Bomdod'
        next_time = times_erta['prayer_times']['Bomdod']

    # Format message like the green interface
    current_time_str = datetime.now().strftime("%I:%M %p")  # e.g., "4:46 AM"
    message_text = (
        f"🕌 *Namoaz vaqtlari*\n"
        f"👉 {times['date']} 👈\n"
        f"{times['islamic_date']}\n"
        f"*{current_time_str}* ⏰\n"
        f"*{next_prayer}*, {next_time} 🔔"
    )
    await message.answer(message_text, parse_mode='Markdown')
    await message.answer("Navigate or view options:", reply_markup=get_navigation_keyboard())


async def set_location_command(message: types.Message, state: FSMContext):
    """Handle /set_location to ask for user location."""
    await message.answer("Please enter your city (e.g., Tashkent) or region code (e.g., 27):")
    await state.set_state(LocationState.waiting_for_location)


async def handle_location(message: types.Message, state: FSMContext):
    """Handle location input."""
    user_input = message.text
    from src.config.settings import LOCATION_MAP
    region = LOCATION_MAP.get(user_input, user_input)  # Try to match city or use as region code
    await state.update_data(region=region)
    await message.answer(f"Location set to {user_input}! Use /start to see prayer times.")
    await state.clear()


async def toggle_reminder_command(message: types.Message):
    """Toggle reminders for a specific prayer."""
    chat_id = message.chat.id
    if not message.text.split()[1:]:
        await message.answer("Usage: /toggle_reminder [prayer]\nE.g., /toggle_reminder Bomdod")
        return

    prayer = message.text.split()[1].capitalize()
    if prayer not in ['Bomdod', 'Quyosh', 'Peshin', 'Asr', 'Shom', 'Xufton']:
        await message.answer("Invalid prayer name!")
        return

    reminders.setdefault(chat_id, {})[prayer] = not reminders.get(chat_id, {}).get(prayer, False)
    status = "enabled" if reminders[chat_id][prayer] else "disabled"
    await message.answer(f"Reminders for {prayer} {status}! 🔔🔕")


def register_commands(dp: Dispatcher):
    dp.message.register(start_command, Command("start"))
    dp.message.register(set_location_command, Command("set_location"))
    dp.message.register(handle_location, LocationState.waiting_for_location, F.text)
    dp.message.register(toggle_reminder_command, Command("toggle_reminder"))