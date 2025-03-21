import asyncio
import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from src.config.settings import BOT_TOKEN, DATABASE_PATH
from src.bot.handlers.commands import register_commands
from src.bot.handlers.callbacks import register_callbacks, register_message_handlers
import aiosqlite
import threading
import logging
from src.scraping.prayer_times import cache_monthly_prayer_times
from src.bot.utils.reminders import run_scheduler


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

default = DefaultBotProperties(parse_mode='Markdown')

bot = Bot(token=BOT_TOKEN, default=default)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


async def initialize_database():
    """Initialize database with necessary tables.
    - Creates directories if they don’t exist and sets up users, prayer_times, and message_log tables.
    - Ensures the database is ready for bot operations.
    """
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)  # Creates database directory if it doesn’t exist.
    logger.info(f"Database path: {DATABASE_PATH}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table to store chat info
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Prayer times table to store cached prayer data
        await db.execute('''
            CREATE TABLE IF NOT EXISTS prayer_times (
                region TEXT NOT NULL,
                date TEXT NOT NULL,
                times TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (region, date)
            )
        ''')

        # Message log table to track sent messages
        await db.execute('''
            CREATE TABLE IF NOT EXISTS message_log (
                chat_id INTEGER,
                message_id INTEGER,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, message_id)
            )
        ''')

        await db.commit()  # Commits changes to the database.
        logger.info("Database initialized successfully")


async def on_startup(bot):
    """Handle bot startup event.
    - Logs startup, initializes the database, and caches monthly prayer times.
    - Starts the scheduler thread for reminders and periodic tasks.
    """
    logger.info('Bot starting...')
    await initialize_database()  # Ensure database is set up before proceeding.

    await cache_monthly_prayer_times()
    logger.info('Monthly prayer times cached successfully on startup!')

    loop = asyncio.get_event_loop()  # Get the current event loop
    scheduler_thread = threading.Thread(target=run_scheduler, args=(loop,), daemon=True)
    scheduler_thread.start()
    logger.info('Scheduler thread started successfully!')


async def main():
    """Main function to start the bot.
    - Registers all handlers for commands, callbacks, and states.
    - Sets up the startup event and starts polling for updates.
    """
    # Register all handlers
    register_commands(dp)  # Registers command handlers (e.g., /start, /bugun).
    register_callbacks(dp)  # Registers callback query handlers.
    register_message_handlers(dp)
    loop = asyncio.get_event_loop()
    run_scheduler(loop)

    # Register startup handler
    dp.startup.register(on_startup)  # Runs on_startup when the bot starts.

    # Start the bot
    await dp.start_polling(bot)  # Keeps the bot running and listening for updates.


if __name__ == '__main__':
    asyncio.run(main())  # Runs the main event loop.