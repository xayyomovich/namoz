from datetime import datetime, timedelta
from hijri_converter import Gregorian

import logging
from src.config.settings import RAMADAN_DATES
from src.scraping.prayer_times import ISLAMIC_MONTHS, fetch_cached_prayer_times

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_ramadan_countdown(now: datetime, times: dict, countdown: str) -> str:
    """
    Calculate the Ramadan countdown text (Saharlikgacha or Iftorlikgacha).

    Args:
        now (datetime): Current datetime.
        times (dict): Prayer times dictionary containing 'prayer_times'.
        countdown (str): Fallback countdown for non-Ramadan periods.

    Returns:
        str: Countdown text (e.g., "Saharlikgacha - 5:11 qoldi").
    """
    ramadan_start, ramadan_end = RAMADAN_DATES
    in_ramadan = ramadan_start <= now <= ramadan_end
    if not in_ramadan:
        return f"Keyingi namozgacha - {countdown} qoldi"

    bomdod_time = times['prayer_times'].get('Bomdod', 'N/A')
    shom_time = times['prayer_times'].get('Shom', 'N/A')
    if bomdod_time == 'N/A' or shom_time == 'N/A':
        return "Saharlik yoki Iftorlik vaqti mavjud emas"

    # Parse Bomdod and Shom times, adjusting for the correct day
    bomdod_dt = datetime.strptime(bomdod_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
    shom_dt = datetime.strptime(shom_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)

    # Adjust for midnight crossover
    if bomdod_dt > shom_dt:  # Bomdod is typically early morning, Shom is evening
        bomdod_dt -= timedelta(days=1)  # Bomdod is from the previous day
    if now > shom_dt:  # If after Shom, Bomdod is for the next day
        bomdod_dt += timedelta(days=1)
    elif now < bomdod_dt:  # If before Bomdod, Shom was the previous day
        shom_dt -= timedelta(days=1)

    # Determine countdown based on current time
    if now < bomdod_dt:  # Before Bomdod (e.g., 12:52 AM to 05:10 AM)
        time_until_sahar = bomdod_dt - now
        hours, remainder = divmod(time_until_sahar.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"Saharlikgacha - {hours}:{minutes:02d} qoldi"
    elif now < shom_dt:  # Between Bomdod and Shom (e.g., 05:10 AM to 18:37 PM)
        time_until_iftar = shom_dt - now
        hours, remainder = divmod(time_until_iftar.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"Iftorlikgacha - {hours}:{minutes:02d} qoldi"
    else:  # After Shom (e.g., 18:37 PM onwards)
        next_bomdod_dt = bomdod_dt + timedelta(days=1)
        time_until_sahar = next_bomdod_dt - now
        hours, remainder = divmod(time_until_sahar.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        return f"Saharlikgacha - {hours}:{minutes:02d} qoldi"


async def calculate_countdown_message(day_type, next_prayer, next_prayer_time, closest_prayer, region, countdown,
                                      now=None):
    """
    Calculate the countdown message for the next prayer, handling both today's prayers and tomorrow's Bomdod after Xufton.

    Args:
        day_type (str): 'bugun' or 'erta'.
        next_prayer (str): Name of the next prayer.
        next_prayer_time (str): Time of the next prayer in "HH:MM" format.
        closest_prayer (str): The closest prayer to the current time.
        region (str): The region for fetching prayer times.
        countdown (str): Pre-calculated countdown for today's prayer.
        now (datetime, optional): Current time for testing; defaults to datetime.now().

    Returns:
        tuple: (message_text, updated_next_prayer, updated_next_prayer_time, updated_countdown)
            - message_text: The formatted countdown message to append (or empty string if not applicable).
            - updated_next_prayer: Updated next prayer (e.g., "Bomdod" if Xufton has passed).
            - updated_next_prayer_time: Updated next prayer time.
            - updated_countdown: Updated countdown value.
    """
    if now is None:
        now = datetime.now()

    message_text = ""
    updated_next_prayer = next_prayer
    updated_next_prayer_time = next_prayer_time
    updated_countdown = countdown

    if day_type == 'bugun' and updated_next_prayer and updated_next_prayer_time != 'N/A':
        message_text = (
            f"{updated_next_prayer} gacha\n"
            f"- {updated_countdown} ⏰ qoldi"
        )
    elif day_type == 'bugun' and closest_prayer == "Xufton" and (
            not updated_next_prayer or updated_next_prayer_time == 'N/A'):
        # All prayers for today have passed; calculate countdown to tomorrow's Bomdod
        tomorrow_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times:
            bomdod_time = tomorrow_times['prayer_times'].get('Bomdod', 'N/A')
            if bomdod_time != 'N/A':
                try:
                    next_time = datetime.strptime(bomdod_time, "%H:%M")
                    next_time = now.replace(
                        hour=next_time.hour,
                        minute=next_time.minute,
                        second=0,
                        microsecond=0
                    ) + timedelta(days=1)  # Set to tomorrow
                    time_until = next_time - now
                    hours, remainder = divmod(time_until.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    updated_countdown = f"{hours}:{minutes:02d}"
                    updated_next_prayer = "Bomdod"
                    updated_next_prayer_time = bomdod_time
                    message_text = (
                        f"Ertangi Bomdod gacha\n"
                        f"- {updated_countdown} ⏰ qoldi"
                    )
                except Exception as e:
                    logger.error(f"Error calculating countdown to tomorrow's Bomdod: {str(e)}")
                    updated_next_prayer = "N/A"
                    updated_next_prayer_time = "N/A"
                    updated_countdown = "N/A"

    return message_text, updated_next_prayer, updated_next_prayer_time, updated_countdown


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








