import aiosqlite
from aiogram import Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.keyboards.navigation import get_main_keyboard, get_location_keyboard, get_settings_keyboard
from src.bot.utils.reminders import reminders
from src.config.settings import LOCATION_MAP, DATABASE_PATH, REVERSE_LOCATION_MAP
from src.bot.handlers.commands import send_main_message

# Store user state (could also use a database)
user_state = {}  # {chat_id: {'level': 'main'|'settings'|'reminders', 'last_message_id': int}}


async def delete_previous_message(bot, chat_id, message_id=None):
    if chat_id in user_state and 'last_message_id' in user_state[chat_id]:
        if user_state[chat_id].get('level') == 'ramadan' and message_id != user_state[chat_id]['last_message_id']:
            return  # Don’t delete Ramadan message unless explicitly replaced
        try:
            await bot.delete_message(chat_id, user_state[chat_id]['last_message_id'])
        except Exception:
            pass


# async def ramadan_taqvim_command(message: types.Message):
#     chat_id = message.chat.id
#     # Assume this generates the Ramadan calendar
#     ramadan_text = "Ramazon taqvimi: ... (your logic here) ..."
#     new_message = await message.answer(ramadan_text, reply_markup=get_main_keyboard())
#     user_state[chat_id] = {'level': 'ramadan', 'last_message_id': new_message.message_id}


async def location_callback(callback_query: types.CallbackQuery):
    """Handle location selection from inline keyboard."""
    region = callback_query.data.split('_')[1]
    chat_id = callback_query.message.chat.id
    city = REVERSE_LOCATION_MAP.get(region, 'Noma’lum shahar')
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('UPDATE users SET region = ? WHERE chat_id = ?', (region, chat_id))
        await db.commit()
    await delete_previous_message(callback_query.bot, chat_id)
    new_message = await callback_query.message.answer(
        f"Joylashuvingiz: {city}",
        reply_markup=get_main_keyboard()
    )
    user_state[chat_id] = {'level': 'main', 'last_message_id': new_message.message_id}
    await send_main_message(callback_query.message, region)
    await callback_query.answer()


async def settings_callback(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await delete_previous_message(callback_query.bot, chat_id)
    new_message = await callback_query.message.answer("Sozlamalar", reply_markup=get_settings_keyboard())
    user_state[chat_id] = {'level': 'settings', 'last_message_id': new_message.message_id}
    await callback_query.answer()


async def reminders_callback(update: types.CallbackQuery | types.Message):
    if isinstance(update, types.CallbackQuery):
        chat_id = update.message.chat.id
        bot = update.bot
        message = update.message
    else:
        chat_id = update.chat.id
        bot = update.bot
        message = update
    prayers = ['Bomdod', 'Quyosh', 'Peshin', 'Asr', 'Shom', 'Xufton']
    builder = InlineKeyboardBuilder()
    for i in range(0, len(prayers), 3):
        row = [InlineKeyboardButton(
            text=f"{prayer} {'🔔' if chat_id not in reminders.get(prayer, {}) else '🔕'}",
            callback_data=f"toggle_{prayer}"
        ) for prayer in prayers[i:i + 3]]
        builder.row(*row)
    builder.row(InlineKeyboardButton(text="Orqaga", callback_data="back"))
    await delete_previous_message(bot, chat_id)
    new_message = await bot.send_message(
        chat_id,
        "Oldindan eslatish",
        reply_markup=builder.as_markup()
    )
    user_state[chat_id] = {'level': 'reminders', 'last_message_id': new_message.message_id}
    if isinstance(update, types.CallbackQuery):
        await update.answer()


async def toggle_prayer_callback(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    prayer = callback_query.data.split('_')[1]
    # If the reminder is currently ON (chat_id not in reminders[prayer]), turn it OFF by adding chat_id
    # If the reminder is currently OFF (chat_id in reminders[prayer]), turn it ON by removing chat_id
    if chat_id in reminders.get(prayer, {}):
        # Turn ON: Remove chat_id from reminders[prayer]
        reminders[prayer].pop(chat_id)
        if not reminders[prayer]:  # If no more chat_ids, remove the prayer key
            del reminders[prayer]
    else:
        # Turn OFF: Add chat_id to reminders[prayer]
        reminders.setdefault(prayer, {})[chat_id] = True
    await reminders_callback(callback_query)


async def change_location_callback(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    await delete_previous_message(callback_query.bot, chat_id)
    new_message = await callback_query.message.answer(
        "Iltimos, yangi shahringizni tanlang",
        reply_markup=get_location_keyboard()
    )
    user_state[chat_id] = {'level': 'location', 'last_message_id': new_message.message_id}
    await callback_query.answer()


async def back_callback(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    current_level = user_state.get(chat_id, {}).get('level', 'main')
    await delete_previous_message(callback_query.bot, chat_id)
    if current_level == 'reminders':
        new_message = await callback_query.message.answer("Sozlamalar", reply_markup=get_settings_keyboard())
        user_state[chat_id] = {'level': 'settings', 'last_message_id': new_message.message_id}
    elif current_level == 'settings':
        # Back to Main
        new_message = await callback_query.message.answer("Hozirgi namoz vaqtlari", reply_markup=get_main_keyboard())
        user_state[chat_id] = {'level': 'main', 'last_message_id': new_message.message_id}
        await send_main_message(callback_query.message)  # Send prayer times
    else:
        # Default to Main
        new_message = await callback_query.message.answer("Hozirgi namoz vaqtlari", reply_markup=get_main_keyboard())
        user_state[chat_id] = {'level': 'main', 'last_message_id': new_message.message_id}
        await send_main_message(callback_query.message)
    await callback_query.answer()


# Add message handler for reply keyboard buttons
async def handle_settings_options(message: types.Message):
    """Handle settings options from reply keyboard."""
    chat_id = message.chat.id
    text = message.text

    await delete_previous_message(message.bot, chat_id)
    if text == "Oldindan eslatish":
        await reminders_callback(message)
    elif text == "Joylashuvni o'zgartirish":
        new_message = await message.answer(
            "Iltimos, yangi shahringizni tanlang",
            reply_markup=get_location_keyboard()
        )
        user_state[chat_id] = {'level': 'location', 'last_message_id': new_message.message_id}
    elif text == "Orqaga":
        new_message = await message.answer("Hozirgi namoz vaqtlari", reply_markup=get_main_keyboard())
        user_state[chat_id] = {'level': 'main', 'last_message_id': new_message.message_id}
        await send_main_message(message)


def register_message_handlers(dp: Dispatcher):
    """Register message handlers for reply keyboard."""
    dp.message.register(handle_settings_options,
                        F.text.in_(["Oldindan eslatish", "Joylashuvni o'zgartirish", "Orqaga"]))


def register_callbacks(dp: Dispatcher):
    """Register callback query handlers."""
    dp.callback_query.register(location_callback, F.data.startswith("location_"))
    dp.callback_query.register(settings_callback, F.data == "settings")
    dp.callback_query.register(reminders_callback, F.data == "reminders")
    dp.callback_query.register(toggle_prayer_callback, F.data.startswith("toggle_"))
    dp.callback_query.register(change_location_callback, F.data == "change_location")
    dp.callback_query.register(back_callback, F.data == "back")
