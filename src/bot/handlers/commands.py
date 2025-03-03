import asyncio

from aiogram import Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.bot.states.location import LocationState
from src.bot.keyboards.navigation import get_main_keyboard, get_settings_keyboard, get_location_keyboard
from src.bot.utils.reminders import run_scheduler, update_main_message, log_message
from src.scraping.prayer_times import scrape_prayer_times, fetch_cached_prayer_times
from src.config.settings import LOCATION_MAP, RAMADAN_DATES, DATABASE_PATH
from datetime import datetime, timedelta
import aiosqlite
import logging
import json

logger = logging.getLogger(__name__)


async def start_command(message: types.Message):
    """Handle /start command."""
    chat_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name

    # Save user to database
    await save_user(chat_id, username)

    # Check if user already has a location set
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
        region = await cursor.fetchone()

    # Send welcome message
    welcome_text = "Assalomu alaykum! Islom.uz namoz vaqtlari botiga xush kelibsiz. Shahringizni tanlang:"

    # If user hasn't set a location yet, show location keyboard
    if not region or not region[0]:
        await message.answer(welcome_text, reply_markup=get_location_keyboard())
        privacy_text = "Biz sizning chat ID va username'ingizni xizmat ko'rsatish uchun saqlaymiz."
        await message.answer(privacy_text)
    else:
        # If region is already set, send main message with prayer times
        await message.answer("Assalomu alaykum! Sizning namoz vaqtlaringiz:", reply_markup=get_main_keyboard())
        await send_main_message(message, region[0])


