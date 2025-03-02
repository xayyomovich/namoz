from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.bot.states.location import LocationState
from src.bot.keyboards.navigation import get_main_keyboard, get_settings_keyboard, get_location_keyboard
from src.bot.utils.reminders import schedule_reminders, update_main_message
from src.scraping.prayer_times import scrape_prayer_times
from src.config.settings import LOCATION_MAP, RAMADAN_2025, DATABASE_PATH
from datetime import datetime, timedelta
import aiosqlite
import logging

logger = logging.getLogger(__name__)


async def start_command(message: types.Message):
    """Handle /start command."""
    chat_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name
    await save_user(chat_id, username)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
        region = await cursor.fetchone()

    welcome_text = "Assalomu alaykum! Welcome to Islom.uz Prayer Times Bot. Get daily prayer times and Ramadan calendar based on your location. Choose your city:"
    await message.answer(welcome_text, reply_markup=get_location_keyboard())
    privacy_text = "Biz sizning chat ID va username'ingizni olamiz."
    await message.answer(privacy_text, reply_markup=get_main_keyboard())

    # If region is set, send main message immediately
    if region:
        await send_main_message(message, region[0])  # Pass the region value


async def save_user(chat_id, username):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Optional: Verify table existence for debugging
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = await cursor.fetchone()
        if not table_exists:
            print(f"Error: 'users' table does not exist in {DATABASE_PATH}")
            raise Exception("Users table not found!")

        await db.execute(
            'INSERT OR REPLACE INTO users (chat_id, username) VALUES (?, ?) '
            'ON CONFLICT(chat_id) DO UPDATE SET username = ?',
            (chat_id, username, username)
        )
        await db.commit()


async def set_location_command(message: types.Message, state: FSMContext):
    """Handle /set_location to ask for user location."""
    await message.answer("Iltimos, shahringizni tanlang (masalan, Тошкент):", reply_markup=get_location_keyboard())
    await state.set_state(LocationState.waiting_for_location)


async def handle_location(message: types.Message, state: FSMContext):
    """Handle location input via callback or text."""
    user_input = message.text
    region = LOCATION_MAP.get(user_input)
    if not region:
        await message.answer("Noma’lum shahar! Iltimos, ro‘yxatdan shaharni tanlang.", reply_markup=get_location_keyboard())
        return
    await state.update_data(region=region)
    await message.answer(f"Joylashuv {user_input} ga o‘rnatildi!", reply_markup=get_main_keyboard())
    await state.clear()
    await send_main_message(message)


async def delete_data_command(message: types.Message):
    """Handle /delete_data to remove user data."""
    chat_id = message.chat.id
    async with aiosqlite.connect('src/database/prayer_times.db') as db:
        await db.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
        await db.commit()
    await message.answer("Sizning ma’lumotlaringiz o‘chirildi! /start bilan qayta boshlang.", reply_markup=get_main_keyboard())


async def send_main_message(message, region, day_type='bugun'):
    """Send or update the main message with prayer times."""
    chat_id = message.chat.id
    times = scrape_prayer_times(region, datetime.now().month, day_type)
    if not times or not times['prayer_times']:
        await message.answer("Namoz vaqtlarini olishda xatolik yuz berdi. Keyinroq urinib ko‘ring.")
        return

    current_time = datetime.now().strftime("%I:%M %p")
    next_prayer_time = min((t for t in times['prayer_times'].values() if t != 'N/A' and t > current_time), default=None)
    if not next_prayer_time:
        times_erta = scrape_prayer_times(region, datetime.now().month, 'erta')
        if times_erta and times_erta['prayer_times'].get('Bomdod'):
            next_prayer = 'Bomdod'
            next_prayer_time = times_erta['prayer_times']['Bomdod']
        else:
            next_prayer = 'Bomdod'
            next_prayer_time = 'N/A'
    else:
        next_prayer = [p for p, t in times['prayer_times'].items() if t == next_prayer_time and t != 'N/A'][0]

    time_until = datetime.strptime(next_prayer_time, "%H:%M") - datetime.strptime(current_time, "%I:%M %p") if next_prayer_time != 'N/A' else timedelta(0)
    if time_until.total_seconds() < 0 and next_prayer != 'Bomdod' and next_prayer_time != 'N/A':
        times_erta = scrape_prayer_times(region, datetime.now().month, 'erta')
        if times_erta and times_erta['prayer_times'].get('Bomdod'):
            next_prayer = 'Bomdod'
            next_prayer_time = times_erta['prayer_times']['Bomdod']
        else:
            next_prayer_time = 'N/A'
        time_until = datetime.strptime(next_prayer_time, "%H:%M") - datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1) if next_prayer_time != 'N/A' else timedelta(0)

    minutes, seconds = divmod(abs(time_until.total_seconds()), 60)
    hours, minutes = divmod(minutes, 60)
    countdown = f"{int(hours)}:{int(minutes):02d}" if hours > 0 else f"{int(minutes):02d}:{int(seconds):02d}"

    if datetime.now() in RAMADAN_2025:  # Updated to RAMADAN_DATES
        bomdod_time = times['prayer_times'].get('Bomdod', 'N/A')
        shom_time = times['prayer_times'].get('Shom', 'N/A')
        if bomdod_time != 'N/A' and shom_time != 'N/A':
            bomdod_dt = datetime.strptime(bomdod_time, "%H:%M")
            shom_dt = datetime.strptime(shom_time, "%H:%M")
            current_dt = datetime.now().replace(second=0, microsecond=0)
            next_bomdod_dt = bomdod_dt + timedelta(days=1) if current_dt > bomdod_dt else bomdod_dt

            if current_dt < shom_dt:
                time_until_iftar = shom_dt - current_dt
                iftar_text = f"Iftorlikgacha - {int(time_until_iftar.total_seconds() // 3600)}:{int((time_until_iftar.total_seconds() % 3600) // 60):02d} qoldi"
            else:
                time_until_sahar = next_bomdod_dt - current_dt
                iftar_text = f"Saharlikgacha - {int(time_until_sahar.total_seconds() // 3600)}:{int((time_until_sahar.total_seconds() % 3600) // 60):02d} qoldi"
        else:
            iftar_text = "Saharlik yoki Iftorlik vaqti mavjud emas"
    else:
        iftar_text = f"Keyingi namozgacha - {countdown} qoldi"

    message_text = (
        f"📍 {times['location']}\n"
        f"🗓 {times['date']}\n"
        f"☪️ {times['islamic_date']}\n"
        f"------------------------\n"
        f"{iftar_text} ⏰\n"
        f"------------------------\n"
        f"{next_prayer} vaqti\n"
        f"**{next_prayer_time} да**\n"
        f"- {countdown} qoldi ⏰\n"
        f"------------------------"
    )
    sent_message = await message.answer(message_text, parse_mode='Markdown')
    await update_main_message(chat_id, sent_message.message_id, times, next_prayer, next_prayer_time)  # Pass full times dict


def register_commands(dp: Dispatcher):
    """Register command handlers with the Dispatcher."""
    dp.message.register(start_command, Command("start"))
    dp.message.register(set_location_command, Command("set_location"))
    dp.message.register(handle_location, LocationState.waiting_for_location, F.text)
    dp.message.register(delete_data_command, Command("delete_data"))