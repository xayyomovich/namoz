from datetime import datetime, timedelta
from hijri_converter import Gregorian
from src.config.log_config import logger

from src.config.constants import ISLAMIC_MONTHS
from src.scraping.prayer_times import fetch_cached_prayer_times


async def calculate_exact_prayer(prayer_times: dict, current_time: str, date_str: str) -> str | None:
    """Find the most recent prayer before or at the current time for highlighting."""
    exact_prayer = None
    max_time_diff = None
    current_dt = datetime.strptime(f"{date_str} {current_time}", "%Y-%m-%d %H:%M")

    for prayer, time_str in prayer_times.items():
        if time_str != "N/A":
            try:
                prayer_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                if prayer_dt > current_dt:
                    prayer_dt -= timedelta(days=1)  # Handle previous day if prayer is after current time
                time_diff = (prayer_dt - current_dt).total_seconds() / 60
                if time_diff <= 0 and (max_time_diff is None or time_diff > max_time_diff):
                    exact_prayer = prayer
                    max_time_diff = time_diff
            except ValueError as e:
                logger.error(f"Error parsing time {time_str} for {prayer}: {e}")
    # print(f"=-=-=-={exact_prayer}=-=-=-=-ex_pr=-=-=")
    return exact_prayer



async def calculate_next_prayer_countdown(prayer_times: dict, region: str, current_time: str, date_str: str) -> tuple[str, str, str, str]:
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

    next_prayer = "N/A"
    next_prayer_time = "N/A"
    countdown = "N/A"
    countdown_message = ""

    current_dt = datetime.strptime(f"{date_str} {current_time}", "%Y-%m-%d %H:%M")

    # Find next prayer for today
    for prayer, time_str in prayer_times.items():
        if time_str != "N/A":
            prayer_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            if prayer_dt > current_dt and (next_prayer == "N/A" or prayer_dt < datetime.strptime(f"{date_str} {next_prayer_time}", "%Y-%m-%d %H:%M")):
                next_prayer = prayer
                next_prayer_time = time_str

    # Calculate countdown
    if next_prayer != "N/A" and next_prayer_time != "N/A":
        try:
            prayer_dt = datetime.strptime(f"{date_str} {next_prayer_time}", "%Y-%m-%d %H:%M")
            if prayer_dt <= current_dt:
                prayer_dt += timedelta(days=1)
            time_until = prayer_dt - current_dt
            total_minutes = -(-int(time_until.total_seconds()) // 60)  # Ceiling division
            hours, minutes = divmod(total_minutes, 60)
            countdown = f"0{hours}:{minutes:02d}" if hours < 10 else f"{hours}:{minutes:02d}"
            countdown_message = f"<code><b>{next_prayer}</b> gacha <b>-{countdown}</b> 🕒 qoldi</code>"
            """
                        "<code><b>Peshin</b> gacha <b>-00:02</b> qoldi</code>",
                          "Peshin",
                           "12:24",
                          "00:02"
            """
        except Exception as e:
            logger.error(f"Error calculating countdown for {next_prayer}: {e}")

    # Handle post-Xufton
    if next_prayer == "N/A":
        tomorrow_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times and tomorrow_times.get("prayer_times"):
            bomdod_time = tomorrow_times['prayer_times'].get("Bomdod", "N/A")
            if bomdod_time != "N/A":
                next_prayer = "Bomdod"
                next_prayer_time = bomdod_time
                try:
                    bomdod_dt = datetime.strptime(f"{tomorrow_date} {bomdod_time}", "%Y-%m-%d %H:%M")
                    time_until = bomdod_dt - current_dt
                    total_minutes = -(-int(time_until.total_seconds()) // 60)
                    hours, minutes = divmod(total_minutes, 60)
                    countdown = f"0{hours}:{minutes:02d}" if hours < 10 else f"{hours}:{minutes:02d}"
                    countdown_message = f"<code><b>Bomdod</b> gacha <b>-{countdown}</b> 🕒 qoldi</code>"
                except Exception as e:
                    logger.error(f"Error calculating countdown to Bomdod: {e}")

    return countdown_message, next_prayer, next_prayer_time, countdown


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







