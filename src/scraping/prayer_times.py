import json
import aiohttp
import logging
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from datetime import datetime, timedelta
import aiosqlite
from src.config.settings import DATABASE_PATH, REVERSE_LOCATION_MAP, LOCATION_MAP

# Initialize logger (replacing print statements for production use where needed, but keeping your debug prints)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants from your original code
UZBEK_WEEKDAYS = {
    'Душанба': 'Dushanba',
    'Сешанба': 'Seshanba',
    'Чоршанба': 'Chorshanba',
    'Пайшанба': 'Payshanba',
    'Жума': 'Juma',
    'Шанба': 'Shanba',
    'Якшанба': 'Yakshanba'
}

UZBEK_MONTHS = {
    'январь': 'Yanvar',
    'февраль': 'Fevral',
    'март': 'Mart',
    'апрель': 'Aprel',
    'май': 'May',
    'июнь': 'Iyun',
    'июль': 'Iyul',
    'август': 'Avgust',
    'сентябрь': 'Sentabr',
    'октябрь': 'Oktabr',
    'ноябрь': 'Noyabr',
    'декабрь': 'Dekabr'
}

ISLAMIC_MONTHS = [
    "Muharram", "Safar", "Rabiu-l Avval", "Rabius-Soni",
    "Jumadul Avval", "Jumadis-Soni", "Rajab", "Sha'bon",
    "Ramazon", "Shavvol", "Zulqada", "Zulhijja"
]

PRAYER_MAP = {
    'Тонг(Саҳарлик)': 'Bomdod',
    'Қуёш': 'Quyosh',
    'Пешин': 'Peshin',
    'Аср': 'Asr',
    'Шом(Ифтор)': 'Shom',
    'Хуфтон': 'Xufton'
}


