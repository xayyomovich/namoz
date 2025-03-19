import asyncio

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext

from src.bot.keyboards.navigation import get_main_keyboard, get_settings_keyboard, get_location_keyboard
from src.bot.utils.calculations import get_ramadan_countdown
from src.bot.utils.reminders import update_main_message, log_message, calculate_islamic_date
from src.scraping.prayer_times import fetch_cached_prayer_times
from src.config.settings import DATABASE_PATH
from datetime import datetime, timedelta
import aiosqlite
import logging
from aiogram.types import FSInputFile
from src.config.ramadan_images import RAMADAN_IMAGES
import os

logger = logging.getLogger(__name__)


async def start_command(message: types.Message, state: FSMContext):
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
    welcome_text = ("Assalomu alaykum! Namoz vaqtlari botiga xush kelibsiz🎉\n"
                    "Bot orqali siz namoz vaqtlaridan boxabar bo'lib turishingiz mumkin 🔔")

    # If user hasn't set a location yet, show location keyboard
    if not region or not region[0]:
        # No location set, prompt with inline keyboard
        await message.answer(welcome_text)
        await message.answer("Iltimos, shahringizni tanlang", reply_markup=get_location_keyboard())
    else:
        # Location set, show main menu with prayer times
        await message.answer(welcome_text, reply_markup=get_main_keyboard())
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


async def set_location_command(message: types.Message):
    """Handle /set_location to ask for user location via inline keyboard."""
    await message.answer("Iltimos, shahringizni tanlang", reply_markup=get_location_keyboard())


PRAYER_EMOJIS = {
    'Bomdod': '🌅',
    'Quyosh': '☀️',
    'Peshin': '🌞',
    'Asr': '🌆',
    'Shom': '🌙',
    'Xufton': '⭐'
}


async def send_main_message(message, region=None, day_type='bugun'):
    """Send or update the main message with prayer times."""
    global closest_prayer
    chat_id = message.chat.id

    # Check if region is provided; if not, fetch it from the database
    if not region:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
            user_data = await cursor.fetchone()
            if not user_data or not user_data[0]:
                # Prompt user for location if no region is found
                await set_location_command(message)
                return
            region = user_data[0]

    # Set the current date and determine the target date based on day_type
    today = datetime.now()
    date_str = today.strftime("%Y-%m-%d") if day_type == 'bugun' else \
        (today + timedelta(days=1)).strftime("%Y-%m-%d")

    # Fetch cached prayer times for the specified region and date
    times = await fetch_cached_prayer_times(region, date_str)
    if not times:
        # Notify user if prayer times are unavailable
        await message.answer("Namoz vaqtlari mavjud emas yoki keshda xatolik.")
        return

    # Get current time for comparison with prayer times
    current_time = datetime.now().strftime("%H:%M")
    next_prayer = None
    next_prayer_time = None

    # Find the next prayer time from today's data
    for prayer, time_str in times['prayer_times'].items():  # Access nested prayer_times from cached data
        if time_str != 'N/A' and time_str > current_time:
            if next_prayer is None or time_str < next_prayer_time:
                next_prayer = prayer
                next_prayer_time = time_str

    # If all prayers for today have passed, get tomorrow's first prayer from cache
    if next_prayer is None:
        tomorrow_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times:
            for prayer, time_str in sorted(tomorrow_times['prayer_times'].items(),
                                           key=lambda x: x[1]):  # Sort to get earliest
                if time_str != 'N/A':
                    next_prayer = prayer
                    next_prayer_time = time_str
                    break

    # Calculate time until next prayer (countdown) for 'bugun' only
    countdown = "N/A"
    if day_type == 'bugun' and next_prayer and next_prayer_time != 'N/A':
        try:
            next_time = datetime.strptime(next_prayer_time, "%H:%M")
            next_time = datetime.now().replace(
                hour=next_time.hour,
                minute=next_time.minute,
                second=0,
                microsecond=0
            )
            if next_time < datetime.now():
                # Adjust to tomorrow if next prayer time has passed today
                next_time += timedelta(days=1)
            time_until = next_time - datetime.now()
            hours, remainder = divmod(time_until.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = f"{hours}:{minutes:02d}"
        except Exception as e:
            logger.error(f"Error calculating countdown: {str(e)}")

    # Calculate Islamic (Hijri) date from the Gregorian date
    islamic_date = await calculate_islamic_date(date_str)

    # Use the new function for Ramadan countdown
    iftar_text = None
    if day_type == 'bugun':
        now = datetime.now()
        iftar_text = get_ramadan_countdown(now, times, countdown)

    # Start building the message with location, date, and Islamic date
    message_text = (
        f"📍 {times['location']}\n"
        f"🗓 {times['date']}\n"
        f"☪️ {islamic_date}\n"
        f"------------------------\n"
    )
    if day_type == 'bugun':
        # Add countdown text only for today
        message_text += f"{iftar_text} ⏰\n"
    message_text += f"------------------------\n"

    # Add prayer times table with emojis, bold, and tick for 'bugun', or just list for 'erta'
    if day_type == 'bugun':
        # Find the closest (exact) prayer time to now
        closest_prayer = None
        min_time_diff = None
        for prayer, time_str in times['prayer_times'].items():
            if time_str != 'N/A':
                prayer_minutes = int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])
                current_minutes = int(current_time.split(':')[0]) * 60 + int(current_time.split(':')[1])
                time_diff = prayer_minutes - current_minutes
                if (min_time_diff is None or
                        (time_diff <= 0 and (min_time_diff > 0 or time_diff > min_time_diff)) or
                        (time_diff > 0 and time_diff < min_time_diff)):
                    closest_prayer = prayer
                    min_time_diff = time_diff

        # Build prayer list with emojis, bolding exact time, and adding tick
        for prayer, time_str in times['prayer_times'].items():
            emoji = PRAYER_EMOJIS.get(prayer, '⏰')
            tick = " ✅" if prayer == closest_prayer else ""
            message_text += f"{emoji} {prayer}: {time_str}{tick}\n"
    else:  # 'erta'
        # Build simple prayer list with emojis for tomorrow
        for prayer, time_str in times['prayer_times'].items():
            emoji = PRAYER_EMOJIS.get(prayer, '⏰')
            message_text += f"{emoji} {prayer}: {time_str}\n"

    message_text += f"------------------------\n"

    # Add next prayer countdown only for 'bugun'
    if day_type == 'bugun' and next_prayer and next_prayer_time != 'N/A':
        message_text += (
            f"{next_prayer} gacha\n"
            f"- {countdown} ⏰qoldi"
        )
    elif day_type == 'bugun' and closest_prayer == "Xufton" and (not next_prayer or next_prayer_time == 'N/A'):
        # All prayers for today have passed (Xufton is the closest and no next prayer)
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times:
            # Get Bomdod time for tomorrow
            bomdod_time = tomorrow_times['prayer_times'].get('Bomdod', 'N/A')
            if bomdod_time != 'N/A':
                try:
                    next_time = datetime.strptime(bomdod_time, "%H:%M")
                    next_time = datetime.now().replace(
                        hour=next_time.hour,
                        minute=next_time.minute,
                        second=0,
                        microsecond=0
                    ) + timedelta(days=1)  # Set to tomorrow
                    time_until = next_time - datetime.now()
                    hours, remainder = divmod(time_until.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    countdown = f"{hours}:{minutes:02d}"
                    message_text += (
                        f"Bomdod gacha\n"
                        f"- {countdown} ⏰qoldi"
                    )
                except Exception as e:
                    logger.error(f"Error calculating countdown to tomorrow's Bomdod: {str(e)}")


    # Send the formatted message with Markdown parsing for bold
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
            next_prayer_time or "N/A",
            islamic_date

        )
    )
    return sent_message


