import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from src.config.settings import BOT_TOKEN
from src.bot.handlers.callbacks import register_callbacks, register_message_handlers
import threading

from src.scraping.prayer_times import cache_monthly_prayer_times
from src.bot.utils.reminders import run_scheduler
from src.bot.utils import reminders
from src.db.pooling import facke_pooling
from src.bot.handlers import commands
from src.config.log_config import logger

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
    from src.db.database import initialize_database
    await initialize_database()  # Ensure database is set up before proceeding.
    await facke_pooling.init()
    await cache_monthly_prayer_times()
    logger.info('Monthly prayer times cached successfully on startup!')

    loop = asyncio.get_event_loop()  # Get the current event loop
    scheduler_thread = threading.Thread(target=run_scheduler, args=(loop,), daemon=True)
    scheduler_thread.start()
    logger.info('Scheduler thread started successfully!')


async def on_shutdown():
    """Clean up resources."""
    await facke_pooling.close()
    logger.info("Bot stopped")


async def main():
    """Main function to start the bot.
    - Registers all handlers for commands, callbacks, and states.
    - Sets up the startup event and starts polling for updates.
    """
    # Register all handlers
    from src.bot.handlers.commands import register_commands
    from src.middleware.rate_limit import rate_limit_middleware

    register_commands(dp)
    register_callbacks(dp)
    register_message_handlers(dp)
    dp.update.outer_middleware(rate_limit_middleware)
    dp.include_routers(commands.router, reminders.router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Start the bot
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())