import json

from bs4 import BeautifulSoup
import requests
from datetime import datetime
from src.config.settings import REVERSE_LOCATION_MAP

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

ISLAMIC_MONTHS = {
    'ражаб': 'Rajab',
    'шаъбон': "Sha'bon",
    'Рамазон': 'Ramazon',
    'шаввол': 'Shavvol',
    'зулқаъда': 'Zulqada',
    'зулҳижжа': 'Zulhijja',
    'муҳаррам': 'Muharram',
    'сафар': 'Safar',
    'рабиъул аввал': 'Rabiu-l Avval',
    'рабиъус сони': 'Rabius-Soni',
    'жумадул аввал': 'Jumadul Avval',
    'жумадис сони': 'Jumadis-Soni'
}

PRAYER_MAP = {
    'Тонг(Саҳарлик)': 'Bomdod (Saharlik)',
    'Қуёш': 'Quyosh',
    'Пешин': 'Peshin',
    'Аср': 'Asr',
    'Шом(Ифтор)': 'Shom (Iftorlik)',
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
        response.raise_for_status()  # raise_for_status() - checks whether the HTTP request was successful. If the request failed, it raises an exception.
        html_text = response.text   # response.text - returns the body of the webpage as a Unicode string.
        soup = BeautifulSoup(html_text, 'html.parser')   # 'html.parser' is the built-in Python HTML parser

        # Find the table headers
        headers = [th.text.strip() for th in soup.select('th.header_table')]
        if not headers or len(headers) < 9:
            return None
        # print(headers)   # ['Рамазон', 'март', 'Ҳафта куни', 'Тонг(Саҳарлик)', 'Қуёш', 'Пешин', 'Аср', 'Шом(Ифтор)', 'Хуфтон']


        # Find the row for the specified day
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
        </tr>-
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
        # print(f"<<<<<<<<day number--{day_number}>>>>>>>>")   #4
        # print(f">>>>>>>>day_of_week_cyrillic--{day_of_week_cyrillic}<<<<<<<<")    #Чоршанба
        # print(f">>>>>>>>day_of_week--{day_of_week}<<<<<<<<")    # Chorshanba


        # Get month name from the page title or fallback to current month
        # month_elem = [th.text.strip() for th in soup.select('th.header_table')]
        gregorian_month_cyrillic = headers[1] if headers else ""
        gregorian_month = UZBEK_MONTHS.get(gregorian_month_cyrillic, datetime.now().strftime('%B'))
        # print(f"<<<<<<<<month_elem--{headers}>>>>>>>>")   #   ['Рамазон', 'март', 'Ҳафта куни', 'Тонг(Саҳарлик)', 'Қуёш', 'Пешин', 'Аср', 'Шом(Ифтор)', 'Хуфтон']
        # print(f">>>>>>>>gregorian_month_cyrillic--{gregorian_month_cyrillic}<<<<<<<<")    #  март
        # print(f">>>>>>>>gregorian_month--{gregorian_month}<<<<<<<<")    # Mart



        # Get Islamic date if available
        islamic_month_cyrillic = headers[0] if headers else ""
        islamic_month = ISLAMIC_MONTHS.get(islamic_month_cyrillic, '')
        islamic_date_number = cells[0].text.strip()
        # print(f">>>>>>>>islamic_date_element--{islamic_month}<<<<<<<<")  #Ramazon
        # print(f">>>>>>>>islamic_date--{islamic_date_number}<<<<<<<<")    #4


        # Map prayer times
        prayer_times = {}
        for i, header in enumerate(headers[3:9], 0):
            prayer_name = PRAYER_MAP.get(header.strip(), f"Prayer{i + 1}")
            if i + 3 < len(cells):
                time_value = cells[i + 3].text.strip()
                prayer_times[prayer_name] = time_value if time_value else "N/A"
            else:
                prayer_times[prayer_name] = "N/A"
        # print(prayer_times)   # {'Bomdod (Saharlik)': '05:55', 'Quyosh': '07:11', 'Peshin': '12:54', 'Asr': '16:54', 'Shom (Iftorlik)': '18:41', 'Xufton': '19:54'}

        # Determine city name from region code
        city = REVERSE_LOCATION_MAP.get(region, 'Noma\'lum shahar')

        # Calculate next prayer and time
        next_prayer, next_prayer_time = get_next_prayer(prayer_times)

        return {
            'location': city,
            'date': f"{day_of_week}, {day_number}-{gregorian_month}",
            'islamic_date': f"{islamic_date_number} {islamic_month}, 1446",
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