## Scrape prayer times from islom.uz (your original function, now enhanced for monthly scraping)
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10), retry=retry_if_exception_type(aiohttp.ClientError))
async def scrape_prayer_times(region, month=None, day_type='bugun'):
    """
    Scrape prayer times from islom.uz for a region.
    Args:
        region (str): Region code (e.g., '27' for Toshkent).
        month (int): Month number (1-12), optional.
        day_type (str): 'bugun' for today, 'erta' for tomorrow, 'kecha' for yesterday, or 'month' for full month.
    Returns:
        dict: For 'bugun'/'erta'/'kecha': {'location': ..., 'date': ..., 'prayer_times': {...}, 'day_type': ..., 'next_prayer': ..., 'next_prayer_time': ...}
              For 'month': {'1': {...}, '2': {...}, ...} where each day has the same structure.
        None: On error.
    Example:
        For day_type='bugun': {'location': 'Toshkent', 'date': 'Dushanba, 3-Mart', 'prayer_times': {'Bomdod (Saharlik)': '05:24', ...}, 'day_type': 'bugun', 'next_prayer': 'Peshin', 'next_prayer_time': '12:23'}
        For day_type='month': {'1': {'location': 'Toshkent', 'date': 'Dushanba, 1-Mart', 'prayer_times': {...}, 'day_type': 'month'}, ...}
    """
    if month is None:
        month = datetime.now().month

    day_classes = {
        'kecha': 'p_day kecha',
        'bugun': 'p_day bugun',
        'erta': 'p_day erta'
    }

    if day_type not in day_classes and day_type != 'month':
        return None

    url = f'https://islom.uz/vaqtlar/{region}/{month}'
    try:
        # Use aiohttp for asynchronous HTTP request
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                response.raise_for_status()  # raise_for_status() - checks whether the HTTP request was successful. If the request failed, it raises an exception.
                html_text = await response.text()  # response.text - returns the body of the webpage as a Unicode string.
                soup = BeautifulSoup(html_text, 'html.parser')  # 'html.parser' is the built-in Python HTML parser

                # Find the table headers
                headers = [th.text.strip() for th in soup.select('th.header_table')]
                if not headers or len(headers) < 9:
                    return None
                # print(headers)   # ['Рамазон', 'март', 'Ҳафта куни', 'Тонг(Саҳарлик)', 'Қуёш', 'Пешин', 'Аср', 'Шом(Ифтор)', 'Хуфтон']

                if day_type == 'month':
                    # Scrape all days in the month
                    all_rows = soup.find_all('tr', class_=lambda c: c and 'p_day' in c)
                    # print(all_rows)
                    if not all_rows:
                        return None
                    monthly_data = {}
                    for row in all_rows:
                        cells = row.find_all('td')
                        if len(cells) < 9:  # Should have day, weekday, and 6 prayer times
                            continue
                        # print(cells)
                        """
                        [<td>1</td>, <td>1</td>, <td>Душанба</td>, <td class="sahar bugun">05:39</td>, <td>06:58</td>, <td>12:35</td>, <td>16:29</td>, <td class="iftor bugun">18:17</td>, <td>19:32</td>]
                        """

                        # Extract basic date information
                        day_number = cells[1].text.strip()
                        day_of_week_cyrillic = cells[2].text.strip()
                        day_of_week = UZBEK_WEEKDAYS.get(day_of_week_cyrillic, day_of_week_cyrillic)
                        # print(f"<<<<<<<<day number--{day_number}>>>>>>>>")   # 1
                        # print(f">>>>>>>>day_of_week_cyrillic--{day_of_week_cyrillic}<<<<<<<<")    # Душанба
                        # print(f">>>>>>>>day_of_week--{day_of_week}<<<<<<<<")    # Dushanba

                        # Get month name from the page title
                        gregorian_month_cyrillic = headers[1] if headers else ""
                        gregorian_month = UZBEK_MONTHS.get(gregorian_month_cyrillic, datetime.now().strftime('%B'))
                        # print(f"<<<<<<<<month_elem--{headers}>>>>>>>>")   # ['Рамазон', 'март', 'Ҳафта куни', 'Тонг(Саҳарлик)', 'Қуёш', 'Пешин', 'Аср', 'Шом(Ифтор)', 'Хуфтон']
                        # print(f">>>>>>>>gregorian_month_cyrillic--{gregorian_month_cyrillic}<<<<<<<<")    # март
                        # print(f">>>>>>>>gregorian_month--{gregorian_month}<<<<<<<<")    # Mart

                        # Map prayer times
                        prayer_times = {}
                        for i, header in enumerate(headers[3:9], 0):
                            # print(header)
                            prayer_name = PRAYER_MAP.get(header.strip(), f"Lazy {i + 1}")
                            # print(prayer_name)
                            if i + 3 < len(cells):
                                time_value = cells[i + 3].text.strip()
                                prayer_times[prayer_name] = time_value if time_value else "N/A"
                            else:
                                prayer_times[prayer_name] = "N/A"
                        # print(prayer_times)  # {'Bomdod (Saharlik)': '05:39', 'Quyosh': '06:58', 'Peshin': '12:35', 'Asr': '16:29', 'Shom (Iftorlik)': '18:17', 'Xufton': '19:32'}

                        # Determine city name from region code
                        city = REVERSE_LOCATION_MAP.get(region, 'Noma\'lum shahar')

                        # Calculate next prayer and time (using current time for consistency)
                        date_str = f"{datetime.now().year}-{month:02d}-{int(day_number):02d}"
                        next_prayer, next_prayer_time = await get_next_prayer({'prayer_times': prayer_times}, region, date_str)

                        monthly_data[day_number] = {
                            'location': city,
                            'date': f"{day_of_week}, {day_number}-{gregorian_month}",
                            'prayer_times': prayer_times,
                            'day_type': day_type,
                            'next_prayer': next_prayer,
                            'next_prayer_time': next_prayer_time
                        }
                    return monthly_data
                else:
                    # Single day scraping (kecha, bugun, erta)
                    day_row = soup.find('tr', class_=day_classes[day_type])
                    if not day_row:
                        return None
                    # print(day_row)
                    """
                    <tr class="p_day bugun">
                    <td>3</td>
                    <td>3</td>
                    <td>Душанба</td>
                    <td class="sahar bugun">05:24</td>
                    <td>06:42</td>
                    <td>12:23</td>
                    <td>16:20</td>
                    <td class="iftor bugun">18:07</td>
                    <td>19:22</td>
                    </tr>
                    """

                    # Extract cells and date information
                    cells = day_row.find_all('td')
                    if len(cells) < 9:  # Should have day, weekday, and 6 prayer times
                        return None
                    # print(cells)
                    """
                    [<td>3</td>, <td>3</td>, <td>Душанба</td>, <td class="sahar bugun">05:24</td>, <td>06:42</td>, <td>12:23</td>, <td>16:20</td>, <td class="iftor bugun">18:07</td>, <td>19:22</td>]
                    """

                    # Extract basic date information
                    day_number = cells[1].text.strip()
                    day_of_week_cyrillic = cells[2].text.strip()
                    day_of_week = UZBEK_WEEKDAYS.get(day_of_week_cyrillic, day_of_week_cyrillic)
                    # print(f"<<<<<<<<day number--{day_number}>>>>>>>>")   # 3
                    # print(f">>>>>>>>day_of_week_cyrillic--{day_of_week_cyrillic}<<<<<<<<")    # Душанба
                    # print(f">>>>>>>>day_of_week--{day_of_week}<<<<<<<<")    # Dushanba

                    # Get month name from the page title or fallback to current month
                    gregorian_month_cyrillic = headers[1] if headers else ""
                    gregorian_month = UZBEK_MONTHS.get(gregorian_month_cyrillic, datetime.now().strftime('%B'))
                    # print(f"<<<<<<<<month_elem--{headers}>>>>>>>>")   # ['Рамазон', 'март', 'Ҳафта куни', 'Тонг(Саҳарлик)', 'Қуёш', 'Пешин', 'Аср', 'Шом(Ифтор)', 'Хуфтон']
                    # print(f">>>>>>>>gregorian_month_cyrillic--{gregorian_month_cyrillic}<<<<<<<<")    # март
                    # print(f">>>>>>>>gregorian_month--{gregorian_month}<<<<<<<<")    # Mart

                    # Map prayer times
                    prayer_times = {}
                    for i, header in enumerate(headers[3:9], 0):
                        # print(header)
                        prayer_name = PRAYER_MAP.get(header.strip(), f"Lazy {i + 1}")
                        # print(prayer_name)
                        if i + 3 < len(cells):
                            time_value = cells[i + 3].text.strip()
                            prayer_times[prayer_name] = time_value if time_value else "N/A"
                        else:
                            prayer_times[prayer_name] = "N/A"
                    # print(prayer_times)  # {'Bomdod (Saharlik)': '05:24', 'Quyosh': '06:42', 'Peshin': '12:23', 'Asr': '16:20', 'Shom (Iftorlik)': '18:07', 'Xufton': '19:22'}

                    # Determine city name from region code
                    city = REVERSE_LOCATION_MAP.get(region, 'Noma\'lum shahar')

                    # Calculate next prayer and time
                    date_str = f"{datetime.now().year}-{month:02d}-{int(day_number):02d}"
                    next_prayer, next_prayer_time = await get_next_prayer({'prayer_times': prayer_times}, region, date_str)

                    return {
                        'location': city,
                        'date': f"{day_of_week}, {day_number}-{gregorian_month}",
                        'prayer_times': prayer_times,
                        'day_type': day_type,
                        'next_prayer': next_prayer,
                        'next_prayer_time': next_prayer_time
                    }
    except aiohttp.ClientError as e:
        print(f"Network error when fetching {url}: {str(e)}")
        return None
    except Exception as e:
        print(f"Error scraping prayer times: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


## Async wrapper for scraping
async def scrape_prayer_times_async(region, month=None, day_type='bugun'):
    """Async wrapper for scrape_prayer_times function."""
    return await scrape_prayer_times(region, month, day_type)


## Fetch cached prayer times from database
async def fetch_cached_prayer_times(region, date_str):
    """
    Fetch cached prayer times from database if available.
    Args:
        region (str): Region code.
        date_str (str): Date in 'YYYY-MM-DD' format.
    Returns:
        dict: Cached data or None if not found.
    Example:
        {'location': 'Toshkent', 'date': 'Dushanba, 1-Mart', 'prayer_times': {'Bomdod (Saharlik)': '05:39', ...}, 'day_type': 'month', 'next_prayer': 'Peshin', 'next_prayer_time': '12:35'}
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=10) as db:  ## Added timeout to prevent 'database locked'
            cursor = await db.execute(
                'SELECT times FROM prayer_times WHERE region = ? AND date = ?',
                (region, date_str)
            )
            result = await cursor.fetchone()
            if result:
                return json.loads(result[0])  ## Returns full dict as stored
            return None
    except Exception as e:
        logger.error(f"Error fetching cached prayer times for {region}, {date_str}: {e}")
        return None


## Save monthly prayer times to database
async def save_monthly_prayer_times(region, month, year, data):
    """
    Save monthly prayer times to database for caching.
    Args:
        region (str): Region code.
        month (int): Month number (1-12).
        year (int): Year.
        data (dict): Monthly data from scrape_prayer_times.
    Example:
        data = {'1': {'location': 'Toshkent', 'date': 'Dushanba, 1-Mart', 'prayer_times': {...}, ...}, ...}
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=10) as db:  ## Added timeout for safety
            # Check if data is a coroutine and await it if necessary
            if hasattr(data, '__await__'):
                data = await data

            for day, day_data in data.items():
                date_str = f"{year}-{month:02d}-{int(day):02d}"
                times_json = json.dumps(day_data)  ## Serialize the full day data
                await db.execute(
                    '''INSERT OR REPLACE INTO prayer_times 
                       (region, date, times) VALUES (?, ?, ?)''',
                    (region, date_str, times_json)
                )
            await db.commit()
            logger.info(f"Saved prayer times for region {region}, month {month}-{year}")
    except Exception as e:
        logger.error(f"Error saving prayer times for {region}, {month}-{year}: {e}")


