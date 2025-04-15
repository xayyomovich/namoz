import asyncio
from src.config.log_config import logger
from aiogram import Bot, Router
from datetime import datetime, timedelta
import schedule
import time
import threading

from src.bot.utils.calculations import calculate_islamic_date, calculate_exact_prayer, calculate_next_prayer_countdown
from src.config.constants import UZBEK_MONTHS_EN, PRAYER_EMOJIS
from src.config.settings import BOT_TOKEN, DATABASE_PATH
from src.db.pooling import facke_pooling
from src.scraping.prayer_times import fetch_cached_prayer_times, cache_monthly_prayer_times

router = Router()
bot = Bot(token=BOT_TOKEN)

# Global dictionaries to track reminders and cached messages
reminders = {}  # Stores reminder states for each chat_id and prayer
reminders_triggered = {}
message_cache = {}  # Caches the main message data for each chat_id


async def update_main_message(chat_id, message_id, times, next_prayer, next_prayer_time, islamic_date):
    print("=-=-=-=-=-=-=-=-=-=-=-=update_main_message-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
    """
    Update the main message with countdown and reminders.
    Args:
        chat_id (int): Telegram chat ID.
        message_id (int): ID of the message to update.
        times (dict): Prayer times data from fetch_cached_prayer_times.
        next_prayer (str): Name of the next prayer.
        next_prayer_time (str): Time of the next prayer.
        islamic_date (str): Pre-calculated Islamic date (optional, passed to avoid recalculation).
    """
    # Cache the message data for periodic updates
    message_cache[chat_id] = {
        'message_id': message_id,
        'times': times,
        'next_prayer': next_prayer,
        'next_prayer_time': next_prayer_time,
        'islamic_date': islamic_date,
        'last_date': times['date']  # Track the date of the current data for day transitions
    }
    await asyncio.create_task(_update_message_task(chat_id))  # Run updates in a background task


async def _update_message_task(chat_id):
    print("=-=-=-=-=-=-=-=-=-=-=-=_update_message_task-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
    """
    Async task to periodically update the main message and handle reminders.
    - Now recalculates the Islamic date dynamically during day transitions.
    """
    if chat_id not in message_cache:
        return

    data = message_cache[chat_id]
    message_id = data['message_id']
    times = data['times']
    next_prayer = data['next_prayer']
    next_prayer_time = data['next_prayer_time']
    islamic_date = data['islamic_date']
    last_date = data['last_date']   # 'Yakshanba, 13-Aprel'

    try:
        while True:  # Controlled loop with delay
            now = datetime.now()   # 2025-04-13 12:19:00
            current_time = now.strftime("%H:%M")  # "12:19"

            # Check if it crossed midnight to fetch tomorrow's data
            current_date = now.strftime("%Y-%m-%d")
            expected_date = last_date.split(', ')[1].split('-')
            month_num = UZBEK_MONTHS_EN[expected_date[1]]
            try:
                day = int(expected_date[0])
                expected_date = f"{now.year}-{str(month_num).zfill(2)}-{str(day).zfill(2)}"
            except ValueError as e:
                logger.error(f"Invalid day format in expected_date: {expected_date[0]}. Error: {e}")
                expected_date = f"{now.year}-{str(month_num).zfill(2)}-01"

            if current_date != expected_date:
                tomorrow_date = now.strftime("%Y-%m-%d")
                tomorrow_times = await fetch_cached_prayer_times(times['location'], tomorrow_date)
                if tomorrow_times:
                    times = tomorrow_times
                    message_cache[chat_id]['times'] = times
                    message_cache[chat_id]['last_date'] = times['date']
                    islamic_date = await calculate_islamic_date(tomorrow_date)
                    message_cache[chat_id]['islamic_date'] = islamic_date
                else:
                    logger.error(f"No cached data for {tomorrow_date} for {times['location']}")
                    await asyncio.sleep(60)
                    continue

            # Update next prayer
            countdown_message, next_prayer, next_prayer_time, countdown = await calculate_next_prayer_countdown(
                times['prayer_times'], times['location'], current_time, current_date)

            message_cache[chat_id]['next_prayer'] = next_prayer
            message_cache[chat_id]['next_prayer_time'] = next_prayer_time

            # Check for reminder
            reminder_triggered = False
            if next_prayer != "N/A" and next_prayer_time != "N/A":
                next_time = datetime.strptime(next_prayer_time, "%H:%M")
                next_time = now.replace(hour=next_time.hour, minute=next_time.minute, second=0, microsecond=0)
                if next_time < now:
                    next_time += timedelta(days=1)
                time_until = next_time - now
                total_seconds_until = time_until.total_seconds()
                if 240 <= total_seconds_until <= 600:
                    reminder_enabled = chat_id not in reminders.get(next_prayer, {})
                    has_triggered = reminders_triggered.get(chat_id, {}).get(next_prayer) == current_date
                    if reminder_enabled and not has_triggered:
                        reminder_triggered = True
                        reminders_triggered.setdefault(chat_id, {})[next_prayer] = current_date
                        new_message = await send_new_main_message(chat_id, times, current_time, islamic_date)
                        try:
                            await bot.delete_message(chat_id, message_id)
                        except Exception as e:
                            logger.error(f"Error deleting message {message_id}: {e}")
                        message_cache[chat_id]['message_id'] = new_message.message_id
                        message_id = new_message.message_id
            await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Error updating message: {e}")
        await asyncio.sleep(120)
        await _update_message_task(chat_id)


async def send_new_main_message(chat_id, times, current_time, islamic_date):
    print("=-=-=-=-=-=-=-=-=-=-=-=send_new_main_message-=-=-=-=-=-=-=-=-=-=-=-=-=-=")
    """Send a new main message for reminders.
    Args:
        chat_id (int): Telegram chat ID.
        times (dict): Prayer times data.
        current_time (str): Current time in "HH:MM" format.
        islamic_date (str): Islamic date string.
    Returns:
        Message: The sent message object.,
    """
    current_date = datetime.now().strftime("%Y/%m/%d")
    countdown_message, next_prayer, next_prayer_time, countdown = await calculate_next_prayer_countdown(
        times['prayer_times'], times['location'], current_time, current_date
    )

    message_text = (
        f"{countdown_message}\n"
        f"<code>-----------------</code>\n"
        f"📍 {times['location']}\n"
        f"🗓 {times['date']}\n"
        f"☪️ {islamic_date}\n"
        f"<code>-----------------</code>\n"
    )

    exact_prayer = await calculate_exact_prayer(times['prayer_times'], current_time)

    for prayer, time_str in times['prayer_times'].items():
        emoji = PRAYER_EMOJIS.get(prayer, '⏰')
        if prayer == exact_prayer:
            message_text += f"<blockquote><b>{emoji} {prayer}: {time_str}</b>      </blockquote>\n"
        else:
            message_text += f"{emoji} {prayer}: {time_str}\n"

    new_message = await bot.send_message(chat_id, message_text, parse_mode='HTML')
    await log_message(chat_id, new_message.message_id, 'bugun')

    return new_message


def run_scheduler(loop: asyncio.AbstractEventLoop):
    """Run the scheduler in the bot's event loop to avoid conflicts."""
    if loop is None:
        loop = asyncio.get_event_loop()

    def schedule_tasks():
        schedule.every(4).weeks.do(lambda: asyncio.run_coroutine_threadsafe(cache_monthly_prayer_times(), loop))

        while True:
            schedule.run_pending()
            time.sleep(720)

    scheduler_thread = threading.Thread(target=schedule_tasks, daemon=True)
    scheduler_thread.start()


async def log_message(chat_id, message_id, message_type):
    """Log a message to the database for tracking.
    Args:
        chat_id (int): Telegram chat ID.
        message_id (int): ID of the message.
        message_type (str): Type of message (e.g., 'bugun').
    """
    try:
        await facke_pooling.execute(
            'INSERT INTO message_log (chat_id, message_id, type, created_at) VALUES (?, ?, ?, ?)',
            (chat_id, message_id, message_type, datetime.now().isoformat())
            )
    except Exception as e:
        logger.error(f"Error logging message: {e}")
