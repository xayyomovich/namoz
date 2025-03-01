import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from src.config.settings import BOT_TOKEN, DATABASE_PATH
from src.bot.handlers.commands import register_commands
from src.bot.handlers.callbacks import register_callbacks
from src.bot.states.location import register_states
from src.bot.utils.reminders import run_scheduler
import aiosqlite
import threading


# Set default properties for the bot
default = DefaultBotProperties(parse_mode='Markdown')

bot = Bot(token=BOT_TOKEN, default=default)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


async def initialize_database():
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)
    print(f"Database path: {DATABASE_PATH}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS prayer_times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                fajr TEXT,
                sunrise TEXT,
                dhuhr TEXT,
                asr TEXT,
                maghrib TEXT,
                isha TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                message TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()


async def on_startup(bot):
    """Handle bot startup event."""
    print('Bot starting...')
    await initialize_database()  # Ensure database is initialized
    print('Bot started!')
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()


async def main():
    register_commands(dp)
    register_callbacks(dp)
    register_states(dp)
    dp.startup.register(on_startup)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

