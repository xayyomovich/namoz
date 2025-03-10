import aiosqlite
from aiogram import Dispatcher, types, F
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.keyboards.navigation import (get_main_keyboard, get_settings_keyboard)
from src.bot.utils.reminders import reminders
from src.config.settings import LOCATION_MAP, DATABASE_PATH, REVERSE_LOCATION_MAP
from src.bot.handlers.commands import send_main_message


async def location_callback(callback_query: types.CallbackQuery):
    """Handle location selection from inline keyboard."""
    region = callback_query.data.split('_')[1]
    chat_id = callback_query.message.chat.id
    city = REVERSE_LOCATION_MAP.get(region, 'Noma’lum shahar')
    # await callback_query.message.answer(f"Joylashuvingiz {city}", reply_markup=get_main_keyboard())
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('UPDATE users SET region = ? WHERE chat_id = ?', (region, chat_id))
        await db.commit()
    await callback_query.answer()
    await send_main_message(callback_query.message, region)
    await callback_query.answer()


async def settings_callback(callback_query: types.CallbackQuery):
    """Handle settings submenu."""
    await callback_query.message.answer("Sozlamalar:", reply_markup=get_settings_keyboard())
    await callback_query.answer()


async def reminders_callback(callback_query: types.CallbackQuery):
    """Handle reminders toggle with inline buttons."""
    chat_id = callback_query.message.chat.id
    prayers = ['Bomdod', 'Quyosh', 'Peshin', 'Asr', 'Shom', 'Xufton']
    builder = InlineKeyboardBuilder()
    for i in range(0, len(prayers), 3):
        row = [InlineKeyboardButton(
            text=f"{prayer} {'🔔' if reminders.get(chat_id, {}).get(prayer, False) else '🔕'}",
            callback_data=f"toggle_{prayer}"
        ) for prayer in prayers[i:i+3]]
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="Orqaga", callback_data="back"))
    await callback_query.message.answer("Eslatishlar:", reply_markup=builder.as_markup())
    await callback_query.answer()


async def toggle_prayer_callback(callback_query: types.CallbackQuery):
    """Toggle reminder for a specific prayer."""
    chat_id = callback_query.message.chat.id
    prayer = callback_query.data.split('_')[1]
    reminders.setdefault(chat_id, {})[prayer] = not reminders.get(chat_id, {}).get(prayer, False)
    await reminders_callback(callback_query)  # Refresh the reminders interface


async def back_callback(callback_query: types.CallbackQuery):
    """Return to main keyboard."""
    await callback_query.message.answer("Asosiy menyuga qaytdingiz:", reply_markup=get_main_keyboard())
    await callback_query.answer()


def register_callbacks(dp: Dispatcher):
    dp.callback_query.register(location_callback, F.data.startswith("location"))
    dp.callback_query.register(settings_callback, F.data == "Sozlamalar")
    dp.callback_query.register(reminders_callback, F.data == "Eslatish")
    dp.callback_query.register(toggle_prayer_callback, F.data.startswith("toggle"))
    dp.callback_query.register(back_callback, F.data == "Orqaga")
