import asyncio

import schedule
import time
import threading
from aiogram import Bot

from src.bot.handlers.commands import logger
from src.config.settings import BOT_TOKEN, RAMADAN_2025, DATABASE_PATH
from datetime import datetime, timedelta
import aiosqlite
from src.scraping.prayer_times import scrape_prayer_times

bot = Bot(token=BOT_TOKEN)
reminders = {}  # Global reminders dictionary


async def update_main_message(chat_id, message_id, times, next_prayer, next_prayer_time):
    """Update the main message with countdown and reminders."""
    while True:
        current_time = datetime.now().strftime("%H:%M")
        time_until = datetime.strptime(next_prayer_time, "%H:%M") - datetime.strptime(current_time, "%H:%M")
        if time_until.total_seconds() < 0 and next_prayer != 'Bomdod':
            times_erta = await scrape_prayer_times_async(chat_id)  # Fetch tomorrow's times
            if times_erta and times_erta['prayer_times'].get('Bomdod'):
                next_prayer = 'Bomdod'
                next_prayer_time = times_erta['prayer_times']['Bomdod']
            else:
                next_prayer_time = 'N/A'
            time_until = datetime.strptime(next_prayer_time, "%H:%M") - datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1) if next_prayer_time != 'N/A' else timedelta(0)

        minutes, seconds = divmod(abs(time_until.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)
        countdown = f"{int(hours)}:{int(minutes):02d}" if hours > 0 else f"{int(minutes):02d}:{int(seconds):02d}"

        if datetime.now() in RAMADAN_2025:
            iftar_time = times['prayer_times'].get('Shom', 'N/A')
            if iftar_time != 'N/A':
                iftar_until = datetime.strptime(iftar_time, "%H:%M") - datetime.now().replace(second=0, microsecond=0)
                if iftar_until.total_seconds() < 0:
                    sahar_time = times_erta['prayer_times'].get('Bomdod', 'N/A') if times_erta else 'N/A'
                    if sahar_time != 'N/A':
                        sahar_until = datetime.strptime(sahar_time, "%H:%M") - datetime.now().replace(second=0, microsecond=0) + timedelta(days=1)
                        iftar_text = f"Saharlikgacha - {int(sahar_until.total_seconds() // 3600)}:{int((sahar_until.total_seconds() % 3600) // 60):02d} qoldi"
                    else:
                        iftar_text = "Saharlik vaqti mavjud emas"
                else:
                    iftar_text = f"Iftorlikgacha - {int(iftar_until.total_seconds() // 3600)}:{int((iftar_until.total_seconds() % 3600) // 60):02d} qoldi"
            else:
                iftar_text = "Iftorlik vaqti mavjud emas"
        else:
            iftar_text = f"Keyingi namozgacha - {countdown} qoldi"

        reminder_text = f"{next_prayer} kirishiga 5 daqiqa qoldi" if int(minutes) == 5 and int(seconds) == 0 and reminders.get(chat_id, {}).get(next_prayer, False) else ""
        message_text = (
            f"📍 {times['location']}\n"  # Use times['location'] from the passed dictionary
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
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message_text, parse_mode='Markdown')
            if int(minutes) == 5 and int(seconds) == 0 and reminders.get(chat_id, {}).get(next_prayer, False):
                await bot.send_message(chat_id, f"{next_prayer} kirishiga 5 daqiqa qoldi")
            if countdown == "0:00":
                await bot.delete_message(chat_id, message_id)
                break
        except Exception as e:
            logger.error(f"Error updating message: {e}")
        await asyncio.sleep(300)  # Update every 5 minutes


async def scrape_prayer_times_async(chat_id):
    """Async wrapper for scrape_prayer_times to fetch tomorrow's times."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT region FROM users WHERE chat_id = ?', (chat_id,))
        region = await cursor.fetchone()
    if region:
        return scrape_prayer_times(region[0], datetime.now().month, 'erta')
    return None


def run_scheduler():
    """Run the scheduler for reminders and message cleanup in a separate thread."""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def schedule_reminders(chat_id, prayer_times):
    """Schedule reminders and cleanup for enabled prayers."""
    for prayer, time in prayer_times.items():
        if reminders.get(chat_id, {}).get(prayer, False):
            hour, minute = time.split(':')
            schedule.every().day.at(f"{hour}:{minute}").do(
                lambda p=prayer, c=chat_id: bot.delete_message(c, bot.send_message(c, f"{p} vaqti keldi!").message_id)
            ).tag(f'reminder_{chat_id}_{prayer}')
        # Schedule cleanup for Bugun and Ertaga messages
        schedule.every().day.at("00:00").do(
            lambda c=chat_id: cleanup_old_messages(c)
        ).tag(f'cleanup_{chat_id}')


async def cleanup_old_messages(chat_id):
    """Delete Bugun and Ertaga messages older than 24 hours."""
    async with aiosqlite.connect('src/database/prayer_times.db') as db:
        cursor = await db.execute('SELECT message_id, created_at FROM message_log WHERE chat_id = ? AND (type = ? OR type = ?) AND created_at < ?',
                                 (chat_id, 'bugun', 'ertaga', (datetime.now() - timedelta(hours=24)).isoformat()))
        messages = await cursor.fetchall()
        for message_id, _ in messages:
            try:
                await bot.delete_message(chat_id, message_id)
                await db.execute('DELETE FROM message_log WHERE message_id = ?', (message_id,))
            except Exception as e:
                print(f"Error deleting message {message_id}: {e}")
        await db.commit()


# Log message for cleanup
async def log_message(chat_id, message_id, message_type):
    async with aiosqlite.connect('src/database/prayer_times.db') as db:
        await db.execute('INSERT INTO message_log (chat_id, message_id, type, created_at) VALUES (?, ?, ?, ?)',
                        (chat_id, message_id, message_type, datetime.now().isoformat()))
        await db.commit()


async def cache_prayer_times(region, month):
    """Cache prayer times for a region and month."""
    async with aiosqlite.connect('src/database/prayer_times.db') as db:
        for day in range(1, 32):  # Assuming max 31 days per month
            try:
                times = scrape_prayer_times(region, month, 'bugun')
                if times:
                    await db.execute('INSERT OR REPLACE INTO prayer_times (region, date, times) VALUES (?, ?, ?)',
                                    (region, datetime(2025, month, day).strftime('%Y-%m-%d'), str(times['prayer_times'])))
                    await db.commit()
            except Exception as e:
                print(f"Error caching day {day}: {e}")