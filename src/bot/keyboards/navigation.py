from aiogram import types
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import (ReplyKeyboardBuilder, InlineKeyboardBuilder)
from src.config.settings import LOCATION_MAP


def get_main_keyboard():
    """Build main reply keyboard with 2x2 layout."""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Bugun"), types.KeyboardButton(text="Ertaga"))
    builder.row(types.KeyboardButton(text="Ramazon taqvimi"), types.KeyboardButton(text="Sozlamalar"))
    markup = builder.as_markup(resize_keyboard=True)
    return markup


def get_settings_keyboard():
    """Build settings submenu with reply buttons."""
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="Oldindan eslatish"), types.KeyboardButton(text="Joylashuvni o'zgartirish"))
    builder.row(types.KeyboardButton(text="Orqaga"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)


def get_location_keyboard():
    """Build location selection keyboard with 3 cities per row, alphabetically sorted."""
    builder = InlineKeyboardBuilder()
    sorted_cities = sorted(LOCATION_MAP.keys(), key=lambda x: x.lower())
    for i in range(0, len(sorted_cities), 3):
        row = [InlineKeyboardButton(text=city, callback_data=f"location_{LOCATION_MAP[city]}")
               for city in sorted_cities[i:i+3]]
        builder.row(*row)
    return builder.as_markup()
