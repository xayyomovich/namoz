import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from src.config.settings import BOT_TOKEN
# from src.bot.handlers.commands import register_commands
from src.bot.handlers.callbacks import register_callbacks, register_message_handlers
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


async def on_startup(bot):
    """Handle bot startup event.
    - Logs startup, initializes the database, and caches monthly prayer times.
    - Starts the scheduler thread for reminders and periodic tasks.
    """
    logger.info('Bot starting...')
    from src.database.database import initialize_database, migrate_db
    await initialize_database()  # Ensure database is set up before proceeding.
    await migrate_db()
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
    from src.bot.handlers.commands import register_commands
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