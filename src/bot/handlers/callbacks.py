from aiogram import Dispatcher, types, F
from src.bot.keyboards.navigation import get_navigation_keyboard
from src.bot.utils import reminders
from src.scraping.prayer_times import scrape_prayer_times
from datetime import datetime


async def full_times_callback(callback_query: types.CallbackQuery):
    """Show full prayer times (white interface) or navigate days."""
    chat_id = callback_query.message.chat.id
    # Determine day_type from callback data
    if callback_query.data in ["yesterday", "today", "tomorrow"]:
        day_type = {
            "yesterday": "kecha",
            "today": "bugun",
            "tomorrow": "erta"
        }[callback_query.data]
    else:  # For full_times callbacks (e.g., full_times_kecha, full_times_bugun, etc.)
        day_type = callback_query.data.split('_')[1] if '_' in callback_query.data and callback_query.data.startswith(
            "full_times") else 'bugun'

    times = await scrape_prayer_times(chat_id, day_type=day_type)

    if not times:
        await callback_query.answer("Error fetching prayer times.")
        return

    message = "🕌 *Namoaz vaqtlari*\n"
    for prayer, time in times['prayer_times'].items():
        reminder_status = "🔔" if reminders.get(chat_id, {}).get(prayer, False) else "🔕"
        message += f"{prayer}: {time} {reminder_status}\n"

    await callback_query.message.answer(message, parse_mode='Markdown')
    await callback_query.message.answer(
        "Navigate days:", reply_markup=get_navigation_keyboard()
    )
    await callback_query.answer()


async def toggle_reminders_callback(callback_query: types.CallbackQuery):
    """Prompt to toggle reminders."""
    await callback_query.message.answer(
        "Use /toggle_reminder [prayer] to enable/disable reminders.\n"
        "E.g., /toggle_reminder Bomdod"
    )
    await callback_query.answer()


def register_callbacks(dp: Dispatcher):
    dp.callback_query.register(full_times_callback, F.data.in_(
        ["yesterday", "today", "tomorrow", "full_times", "full_times_kecha", "full_times_bugun", "full_times_erta"]))
    dp.callback_query.register(toggle_reminders_callback, F.data == "toggle_reminders")