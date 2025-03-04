from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
LOCATION_MAP = {
    'Andijon': '1',
    'Buxoro': '4',
    'Guliston': '5',
    'Jizzax': '9',
    'Marg\'ilon': '13',
    'Namangan': '15',
    'Navoiy': '14',
    'Nukus': '16',
    'Qarshi': '25',
    'Qo\'qon': '26',
    'Samarqand': '18',
    'Toshkent': '27',
    'Xiva': '21'
}

REVERSE_LOCATION_MAP = {v: k for k, v in LOCATION_MAP.items()}  # Reverse mapping
RAMADAN_DATES = (datetime(2025, 3, 1), datetime(2025, 3, 30))  # Hardcoded for now
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'prayer_times.db')