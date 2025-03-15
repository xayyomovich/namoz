import asyncio
import logging
from aiogram import Bot
from datetime import datetime, timedelta
import aiosqlite
import schedule
import time
import threading
from hijri_converter import Gregorian

from src.config.settings import BOT_TOKEN, RAMADAN_DATES, DATABASE_PATH
from src.scraping.prayer_times import fetch_cached_prayer_times, get_next_prayer, cache_monthly_prayer_times, \
    ISLAMIC_MONTHS

UZBEK_MONTHS_EN = {
    'Yanvar': '01', 'Fevral': '02', 'Mart': '03', 'Aprel': '04', 'May': '05', 'Iyun': '06',
    'Iyul': '07', 'Avgust': '08', 'Sentabr': '09', 'Oktabr': '10', 'Noyabr': '11', 'Dekabr': '12'
}

# Initialize logger
# - Configures logging to capture info and errors with a detailed format.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot instance
bot = Bot(token=BOT_TOKEN)

# Global dictionaries to track reminders and cached messages
reminders = {}  # Stores reminder states for each chat_id and prayer
message_cache = {}  # Caches the main message data for each chat_id

# Prayer emojis for visual enhancement in messages
PRAYER_EMOJIS = {
    'Bomdod (Saharlik)': '🌅',
    'Quyosh': '☀️',
    'Peshin': '🌞',
    'Asr': '🌆',
    'Shom (Iftorlik)': '🌙',
    'Xufton': '⭐'
}


async def update_main_message(chat_id, message_id, times, next_prayer, next_prayer_time, islamic_date):
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


async def calculate_islamic_date(date_str):
    """
    Calculate the Islamic (Hijri) date for a given Gregorian date string.
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format (e.g., '2025-03-11').
    Returns:
        str: Islamic date in the format 'DD MonthName, YYYY' (e.g., '1 Rajab, 1446').
    """
    try:
        gregorian_date = datetime.strptime(date_str, "%Y-%m-%d")
        hijri = Gregorian(gregorian_date.year, gregorian_date.month, gregorian_date.day).to_hijri()
        islamic_date = f"{hijri.day} {ISLAMIC_MONTHS[hijri.month - 1]}, {hijri.year}"
        return islamic_date
    except Exception as e:
        logger.error(f"Error calculating Islamic date for {date_str}: {e}")
        return "N/A"


