import schedule
import time
import threading
from aiogram import Bot
from src.config.settings import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
reminders = {}  # Global reminders dictionary (shared across modules)


def run_scheduler():
    """Run the scheduler for reminders in a separate thread."""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute


def schedule_reminders(chat_id, prayer_times):
    """Schedule reminders for enabled prayers."""
    for prayer, time in prayer_times.items():
        if reminders.get(chat_id, {}).get(prayer, False):
            hour, minute = time.split(':')
            schedule.every().day.at(f"{hour}:{minute}").do(
                lambda p=prayer, c=chat_id: bot.send_message(
                    c, f"Time for {p}! 🔔"
                ))