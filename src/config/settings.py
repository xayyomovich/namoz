from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
LOCATION_MAP = {
    'Андижон': '1',
    'Бухоро': '4',
    'Гулистон': '5',
    'Жиззах': '9',
    'Марғилон': '13',
    'Наманган': '15',
    'Навоий': '14',
    'Нукус': '16',
    'Қарши': '25',
    'Қўқон': '26',
    'Самарқанд': '18',
    'Тошкент': '27',
    'Хива': '21'
}

REVERSE_LOCATION_MAP = {v: k for k, v in LOCATION_MAP.items()}  # Reverse mapping
RAMADAN_2025 = (datetime(2025, 3, 1), datetime(2025, 3, 30))  # Hardcoded for now
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'prayer_times.db')