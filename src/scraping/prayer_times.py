from bs4 import BeautifulSoup
import requests
from datetime import datetime


def scrape_prayer_times(region='27', month='2', day_type='bugun'):
    """Scrape prayer times for a given region, month, and day type (kecha, bugun, erta)."""
    day_classes = {
        'kecha': 'p_day kecha',
        'bugun': 'p_day bugun',
        'erta': 'p_day erta'
    }
    url = f'https://islom.uz/vaqtlar/27/2'
    html_text = requests.get(url).text
    soup = BeautifulSoup(html_text, 'lxml')

    # Extract headers
    times = soup.find_all('th', class_='header_table')
    headers = [time.text.strip().replace('\n', ' ') for time in times]

    # Map headers to desired names
    prayer_map = {
        'Тонг (Саҳарлик)': 'Bomdod',
        'Қуёш': 'Quyosh',
        'Пешин': 'Peshin',
        'Аср': 'Asr',
        'Шом (Ифтор)': 'Shom',
        'Хуфтон': 'Xufton'
    }

    # Extract the row for the specified day
    row_class = day_classes[day_type]
    day_row = soup.find('tr', class_=row_class)
    if not day_row:
        return None

    # Extract hours (data cells)
    hours = [td.text.strip() for td in day_row.find_all('td')]

    # Get date and day info
    date = hours[0]  # e.g., "21"
    day = hours[2]   # e.g., "Juma"
    gregorian_month = headers[1].capitalize()  # e.g., "Fevral"
    islamic_month = "22 Sha’bon, 1446"  # Hardcoded for now; scrape if available

    # Pair headers with times, using mapped names
    prayer_times = {}
    for header, hour in zip(headers[3:], hours[3:]):  # Skip date/month/day headers
        if header in prayer_map:
            prayer_times[prayer_map[header]] = hour

    return {
        'date': f"{day}, {date} {gregorian_month}",
        'islamic_date': islamic_month,
        'prayer_times': prayer_times,
        'day_type': day_type
    }