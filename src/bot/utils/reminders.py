import asyncio
import logging
import schedule
import time
import threading
from aiogram import Bot
from datetime import datetime, timedelta
import aiosqlite
import json

from src.config.settings import BOT_TOKEN, RAMADAN_DATES, DATABASE_PATH
from src.scraping.prayer_times import scrape_prayer_times

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
reminders = {}  # Global reminders dictionary
message_cache = {}  # Cache of main messages


async def update_main_message(chat_id, message_id, times, next_prayer, next_prayer_time):
    """
    Update the main message with countdown and reminders.

    Args:
        chat_id: User's chat ID
        message_id: Message ID to update
        times: Dictionary with prayer times and metadata
        next_prayer: Name of the next prayer
        next_prayer_time: Time of the next prayer
    """
    # Store in global cache for thread access
    message_cache[chat_id] = {
        'message_id': message_id,
        'times': times,
        'next_prayer': next_prayer,
        'next_prayer_time': next_prayer_time
    }

    # Schedule the first update in 5 minutes
    await asyncio.create_task(_update_message_task(chat_id))


async def _update_message_task(chat_id):
    """Async task to periodically update the message"""
    if chat_id not in message_cache:
        return

    data = message_cache[chat_id]
    message_id = data['message_id']
    times = data['times']
    next_prayer = data['next_prayer']
    next_prayer_time = data['next_prayer_time']

    try:
        # Current time
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # Calculate time until next prayer
        next_prayer_dt = datetime.strptime(next_prayer_time, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )

        # If next prayer is tomorrow (e.g., it's after Xufton)
        if next_prayer_dt < now and next_prayer != 'Bomdod':
            # Get region from database
            async with aiosqlite.connect(DATABASE_PATH) as db:
                cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
                result = await cursor.fetchone()
                if not result:
                    logger.error(f"User {chat_id} not found in database")
                    return
                region = result[0]

            # Get tomorrow's prayer times
            tomorrow_times = scrape_prayer_times(region, now.month, 'erta')
            if tomorrow_times and 'Bomdod' in tomorrow_times['prayer_times']:
                next_prayer = 'Bomdod'
                next_prayer_time = tomorrow_times['prayer_times']['Bomdod']
                next_prayer_dt = datetime.strptime(next_prayer_time, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day + 1
                )
            else:
                logger.error(f"Failed to get tomorrow's prayer times for {chat_id}")
                return

        # Time until next prayer
        time_until = next_prayer_dt - now
        hours, remainder = divmod(time_until.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        countdown = f"{hours}:{minutes:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"

        # Check if during Ramadan
        now_date = now.date()
        ramadan_start, ramadan_end = RAMADAN_DATES
        is_ramadan = ramadan_start.date() <= now_date <= ramadan_end.date()

        if is_ramadan:
            # Get Bomdod (Saharlik) and Shom (Iftorlik) times
            bomdod_time = times['prayer_times'].get('Bomdod', 'N/A')
            shom_time = times['prayer_times'].get('Shom', 'N/A')

            if bomdod_time != 'N/A' and shom_time != 'N/A':
                bomdod_dt = datetime.strptime(bomdod_time, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
                shom_dt = datetime.strptime(shom_time, "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )

                # If before Shom time, countdown to Iftorlik
                if now < shom_dt:
                    time_until_iftar = shom_dt - now
                    hours, remainder = divmod(time_until_iftar.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Iftorlikgacha - {hours}:{minutes:02d} qoldi"
                else:
                    # After Shom, countdown to next day's Saharlik
                    next_bomdod_dt = bomdod_dt + timedelta(days=1)
                    time_until_sahar = next_bomdod_dt - now
                    hours, remainder = divmod(time_until_sahar.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    iftar_text = f"Saharlikgacha - {hours}:{minutes:02d} qoldi"
            else:
                iftar_text = "Saharlik yoki Iftorlik vaqti mavjud emas"
        else:
            iftar_text = f"Keyingi namozgacha - {countdown} qoldi"

        # Check if reminder is needed (5 minutes before prayer)
        reminder_text = ""
        if minutes == 5 and seconds == 0 and reminders.get(chat_id, {}).get(next_prayer, False):
            reminder_text = f"{next_prayer} kirishiga 5 daqiqa qoldi"
            # Send separate notification
            await bot.send_message(chat_id, reminder_text)

        # Build message text
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
            f"{reminder_text}\n"
            f"------------------------"
        )

        # Update message
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            parse_mode='Markdown'
        )

        # Schedule next update in 5 minutes
        # If prayer time has passed, remove from cache
        if time_until.total_seconds() <= 0:
            del message_cache[chat_id]
        else:
            await asyncio.sleep(300)  # 5 minutes
            await _update_message_task(chat_id)

    except Exception as e:
        logger.error(f"Error updating message: {e}")


def run_scheduler():
    """Run the scheduler for reminders and message cleanup in a separate thread."""
    schedule.every().day.at("00:00").do(lambda: asyncio.run(cache_daily_prayer_times()))

    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


async def cache_daily_prayer_times():
    """Cache prayer times for all regions for current month."""
    from src.config.settings import LOCATION_MAP

    now = datetime.now()
    month = now.month

    for region_name, region_code in LOCATION_MAP.items():
        try:
            logger.info(f"Caching prayer times for {region_name} ({region_code})")
            times = scrape_prayer_times(region_code, month)

            if times and times['prayer_times']:
                date_str = now.strftime("%Y-%m-%d")
                times_json = json.dumps(times['prayer_times'])

                async with aiosqlite.connect(DATABASE_PATH) as db:
                    await db.execute(
                        'INSERT OR REPLACE INTO prayer_times (region, date, times) VALUES (?, ?, ?)',
                        (region_code, date_str, times_json)
                    )
                    await db.commit()

                logger.info(f"Cached prayer times for {region_name}")
            else:
                logger.error(f"Failed to get prayer times for {region_name}")

        except Exception as e:
            logger.error(f"Error caching prayer times for {region_name}: {e}")

    logger.info("Completed caching prayer times for all regions")


async def cleanup_old_messages():
    """Delete messages older than 24 hours from message_log."""
    try:
        one_day_ago = (datetime.now() - timedelta(hours=24)).isoformat()

        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Get old messages
            cursor = await db.execute(
                'SELECT chat_id, message_id FROM message_log WHERE created_at < ?',
                (one_day_ago,)
            )
            old_messages = await cursor.fetchall()

            # Delete from Telegram
            for chat_id, message_id in old_messages:
                try:
                    await bot.delete_message(chat_id, message_id)
                except Exception as e:
                    logger.error(f"Error deleting message {message_id} for chat {chat_id}: {e}")

            # Delete from database
            await db.execute('DELETE FROM message_log WHERE created_at < ?', (one_day_ago,))
            await db.commit()

            logger.info(f"Cleaned up {len(old_messages)} old messages")
    except Exception as e:
        logger.error(f"Error cleaning up old messages: {e}")


async def log_message(chat_id, message_id, message_type):
    """Log a message to the database for tracking."""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                'INSERT INTO message_log (chat_id, message_id, type, created_at) VALUES (?, ?, ?, ?)',
                (chat_id, message_id, message_type, datetime.now().isoformat())
            )
            await db.commit()
            logger.info(f"Logged message {message_id} for chat {chat_id}")
    except Exception as e:
        logger.error(f"Error logging message: {e}")