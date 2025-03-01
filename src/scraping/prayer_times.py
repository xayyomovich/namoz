from bs4 import BeautifulSoup
import requests
from datetime import datetime
from src.config.settings import REVERSE_LOCATION_MAP, LOCATION_MAP


def scrape_prayer_times(region, month=None, day_type='bugun'):
    """Scrape prayer times for a given region, month, and day type."""
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
        soup = BeautifulSoup(html_text, 'lxml')

        # Find the table headers
        headers = [th.text.strip().replace('\n', ' ') for th in soup.find_all('th', class_='header_table')]
        if not headers or len(headers) < 6:  # Ensure enough headers for all prayers
            return None

        # Map prayer names
        prayer_map = {
            'Тонг (Саҳарлик)': 'Bomdod',
            'Қуёш': 'Quyosh',
            'Пешин': 'Peshin',
            'Аср': 'Asr',
            'Шом (Ифтор)': 'Shom',
            'Хуфтон': 'Xufton'
        }

        # Find the row for the specified day
        row_class = day_classes[day_type]
        day_row = soup.find('tr', class_=row_class)
        if not day_row:
            return None

        # Extract hours and date information
        hours = [td.text.strip() for td in day_row.find_all('td')]
        if len(hours) < 6:  # Ensure minimum columns for date, day, and 5 prayer times
            return None

        date = hours[0]  # Day number
        day_of_week = hours[1]  # Day of week
        gregorian_month = headers[1].capitalize() if len(headers) > 1 else datetime.now().strftime('%B')
        islamic_date_elem = soup.find('div', class_='hijri')  # Adjust class based on actual HTML
        islamic_month = islamic_date_elem.text.strip() if islamic_date_elem else f"{datetime.now().day} Sha’bon, 1446"  # Dynamic fallback

        # Map headers to prayer times with fallback for missing times
        prayer_times = {prayer: 'N/A' for prayer in prayer_map.values()}  # Initialize with defaults
        for i, header in enumerate(headers[2:], 2):  # Start from the third header
            if i < len(hours) and header in prayer_map:
                prayer_times[prayer_map[header]] = hours[i] or 'N/A'

        # Determine location name from region
        city = REVERSE_LOCATION_MAP.get(region, 'Noma’lum shahar')

        return {
            'location': city,
            'date': f"{day_of_week}, {date} {gregorian_month}",
            'islamic_date': islamic_month,
            'prayer_times': prayer_times,
            'day_type': day_type
        }
    except requests.RequestException as e:
        print(f"Network error: {e.response.status_code} - {e.response.reason} for URL: {url}")
        return None
    except Exception as e:
        print(f"Error scraping prayer times: {e}")
        return None