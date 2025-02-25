import asyncio
import threading
from aiogram import Bot, Dispatcher
from src.config.settings import BOT_TOKEN
from src.bot.handlers.commands import register_commands
from src.bot.handlers.callbacks import register_callbacks
from src.bot.states.location import register_states
from src.bot.utils.reminders import run_scheduler

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def on_startup():
    """Handle bot startup event."""
    print('Bot started!')
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()


def main():
    register_commands(dp)
    register_callbacks(dp)
    register_states(dp)
    dp.startup.register(on_startup)
    asyncio.run(dp.start_polling(bot))


if __name__ == '__main__':
    main()