from datetime import datetime, timedelta
from hijri_converter import Gregorian
from src.config.log_config import logger

from src.config.constants import ISLAMIC_MONTHS
from src.scraping.prayer_times import fetch_cached_prayer_times


async def calculate_exact_prayer(prayer_times: dict, current_time: str) -> str | None:
    """
    Find the exact prayer closest to the current time for highlighting.

    Args:
        prayer_times: Dict of prayer names to times (e.g., {"Bomdod": "04:24", ...}).
        current_time: Current time in "HH:MM" format.

    Returns:
        Name of the exact prayer (e.g., "Peshin") or None if no valid times.
    """
    exact_prayer = None
    min_time_diff = None

    for prayer, time_str in prayer_times.items():
        if time_str != "N/A":
            try:
                prayer_minutes = int(time_str.split(':')[0]) * 60 + int(time_str.split(':')[1])
                current_minutes = int(current_time.split(':')[0]) * 60 + int(current_time.split(':')[1])
                time_diff = prayer_minutes - current_minutes
                if min_time_diff is None or abs(time_diff) < abs(min_time_diff):
                    exact_prayer = prayer
                    min_time_diff = time_diff
                    # print(f"-=-=-=-=--=-=-=-=-=-min_time_diff=-=-=-=-=-=-=-=-=-={min_time_diff}")
            except ValueError as e:
                logger.error(f"Error parsing time {time_str} for {prayer}: {e}")
                continue

    return exact_prayer


async def calculate_next_prayer_countdown(prayer_times: dict, region: str, current_time: str, date_str: str) -> tuple[
    str, str, str, str]:
    """
    Calculate the next prayer and countdown message, including post-Xufton Bomdod.

    Args:
        prayer_times: Dict of prayer names to times (e.g., {"Bomdod": "04:24", ...}).
        region: Region code for fetching tomorrow's times.
        current_time: Current time in "HH:MM" format.
        date_str: Current date in "YYYY-MM-DD" format.

    Returns:
        Tuple: (countdown_message, next_prayer, next_prayer_time, countdown)
        - countdown_message: Formatted string like "<code><b>Peshin</b> gacha <b>-02:15</b> qoldi</code>".
        - next_prayer: Name of next prayer (e.g., "Peshin").
        - next_prayer_time: Time of next prayer (e.g., "12:24").
        - countdown: Countdown string (e.g., "02:15").
    """
    next_prayer = None
    next_prayer_time = None
    countdown = "N/A"
    countdown_message = ""

    # Find next prayer for today
    for prayer, time_str in prayer_times.items():
        if time_str != "N/A" and time_str > current_time:
            if next_prayer is None or time_str < next_prayer_time:
                next_prayer = prayer
                next_prayer_time = time_str

    # Calculate countdown
    if next_prayer and next_prayer_time != "N/A":
        try:
            now = datetime.now()
            next_time = datetime.strptime(next_prayer_time, "%H:%M")
            next_time = now.replace(hour=next_time.hour, minute=next_time.minute, second=0, microsecond=0)
            if next_time < now:
                next_time += timedelta(days=1)
            time_until = next_time - now
            hours, remainder = divmod(time_until.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = f"{hours}:{minutes:02d}"
            countdown_message = f"<code><b>{next_prayer}</b> gacha <b>-{countdown}</b> qoldi</code>"
            """
            "<code><b>Peshin</b> gacha <b>-00:02</b> qoldi</code>",
                "Peshin",
                "12:24",
                "00:02"
            """
        except Exception as e:
            logger.error(f"Error calculating countdown for {next_prayer}: {e}")
            countdown = "N/A"
            countdown_message = ""

    # Handle post-Xufton (no next prayer today)
    if not next_prayer:
        tomorrow_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times and tomorrow_times.get("prayer_times"):
            bomdod_time = tomorrow_times['prayer_times'].get("Bomdod", "N/A")
            if bomdod_time != "N/A":
                next_prayer = "Bomdod"
                next_prayer_time = bomdod_time
                try:
                    now = datetime.now()
                    next_time = datetime.strptime(bomdod_time, "%H:%M")
                    next_time = now.replace(hour=next_time.hour, minute=next_time.minute, second=0,
                                            microsecond=0) + timedelta(days=1)
                    time_until = next_time - now
                    hours, remainder = divmod(time_until.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    countdown = f"{hours}:{minutes:02d}"
                    countdown_message = f"<code>Bomdod gacha -{countdown} qoldi</code>"
                except Exception as e:
                    logger.error(f"Error calculating countdown to Bomdod: {e}")
                    countdown = "N/A"
                    countdown_message = ""

    return countdown_message, next_prayer or "N/A", next_prayer_time or "N/A", countdown


async def calculate_islamic_date(date_str):
    """
    Calculate the Islamic (Hijri) date for a given Gregorian date string.
    Args:
        date_str (str): Date in 'YYYY-MM-DD' format (e.g., '2025-03-11').
    Returns:
        str: Islamic date in the format 'DD MonthName, YYYY' (e.g., '1 Rajab, 1446').
    """
    try:
        gregorian_date = datetime.strptime(date_str, "%Y-%m-%d")
        hijri = Gregorian(gregorian_date.year, gregorian_date.month, gregorian_date.day).to_hijri()
        islamic_date = f"{hijri.day} {ISLAMIC_MONTHS[hijri.month - 1]}, {hijri.year}"
        return islamic_date
    except Exception as e:
        logger.error(f"Error calculating Islamic date for {date_str}: {e}")
        return "N/A"