async def save_user(chat_id, username):
    """Save user to database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if user exists
        cursor = await db.execute('SELECT chat_id FROM users WHERE chat_id = ?', (chat_id,))
        user_exists = await cursor.fetchone()

        if user_exists:
            # Update username if user exists
            await db.execute('UPDATE users SET username = ? WHERE chat_id = ?',
                             (username, chat_id))
        else:
            # Insert new user
            await db.execute('INSERT INTO users (chat_id, username) VALUES (?, ?)',
                             (chat_id, username))

        await db.commit()


async def set_location_command(message: types.Message, state: FSMContext):
    """Handle /set_location to ask for user location."""
    await message.answer("Iltimos, shahringizni tanlang:", reply_markup=get_location_keyboard())
    await state.set_state(LocationState.waiting_for_location)


async def handle_location(message: types.Message, state: FSMContext):
    """Handle location input via text."""
    user_input = message.text
    region = LOCATION_MAP.get(user_input)

    if not region:
        await message.answer("Noma'lum shahar! Iltimos, ro'yxatdan shaharni tanlang.",
                             reply_markup=get_location_keyboard())
        return

    # Save user's region
    chat_id = message.chat.id
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('UPDATE users SET region = ? WHERE chat_id = ?', (region, chat_id))
        await db.commit()

    await message.answer(f"Joylashuv {user_input} ga o'rnatildi!", reply_markup=get_main_keyboard())
    await state.clear()
    await send_main_message(message, region)


async def delete_data_command(message: types.Message):
    """Handle /delete_data to remove user data."""
    chat_id = message.chat.id

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
        await db.commit()

    await message.answer("Sizning ma'lumotlaringiz o'chirildi! /start bilan qayta boshlang.")


async def send_main_message(message, region=None, day_type='bugun'):
    """Send or update the main message with prayer times."""
    chat_id = message.chat.id

    # If region is not provided, get it from the database
    if not region:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
            user_data = await cursor.fetchone()
            if not user_data or not user_data[0]:
                await message.answer("Iltimos, avval shahringizni tanlang:",
                                     reply_markup=get_location_keyboard())
                return
            region = user_data[0]

    # Get prayer times for the selected day
    today = datetime.now()

    # Format date for database query
    date_str = today.strftime("%Y-%m-%d") if day_type == 'bugun' else \
        (today + timedelta(days=1)).strftime("%Y-%m-%d")

    # Try to get cached data first
    times = None
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute(
                'SELECT times FROM prayer_times WHERE region = ? AND date = ?',
                (region, date_str)
            )
            data = await cursor.fetchone()
            if data:
                prayer_times = json.loads(data[0])
                times = scrape_prayer_times(region, today.month, day_type)
                if times:
                    times['prayer_times'] = prayer_times
    except Exception as e:
        logger.error(f"Error fetching cached data: {str(e)}")

    # If no cached data, scrape from website
    if not times or 'prayer_times' not in times:
        times = scrape_prayer_times(region, today.month, day_type)

    if not times or 'prayer_times' not in times:
        await message.answer("Namoz vaqtlarini olishda xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return

    # Get current time and determine next prayer
    current_time = datetime.now().strftime("%H:%M")
    next_prayer = None
    next_prayer_time = None

    # Find the next prayer time
    for prayer, time_str in times['prayer_times'].items():
        if time_str != 'N/A' and time_str > current_time:
            if next_prayer is None or time_str < next_prayer_time:
                next_prayer = prayer
                next_prayer_time = time_str

    # If all prayers for today have passed, get first prayer for tomorrow
    if next_prayer is None:
        tomorrow_times = scrape_prayer_times(region, (today + timedelta(days=1)).month, 'erta')
        if tomorrow_times and 'prayer_times' in tomorrow_times:
            # Find the earliest prayer for tomorrow
            for prayer, time_str in sorted(tomorrow_times['prayer_times'].items(), key=lambda x: x[1]):
                if time_str != 'N/A':
                    next_prayer = prayer
                    next_prayer_time = time_str
                    break

    # Calculate time until next prayer
    if next_prayer and next_prayer_time and next_prayer_time != 'N/A':
        # Parse times to calculate time difference
        try:
            next_time = datetime.strptime(next_prayer_time, "%H:%M")
            next_time = datetime.now().replace(
                hour=next_time.hour,
                minute=next_time.minute,
                second=0,
                microsecond=0
            )

            # If next prayer is tomorrow, add a day
            if next_time < datetime.now():
                next_time += timedelta(days=1)

            time_until = next_time - datetime.now()
            hours, remainder = divmod(time_until.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = f"{hours}:{minutes:02d}"
        except Exception as e:
            logger.error(f"Error calculating countdown: {str(e)}")
            countdown = "N/A"
    else:
        countdown = "N/A"

    # Check if we're in Ramadan for special countdown
    today_datetime = datetime.now()
    ramadan_start, ramadan_end = RAMADAN_DATES

    in_ramadan = ramadan_start <= today_datetime <= ramadan_end

    if in_ramadan:
        # Ramadan-specific countdowns
        bomdod_time = times['prayer_times'].get('Bomdod', 'N/A')
        shom_time = times['prayer_times'].get('Shom', 'N/A')

        if bomdod_time != 'N/A' and shom_time != 'N/A':
            try:
                # Convert string times to datetime objects
                bomdod_dt = datetime.strptime(bomdod_time, "%H:%M")
                bomdod_dt = datetime.now().replace(
                    hour=bomdod_dt.hour,
                    minute=bomdod_dt.minute,
                    second=0,
                    microsecond=0
                )

                shom_dt = datetime.strptime(shom_time, "%H:%M")
                shom_dt = datetime.now().replace(
                    hour=shom_dt.hour,
                    minute=shom_dt.minute,
                    second=0,
                    microsecond=0
                )

                # Adjust dates if needed
                current_dt = datetime.now()

                if bomdod_dt < current_dt:
                    bomdod_dt += timedelta(days=1)

                if shom_dt < current_dt:
                    shom_dt += timedelta(days=1)

                # Calculate countdown to iftar (shom) or saharlik (bomdod)
                if current_dt < shom_dt and current_dt > bomdod_dt:
                    # It's daytime, count down to iftar
                    time_until_iftar = shom_dt - current_dt
                    iftar_hours, remainder = divmod(time_until_iftar.seconds, 3600)
                    iftar_minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Iftorlikgacha - {iftar_hours}:{iftar_minutes:02d} qoldi"
                else:
                    # It's nighttime, count down to saharlik
                    time_until_sahar = bomdod_dt - current_dt
                    sahar_hours, remainder = divmod(time_until_sahar.seconds, 3600)
                    sahar_minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Saharlikgacha - {sahar_hours}:{sahar_minutes:02d} qoldi"
            except Exception as e:
                logger.error(f"Error calculating Ramadan countdown: {str(e)}")
                iftar_text = "Vaqtni hisoblashda xatolik"
        else:
            iftar_text = "Saharlik yoki Iftorlik vaqti mavjud emas"
    else:
        iftar_text = f"Keyingi namozgacha - {countdown} qoldi"

    # Build the message text
    message_text = (
        f"📍 {times['location']}\n"
        f"🗓 {times['date']}\n"
        f"☪️ {times['islamic_date']}\n"
        f"------------------------\n"
        f"{iftar_text} ⏰\n"
        f"------------------------\n"
    )

    # Add prayer times table
    for prayer, time_str in times['prayer_times'].items():
        highlight = "**" if prayer == next_prayer else ""
        message_text += f"{prayer}: {highlight}{time_str}{highlight}\n"

    message_text += f"------------------------\n"

    if next_prayer and next_prayer_time and next_prayer_time != 'N/A':
        message_text += (
            f"Keyingi namoz: {next_prayer}\n"
            f"Soat **{next_prayer_time}** da\n"
            f"- {countdown} ⏰qoldi"
        )

    # Send the message
    sent_message = await message.answer(message_text, parse_mode='Markdown')

    # Log the message for future updates
    await log_message(chat_id, sent_message.message_id, day_type)

    # Schedule automatic updates for this message
    await asyncio.create_task(
        update_main_message(
            chat_id,
            sent_message.message_id,
            times,
            next_prayer or "N/A",
            next_prayer_time or "N/A"
        )
    )

    return sent_message


async def today_handler(message: types.Message):
    """Handle 'Bugun' button press."""
    await send_main_message(message, day_type='bugun')


async def tomorrow_handler(message: types.Message):
    """Handle 'Ertaga' button press."""
    await send_main_message(message, day_type='erta')


async def ramadan_calendar_handler(message: types.Message):
    """Handle 'Ramazon taqvimi' button press."""
    # For now, just send a placeholder message
    await message.answer("Ramazon taqvimi hozircha mavjud emas. Tez orada qo'shiladi.")


async def settings_handler(message: types.Message):
    """Handle 'Sozlamalar' button press."""
    await message.answer("Sozlamalar:", reply_markup=get_settings_keyboard())


def register_commands(dp: Dispatcher):
    """Register command handlers with the Dispatcher."""
    dp.message.register(start_command, Command("start"))
    dp.message.register(set_location_command, Command("set_location"))
    dp.message.register(handle_location, LocationState.waiting_for_location, F.text)
    dp.message.register(delete_data_command, Command("delete_data"))

    # Register button handlers
    dp.message.register(today_handler, F.text == "Bugun")
    dp.message.register(tomorrow_handler, F.text == "Ertaga")
    dp.message.register(ramadan_calendar_handler, F.text == "Ramazon taqvimi")
    dp.message.register(settings_handler, F.text == "Sozlamalar")