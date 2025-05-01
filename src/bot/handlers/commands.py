import asyncio
from aiogram import Dispatcher, types, F, Router
from aiogram.exceptions import TelegramForbiddenError

from src.bot.keyboards.navigation import get_main_keyboard, get_settings_keyboard, get_location_keyboard
from src.bot.utils.calculations import calculate_exact_prayer, calculate_next_prayer_countdown
from src.bot.utils.reminders import update_main_message, log_message, calculate_islamic_date
from src.config.constants import PRAYER_EMOJIS
from src.db.pooling import facke_pooling
from src.scraping.prayer_times import fetch_cached_prayer_times
from datetime import datetime, timedelta
from src.config.log_config import logger

router = Router()


async def start_command(message: types.Message):
    """Handle /start command."""
    chat_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name

    # Save user to database
    await save_user(chat_id, username)

    # Check if user already has a location set
    region = await facke_pooling.fetchone('SELECT region FROM users WHERE chat_id = ?', (chat_id,))

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


async def set_location_command(message: types.Message):
    """Handle /set_location to ask for user location via inline keyboard."""
    await message.answer("Iltimos, shahringizni tanlang", reply_markup=get_location_keyboard())


async def save_user(chat_id, username):
    """Save user to database."""
    try:
        # Check if user exists
        user_exists = await facke_pooling.fetchone('SELECT chat_id FROM users WHERE chat_id = ?', (chat_id,))

        if user_exists:
            # Update username if user exists
            await facke_pooling.execute('UPDATE users SET username = ? WHERE chat_id = ?',
                        (username, chat_id))
        else:
            # Insert new user
            await facke_pooling.execute('INSERT INTO users (chat_id, username) VALUES (?, ?)',
                            (chat_id, username))
    except Exception as e:
        logger.error(f"Error saving user {chat_id}: {e}")
        raise


async def send_main_message(message, region=None, day_type='bugun'):
    """Send or update the main message with prayer times."""
    chat_id = message.chat.id

    try:
        # Check if region is provided; if not, fetch it from the database
        if not region:
            user_data = await facke_pooling.fetchone('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
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

        # Calculate Islamic (Hijri) date from the Gregorian date
        islamic_date = await calculate_islamic_date(date_str)

        # Start building the message with location, date, and Islamic date
        message_text = (
            f"📍 {times['location']}\n"
            f"🗓 {times['date']}\n"
            f"☪️ {islamic_date}\n"
            f"<code>-----------------</code>\n"
        )

        # Add prayer times table with emojis, bold, and tick for 'bugun', or just list for 'erta'
        if day_type == 'bugun':
            # Find the exact prayer time to now
            exact_prayer = await calculate_exact_prayer(times['prayer_times'], current_time, date_str)
            # print(f"=-=-=-={exact_prayer}=-=-=-=-")
            # print(f"=-=-=-={current_time}=-=-=-=-")
            # Build prayer list with emojis, bolding exact time, and adding tick
            for prayer, time_str in times['prayer_times'].items():
                emoji = PRAYER_EMOJIS.get(prayer, '⏰')
                if prayer == exact_prayer:
                    # Use blockquote with bold for the closest prayer
                    message_text += f"<blockquote><b>{emoji} {prayer}: {time_str}</b>      </blockquote>\n"
                else:
                    # Regular formatting for other prayers
                    message_text += f"{emoji} {prayer}: {time_str}\n"
        else:  # 'erta'
            # Build simple prayer list with emojis for tomorrow
            for prayer, time_str in times['prayer_times'].items():
                emoji = PRAYER_EMOJIS.get(prayer, '⏰')
                message_text += f"{emoji} {prayer}: {time_str}\n"
        message_text += f"<code>-----------------</code>\n"

        next_prayer = "N/A"
        next_prayer_time = "N/A"
        if day_type == 'bugun':
            countdown_message, next_prayer, next_prayer_time, countdown = await calculate_next_prayer_countdown(
                times['prayer_times'], region, current_time, date_str
            )
            message_text += countdown_message

        # Send the formatted message with Markdown parsing for bold
        sent_message = await message.answer(message_text, parse_mode='HTML')

        # Log the message for future updates
        await log_message(chat_id, sent_message.message_id, day_type)

        # Schedule automatic updates for 'bugun' only
        if day_type == 'bugun':
            await asyncio.create_task(
                update_main_message(
                    chat_id,
                    sent_message.message_id,
                    times,
                    next_prayer,
                    next_prayer_time,
                    islamic_date
                )
            )
        return sent_message

    except TelegramForbiddenError as e:
        logger.error(f"User {chat_id} blocked bot: {e}")
        await facke_pooling.execute('DELETE FROM users WHERE chat_id = ?', (chat_id,))
        return None
    except Exception as e:
        logger.error(f"Error in send_main_message for chat {chat_id}: {e}")
        await message.answer("Xatolik yuz berdi. Iltimos, keyinroq urinib ko'ring.")
        return None


async def today_handler(message: types.Message):
    """Handle 'Bugun' button press."""
    await send_main_message(message, day_type='bugun')


async def tomorrow_handler(message: types.Message):
    """Handle 'Ertaga' button press."""
    await send_main_message(message, day_type='erta')


async def settings_handler(message: types.Message):
    """Handle 'Sozlamalar' button press."""
    await message.answer("Sozlamalar", reply_markup=get_settings_keyboard())


def register_commands(dp: Dispatcher):
    """Register command handlers with the Dispatcher."""
    dp.message.register(start_command, F.text == "/start")
    dp.message.register(set_location_command, F.text == "/set_location")
    # Register button handlers
    dp.message.register(today_handler, F.text == "Bugun")
    dp.message.register(tomorrow_handler, F.text == "Ertaga")
    dp.message.register(settings_handler, F.text == "⚙️ Sozlamalar")



"""
times = {
    'location': 'Toshkent',
    'date': 'Yakshanba, 13-Aprel',
    'prayer_times': {
        'Bomdod': '04:24',
        'Quyosh': '05:47',
        'Peshin': '12:24',
        'Asr': '17:05',
        'Shom': '19:04',
        'Xufton': '20:24'
    }
}
"""