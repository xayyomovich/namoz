import asyncio
import os
from datetime import datetime, timedelta

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
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Set default properties for the bot
default = DefaultBotProperties(parse_mode='Markdown')

bot = Bot(token=BOT_TOKEN, default=default)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


async def initialize_database():
    """Initialize database with necessary tables."""
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)
    logger.info(f"Database path: {DATABASE_PATH}")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Prayer times table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS prayer_times (
                region TEXT NOT NULL,
                date TEXT NOT NULL,
                times TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (region, date)
            )
        ''')

        # Message log table for tracking messages
        await db.execute('''
            CREATE TABLE IF NOT EXISTS message_log (
                chat_id INTEGER,
                message_id INTEGER,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, message_id)
            )
        ''')

        await db.commit()
        logger.info("Database initialized successfully")


async def on_startup(bot):
    """Handle bot startup event."""
    logger.info('Bot starting...')
    await initialize_database()  # Ensure database is initialized

    # Initial cache of prayer times for all regions
    from src.scraping.prayer_times import scrape_prayer_times
    from src.config.settings import LOCATION_MAP
    import json

    current_month = asyncio.create_task(cache_monthly_prayer_times(bot))

    logger.info('Bot started successfully!')
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()


async def cache_monthly_prayer_times(bot):
    """Cache prayer times for all regions for the current month."""
    from src.config.settings import LOCATION_MAP
    from src.scraping.prayer_times import scrape_prayer_times
    import json

    logger.info("Starting to cache monthly prayer times for all regions")
    current_month = datetime.now().month

    async with aiosqlite.connect(DATABASE_PATH) as db:
        for city, region in LOCATION_MAP.items():
            try:
                logger.info(f"Caching data for {city} (region {region})")

                # Get today's data
                today_data = scrape_prayer_times(region, current_month, 'bugun')
                if today_data and 'prayer_times' in today_data:
                    today_date = datetime.now().strftime("%Y-%m-%d")
                    times_json = json.dumps(today_data['prayer_times'])

                    await db.execute(
                        '''INSERT OR REPLACE INTO prayer_times 
                           (region, date, times) VALUES (?, ?, ?)''',
                        (region, today_date, times_json)
                    )

                # Get tomorrow's data
                tomorrow = datetime.now() + timedelta(days=1)
                tomorrow_month = tomorrow.month
                tomorrow_data = scrape_prayer_times(region, tomorrow_month, 'erta')
                if tomorrow_data and 'prayer_times' in tomorrow_data:
                    tomorrow_date = tomorrow.strftime("%Y-%m-%d")
                    times_json = json.dumps(tomorrow_data['prayer_times'])

                    await db.execute(
                        '''INSERT OR REPLACE INTO prayer_times 
                           (region, date, times) VALUES (?, ?, ?)''',
                        (region, tomorrow_date, times_json)
                    )

                await db.commit()
            except Exception as e:
                logger.error(f"Error caching data for {city}: {str(e)}")

    logger.info("Finished caching monthly prayer times")


async def main():
    """Main function to start the bot."""
    from datetime import datetime, timedelta

    # Register all handlers
    register_commands(dp)
    register_callbacks(dp)
    register_states(dp)

    # Register startup handler
    dp.startup.register(on_startup)

    # Start the bot
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())

