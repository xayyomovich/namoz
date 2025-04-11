# bot/services/prayer_service.py
from datetime import datetime, timedelta
import aiosqlite
from src.config.constants import PRAYER_EMOJIS
from src.config import settings
from src.bot.utils.calculations import calculate_islamic_date, calculate_countdown_message
from src.scraping.prayer_times import fetchCachedPrayerTimes

async def getPrayerMessage(chat_id: int, region: str | None, day_type: str = "bugun") -> tuple[str, str, str, str]:
    """Generate formatted prayer times message."""
    # Fetch region from database if not provided
    if not region:
        async with aiosqlite.connect(settings.database_path) as db:
            cursor = await db.execute("SELECT region FROM users WHERE chat_id = ?", (chat_id,))
            region = (await cursor.fetchone())[0] if await cursor.fetchone() else None
        if not region:
            return "Iltimos, shahringizni tanlang", "N/A", "N/A", "N/A"

    # Determine date based on day_type
    date_str = datetime.now().strftime("%Y-%m-%d") if day_type == "bugun" else \
        (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Fetch prayer times
    times = await fetchCachedPrayerTimes(region, date_str)
    if not times:
        return "Namoz vaqtlari mavjud emas.", "N/A", "N/A", "N/A"

    # Calculate Islamic date
    islamic_date = await calculate_islamic_date(date_str)

    # Find closest prayer
    current_time = datetime.now().strftime("%H:%M")
    closest_prayer, min_diff = None, None
    for prayer, time_str in times["prayer_times"].items():
        if time_str != "N/A":
            prayer_minutes = int(time_str.split(":")[0]) * 60 + int(time_str.split(":")[1])
            current_minutes = int(current_time.split(":")[0]) * 60 + int(current_time.split(":")[1])
            time_diff = prayer_minutes - current_minutes
            if min_diff is None or abs(time_diff) < abs(min_diff):
                closest_prayer, min_diff = prayer, time_diff

    # Calculate countdown
    countdown_message, next_prayer, next_prayer_time, countdown = await calculate_countdown_message(
        day_type, times["next_prayer"], times["next_prayer_time"], closest_prayer, region, "N/A"
    )

    # Format message
    message_text = (
        f"<b>📍 {times['location']}</b>\n"
        f"<b>🗓 {times['date']}</b>\n"
        f"<b>☪️ {islamic_date}</b>\n"
        f"════════════════════\n"
    )
    for prayer, time_str in times["prayer_times"].items():
        emoji = PRAYER_EMOJIS.get(prayer, "⏰")
        if prayer == closest_prayer:
            message_text += f"<blockquote><b>{emoji} {prayer}: {time_str}</b></blockquote>\n"
        else:
            message_text += f"{emoji} {prayer}: {time_str}\n"
    message_text += f"════════════════════\n{countdown_message}"

    return message_text, next_prayer, next_prayer_time, countdown