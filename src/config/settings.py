from dotenv import load_dotenv
import os

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '7677956586:AAGhcJF-sQP91-ktOAaJq7cESwBE3ojl7lk')
LOCATION_MAP = {
    'Tashkent': '27',
    'Samarkand': '61',
    # Add more cities/regions
}