## New function to cache monthly prayer times
async def cache_monthly_prayer_times():
    """Cache prayer times for all regions for the entire current month"""
    now = datetime.now()
    year = now.year
    month = now.month
    for region_name, region_code in LOCATION_MAP.items():
        try:
            logger.info(f"Caching prayer times for {region_name} ({region_code}) for {year}-{month}")
            # Scrape the entire month
            monthly_times = await scrape_prayer_times_async(region_code, month, 'month')
            if monthly_times:
                await save_monthly_prayer_times(region_code, month, year, monthly_times)
                logger.info(f"Cached prayer times for {region_name} for {year}-{month}")
            else:
                logger.error(f"Failed to scrape prayer times for {region_name}")
        except Exception as e:
            logger.error(f"Error caching prayer times for {region_name}: {e}")


## Get next prayer (unchanged, but updated to use logger)
async def get_next_prayer(prayer_times, region, date_str):
    """
    Determine the next prayer time.
    Args:
        prayer_times (dict): Current day’s prayer times.
        region (str): Region code.
        date_str (str): Current date.
    Returns:
        tuple: (next_prayer, next_prayer_time) or ('N/A', 'N/A').
    Example:
        ('Peshin', '12:35') or ('N/A', 'N/A')
    """
    current_time = datetime.now().strftime("%H:%M")
    next_prayer = None
    next_prayer_time = None

    for prayer, time_str in prayer_times['prayer_times'].items():
        if time_str != 'N/A' and time_str > current_time:
            if next_prayer is None or time_str < next_prayer_time:
                next_prayer = prayer
                next_prayer_time = time_str

    if next_prayer is None:
        tomorrow_date = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_times = await fetch_cached_prayer_times(region, tomorrow_date)
        if tomorrow_times:
            for prayer, time_str in sorted(tomorrow_times['prayer_times'].items(), key=lambda x: x[1]):
                if time_str != 'N/A':
                    next_prayer = prayer
                    next_prayer_time = time_str
                    break

    if next_prayer is None or next_prayer_time is None:
        logger.info(f"No next prayer found for {region}, {date_str}")
        return "N/A", "N/A"
    return next_prayer, next_prayer_time


