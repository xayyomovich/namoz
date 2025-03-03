import json

from bs4 import BeautifulSoup
import requests
from datetime import datetime
from src.config.settings import REVERSE_LOCATION_MAP, LOCATION_MAP

UZBEK_WEEKDAYS_CYRILLIC_TO_LATIN = {
    'Душанба': 'Dushanba',
    'Сешанба': 'Seshanba',
    'Чоршанба': 'Chorshanba',
    'Пайшанба': 'Payshanba',
    'Жума': 'Juma',
    'Шанба': 'Shanba',
    'Якшанба': 'Yakshanba'
}

UZBEK_MONTHS_CYRILLIC_TO_LATIN = {
    'Январь': 'Yanvar',
    'Февраль': 'Fevral',
    'Март': 'Mart',
    'Апрель': 'Aprel',
    'Май': 'May',
    'Июнь': 'Iyun',
    'Июль': 'Iyul',
    'Август': 'Avgust',
    'Сентябрь': 'Sentabr',
    'Октябрь': 'Oktabr',
    'Ноябрь': 'Noyabr',
    'Декабрь': 'Dekabr'
}

PRAYER_MAP = {
    'Тонг (Саҳарлик)': 'Bomdod',
    'Қуёш': 'Quyosh',
    'Пешин': 'Peshin',
    'Аср': 'Asr',
    'Шом (Ифтор)': 'Shom',
    'Хуфтон': 'Xufton'
}


def scrape_prayer_times(region, month=None, day_type='bugun'):
    """
    Scrape prayer times for a given region, month, and day type.

    Args:
        region (str): Region code (e.g., '27' for Toshkent)
        month (int, optional): Month number (1-12). Defaults to current month.
        day_type (str, optional): 'bugun', 'erta', or 'kecha'. Defaults to 'bugun'.

    Returns:
        dict: Prayer times and related information or None on failure
    """
    if month is None:
        month = datetime.now().month

    day_classes = {
        'kecha': 'p_day kecha',
        'bugun': 'p_day bugun',
        'erta': 'p_day erta'
    }

    if day_type not in day_classes:
        return None

    url = f'https://islom.uz/vaqtlar/{region}/{month}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        html_text = response.text
        soup = BeautifulSoup(html_text, 'html.parser')

        # Find the table headers
        headers = [th.text.strip() for th in soup.select('th.header_table')]
        if not headers or len(headers) < 8:  # Headers should include day, weekday, and 6 prayer times
            return None

        # Find the row for the specified day
        day_row = soup.find('tr', class_=day_classes[day_type])
        if not day_row:
            return None

        # Extract cells and date information
        cells = day_row.find_all('td')
        if len(cells) < 8:  # Should have day, weekday, and 6 prayer times
            return None

        # Extract basic date information
        day_number = cells[0].text.strip()
        day_of_week_cyrillic = cells[1].text.strip()
        day_of_week = UZBEK_WEEKDAYS_CYRILLIC_TO_LATIN.get(day_of_week_cyrillic, day_of_week_cyrillic)

        # Get month name from the page title or fallback to current month
        month_elem = soup.select_one('div.region_name')
        gregorian_month_cyrillic = month_elem.text.strip().split()[-1] if month_elem else ""
        gregorian_month = UZBEK_MONTHS_CYRILLIC_TO_LATIN.get(gregorian_month_cyrillic,
                                                             datetime.now().strftime('%B'))

        # Get Islamic date if available
        islamic_date_elem = soup.select_one('div.hijri')
        islamic_date = islamic_date_elem.text.strip() if islamic_date_elem else f"{datetime.now().day} Sha'bon, 1446"

        # Map prayer times
        prayer_times = {}
        for i, header in enumerate(headers[2:8], 0):  # First 2 are day and weekday, next 6 are prayer times
            prayer_name = PRAYER_MAP.get(header.strip(), f"Prayer{i + 1}")
            if i + 2 < len(cells):
                time_value = cells[i + 2].text.strip()
                prayer_times[prayer_name] = time_value if time_value else "N/A"
            else:
                prayer_times[prayer_name] = "N/A"

        # Determine city name from region code
        city = REVERSE_LOCATION_MAP.get(region, 'Noma\'lum shahar')

        # Calculate next prayer and time
        next_prayer, next_prayer_time = get_next_prayer(prayer_times)

        return {
            'location': city,
            'date': f"{day_of_week}, {day_number} {gregorian_month}",
            'islamic_date': islamic_date,
            'prayer_times': prayer_times,
            'day_type': day_type,
            'next_prayer': next_prayer,
            'next_prayer_time': next_prayer_time
        }
    except requests.RequestException as e:
        print(f"Network error when fetching {url}: {str(e)}")
        return None
    except Exception as e:
        print(f"Error scraping prayer times: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def get_next_prayer(prayer_times):
    """
    Determine the next prayer time based on current time.

    Args:
        prayer_times (dict): Dictionary of prayer times

    Returns:
        tuple: (next_prayer_name, next_prayer_time)
    """
    current_time = datetime.now().strftime("%H:%M")

    # Filter valid prayer times and sort them
    valid_times = [(prayer, time) for prayer, time in prayer_times.items()
                   if time != "N/A" and len(time) >= 5]

    if not valid_times:
        return "N/A", "N/A"

    # Find the next prayer time that hasn't passed yet
    next_prayers = [(prayer, time) for prayer, time in valid_times if time > current_time]

    if next_prayers:
        # Return the next upcoming prayer
        next_prayers.sort(key=lambda x: x[1])
        return next_prayers[0]
    else:
        # If all prayers for today have passed, return the first prayer for tomorrow
        return "Bomdod", valid_times[0][1]


async def save_monthly_prayer_times(region, month, year, data):
    """Save monthly prayer times to database for caching."""
    import aiosqlite
    from src.config.settings import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as db:
        for day, day_data in data.items():
            date_str = f"{year}-{month:02d}-{day:02d}"
            times_json = json.dumps(day_data['prayer_times'])
            await db.execute(
                '''INSERT OR REPLACE INTO prayer_times 
                   (region, date, times) VALUES (?, ?, ?)''',
                (region, date_str, times_json)
            )
        await db.commit()


async def scrape_prayer_times_async(region, month=None, day_type='bugun'):
    """Async wrapper for scrape_prayer_times function."""
    return scrape_prayer_times(region, month, day_type)


async def fetch_cached_prayer_times(region, date_str):
    """Fetch cached prayer times from database if available."""
    import aiosqlite
    from src.config.settings import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            'SELECT times FROM prayer_times WHERE region = ? AND date = ?',
            (region, date_str)
        )
        result = await cursor.fetchone()

        if result:
            return json.loads(result[0])
        else:
            return None