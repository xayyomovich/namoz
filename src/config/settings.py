from dotenv import load_dotenv
import os
from datetime import datetime
from src.config.constants import LOCATION_MAP

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')


REVERSE_LOCATION_MAP = {v: k for k, v in LOCATION_MAP.items()}  # Reverse mapping
RAMADAN_DATES = (datetime(2025, 3, 1), datetime(2025, 3, 30))  # Hardcoded for now
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'prayer_times.db')