async def _update_message_task(chat_id):
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
    last_date = data['last_date']

    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # Check if we've crossed midnight to fetch tomorrow's data
        current_date = now.strftime("%Y-%m-%d")
        expected_date = last_date.split(', ')[1].split('-')
        expected_date = f"{now.year}-{UZBEK_MONTHS_EN[expected_date[1]]:02d}-{int(expected_date[0]):02d}"
        if current_date != expected_date:
            tomorrow_date = now.strftime("%Y-%m-%d")
            tomorrow_times = await fetch_cached_prayer_times(times['location'], tomorrow_date)
            if tomorrow_times:
                times = tomorrow_times
                message_cache[chat_id]['times'] = times
                message_cache[chat_id]['last_date'] = times['date']
                next_prayer, next_prayer_time = await get_next_prayer(times, times['location'], tomorrow_date)
                message_cache[chat_id]['next_prayer'] = next_prayer
                message_cache[chat_id]['next_prayer_time'] = next_prayer_time
                # Recalculate Islamic date for the new day
                islamic_date = await calculate_islamic_date(tomorrow_date)
                message_cache[chat_id]['islamic_date'] = islamic_date
            else:
                logger.error(f"No cached data for {tomorrow_date} for {times['location']}. Retrying in next cycle.")
                await asyncio.sleep(300)
                await _update_message_task(chat_id)
                return

        # Recalculate next prayer if the current time has passed the last next_prayer_time
        if next_prayer_time <= current_time:
            next_prayer, next_prayer_time = await get_next_prayer(times, times['location'], current_date)
            message_cache[chat_id]['next_prayer'] = next_prayer
            message_cache[chat_id]['next_prayer_time'] = next_prayer_time

            if next_prayer == "N/A":
                tomorrow_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
                tomorrow_times = await fetch_cached_prayer_times(times['location'], tomorrow_date)
                if tomorrow_times:
                    next_prayer, next_prayer_time = await get_next_prayer(tomorrow_times, times['location'],
                                                                          tomorrow_date)
                    times = tomorrow_times
                    message_cache[chat_id]['times'] = times
                    message_cache[chat_id]['next_prayer'] = next_prayer
                    message_cache[chat_id]['next_prayer_time'] = next_prayer_time
                    message_cache[chat_id]['last_date'] = times['date']
                    # Recalculate Islamic date for the new day
                    islamic_date = await calculate_islamic_date(tomorrow_date)
                    message_cache[chat_id]['islamic_date'] = islamic_date
                else:
                    logger.error(f"No cached data for tomorrow ({tomorrow_date}) for {times['location']}")
                    next_prayer = "N/A"
                    next_prayer_time = "N/A"
                    message_cache[chat_id]['next_prayer'] = next_prayer
                    message_cache[chat_id]['next_prayer_time'] = next_prayer_time

        # Calculate countdown to next prayer
        countdown = "N/A"
        reminder_triggered = False
        if next_prayer != "N/A" and next_prayer_time != "N/A":
            next_time = datetime.strptime(next_prayer_time, "%H:%M")
            next_time = now.replace(hour=next_time.hour, minute=next_time.minute, second=0, microsecond=0)
            if next_time < now:
                next_time += timedelta(days=1)
            time_until = next_time - now
            hours, remainder = divmod(time_until.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = f"{hours}:{int(minutes):02d}"

            # Trigger reminder 5 minutes before the prayer
            if minutes == 5 and seconds == 0 and chat_id not in reminders.get(next_prayer, {}):
                reminder_triggered = True
                reminders.setdefault(next_prayer, {}).update({chat_id: True})
                new_message = await send_new_main_message(chat_id, times, current_time, islamic_date, next_prayer,
                                                          next_prayer_time, countdown)
                try:
                    await bot.delete_message(chat_id, message_id)
                except Exception as e:
                    logger.error(f"Error deleting message {message_id} for chat {chat_id}: {e}")
                message_cache[chat_id]['message_id'] = new_message.message_id
                message_id = new_message.message_id

        # Ramadan countdown logic
        iftar_text = f"Keyingi namozgacha - {countdown} qoldi"
        ramadan_start, ramadan_end = RAMADAN_DATES
        in_ramadan = ramadan_start <= now <= ramadan_end
        if in_ramadan:
            bomdod_time = times['prayer_times'].get('Bomdod (Saharlik)', 'N/A')
            shom_time = times['prayer_times'].get('Shom (Iftorlik)', 'N/A')
            if bomdod_time != 'N/A' and shom_time != 'N/A':
                bomdod_dt = datetime.strptime(bomdod_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                shom_dt = datetime.strptime(shom_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
                if bomdod_dt < now:
                    bomdod_dt += timedelta(days=1)
                if shom_dt < now:
                    shom_dt += timedelta(days=1)
                if shom_dt > now > bomdod_dt:
                    time_until_iftar = shom_dt - now
                    hours, remainder = divmod(time_until_iftar.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Iftorlikgacha - {hours}:{int(minutes):02d} qoldi"
                else:
                    time_until_sahar = bomdod_dt - now
                    hours, remainder = divmod(time_until_sahar.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Saharlikgacha - {hours}:{int(minutes):02d} qoldi"

        # Find the closest prayer time for highlighting
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

        # Build the message text
        message_text = (
            f"📍 {times['location']}\n"
            f"🗓 {times['date']}\n"
            f"☪️ {islamic_date}\n"
            f"------------------------\n"
            f"{iftar_text} ⏰\n"
            f"------------------------\n"
        )
        for prayer, time_str in times['prayer_times'].items():
            emoji = PRAYER_EMOJIS.get(prayer, '⏰')
            highlight = "**" if prayer == closest_prayer else ""
            tick = " ✅" if prayer == closest_prayer else ""
            message_text += f"{emoji} {prayer}: {highlight}{time_str}{highlight}{tick}\n"
        message_text += f"------------------------\n"
        if next_prayer != "N/A" and next_prayer_time != "N/A":
            message_text += (
                f"{next_prayer} gacha\n"
                f"- {countdown} ⏰ qoldi"
            )

        # Update the message if no reminder was triggered
        if not reminder_triggered:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                parse_mode='Markdown'
            )

        # Schedule the next update (every 5 minutes)
        await asyncio.sleep(300)
        await _update_message_task(chat_id)

    except Exception as e:
        logger.error(f"Error updating message: {e}")
        await asyncio.sleep(300)
        await _update_message_task(chat_id)


async def send_new_main_message(chat_id, times, current_time, islamic_date, next_prayer, next_prayer_time, countdown):
    """Send a new main message for reminders.
    Args:
        chat_id (int): Telegram chat ID.
        times (dict): Prayer times data.
        current_time (str): Current time in "HH:MM" format.
        islamic_date (str): Islamic date string.
        next_prayer (str): Name of the next prayer.
        next_prayer_time (str): Time of the next prayer.
        countdown (str): Time remaining until the next prayer.
    Returns:
        Message: The sent message object.
    """
    now = datetime.now()
    iftar_text = f"Keyingi namozgacha - {countdown} qoldi"
    ramadan_start, ramadan_end = RAMADAN_DATES
    in_ramadan = ramadan_start <= now <= ramadan_end
    if in_ramadan:
        bomdod_time = times['prayer_times'].get('Bomdod (Saharlik)', 'N/A')
        shom_time = times['prayer_times'].get('Shom (Iftorlik)', 'N/A')
        if bomdod_time != 'N/A' and shom_time != 'N/A':
            bomdod_dt = datetime.strptime(bomdod_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            shom_dt = datetime.strptime(shom_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            if bomdod_dt < now:
                bomdod_dt += timedelta(days=1)
            if shom_dt < now:
                shom_dt += timedelta(days=1)
            if shom_dt > now > bomdod_dt:
                time_until_iftar = shom_dt - now
                hours, remainder = divmod(time_until_iftar.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                iftar_text = f"Iftorlikgacha - {hours}:{int(minutes):02d} qoldi"
            else:
                time_until_sahar = bomdod_dt - now
                hours, remainder = divmod(time_until_sahar.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                iftar_text = f"Saharlikgacha - {hours}:{int(minutes):02d} qoldi"

    # Find the closest prayer for highlighting
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

    # Build the message text
    message_text = (
        f"📍 {times['location']}\n"
        f"🗓 {times['date']}\n"
        f"☪️ {islamic_date}\n"
        f"------------------------\n"
        f"{iftar_text} ⏰\n"
        f"------------------------\n"
    )
    for prayer, time_str in times['prayer_times'].items():
        emoji = PRAYER_EMOJIS.get(prayer, '⏰')
        highlight = "**" if prayer == closest_prayer else ""
        tick = " ✅" if prayer == closest_prayer else ""
        message_text += f"{emoji} {prayer}: {highlight}{time_str}{highlight}{tick}\n"
    message_text += f"------------------------\n"
    if next_prayer != "N/A" and next_prayer_time != "N/A":
        message_text += (
            f"{next_prayer} gacha\n"
            f"- {countdown} ⏰ qoldi"
        )

    new_message = await bot.send_message(chat_id, message_text, parse_mode='Markdown')
    await log_message(chat_id, new_message.message_id, 'bugun')  # Log the new message
    return new_message


def run_scheduler():
    """Run the scheduler for monthly caching and message cleanup.
    - Schedules cache_monthly_prayer_times() to run on the 1st of each month.
    - Schedules cleanup_old_messages() to run hourly.
    - Runs in a loop, checking every 60 seconds.
    """
    schedule.every(4).week.do(lambda: asyncio.run(cache_monthly_prayer_times())).tag('monthly_cache')
    schedule.every().hour.do(lambda: asyncio.run(cleanup_old_messages()))

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


async def cleanup_old_messages():
    """Delete messages older than 24 hours from message_log.
    - Queries messages older than 24 hours and deletes them from Telegram.
    - Cleans up the message_log table accordingly.
    """
    try:
        one_day_ago = (datetime.now() - timedelta(hours=24)).isoformat()

        async with aiosqlite.connect(DATABASE_PATH, timeout=10) as db:  # Added timeout to prevent 'database locked'
            cursor = await db.execute(
                'SELECT chat_id, message_id FROM message_log WHERE created_at < ?',
                (one_day_ago,)
            )
            old_messages = await cursor.fetchall()

            for chat_id, message_id in old_messages:
                try:
                    await bot.delete_message(chat_id, message_id)
                except Exception as e:
                    logger.error(f"Error deleting message {message_id} for chat {chat_id}: {e}")

            await db.execute('DELETE FROM message_log WHERE created_at < ?', (one_day_ago,))
            await db.commit()

            logger.info(f"Cleaned up {len(old_messages)} old messages")
    except Exception as e:
        logger.error(f"Error cleaning up old messages: {e}")


async def log_message(chat_id, message_id, message_type):
    """Log a message to the database for tracking.
    Args:
        chat_id (int): Telegram chat ID.
        message_id (int): ID of the message.
        message_type (str): Type of message (e.g., 'bugun').
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=10) as db:  # Added timeout for safety
            await db.execute(
                'INSERT INTO message_log (chat_id, message_id, type, created_at) VALUES (?, ?, ?, ?)',
                (chat_id, message_id, message_type, datetime.now().isoformat())
            )
            await db.commit()
            logger.info(f"Logged message {message_id} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error logging message: {e}")