async def today_handler(message: types.Message):
    """Handle 'Bugun' button press."""
    await send_main_message(message, day_type='bugun')


async def tomorrow_handler(message: types.Message):
    """Handle 'Ertaga' button press."""
    await send_main_message(message, day_type='erta')


async def settings_handler(message: types.Message):
    """Handle 'Sozlamalar' button press."""
    await message.answer("Sozlamalar ⚙️", reply_markup=get_settings_keyboard())
    # await settings_callback(message, reply_markup=get_settings_keyboard())


async def ramadan_calendar_handler(message: types.Message):
    """Handle 'Ramazon taqvimi' button press and display a Ramadan image from static files."""
    try:
        image_config = RAMADAN_IMAGES.get("default")
        if not image_config:
            await message.answer("Ramazon taqvimi uchun rasm topilmadi.")
            return

        image_path = os.path.join("src/static/ramadan", image_config["filename"])
        if os.path.exists(image_path):
            photo = FSInputFile(image_path)  # Use FSInputFile instead of opening directly
            await message.answer_photo(photo, caption=image_config["description"])
        else:
            await message.answer("Rasm fayli topilmadi. Iltimos, rasmni tekshiring.")
    except Exception as e:
        logger.error(f"Error displaying Ramadan image: {e}")
        await message.answer("Xatolik yuz berdi, rasmni ko'rsatishda muammo bor.")


def register_commands(dp: Dispatcher):
    """Register command handlers with the Dispatcher."""
    dp.message.register(start_command, F.text == "/start")
    dp.message.register(set_location_command, F.text == "/set_location")

    # Register button handlers
    dp.message.register(today_handler, F.text == "Bugun")
    dp.message.register(tomorrow_handler, F.text == "Ertaga")
    dp.message.register(ramadan_calendar_handler, F.text == "Ramazon taqvimi")
    dp.message.register(settings_handler, F.text == "Sozlamalar")






