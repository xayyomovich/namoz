import os
from src.config.settings import DATABASE_PATH
import aiosqlite


async def initialize_database():
    """Initialize database with necessary tables.
    - Creates directories if they don’t exist and sets up users, prayer_times, and message_log tables.
    - Ensures the database is ready for bot operations.
    """
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)  # Creates database directory if it doesn’t exist.
    from src.config.log_config import logger

    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Users table to store chat info
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                username TEXT,
                region TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Prayer times table to store cached prayer data
        await db.execute('''
            CREATE TABLE IF NOT EXISTS prayer_times (
                region TEXT NOT NULL,
                date TEXT NOT NULL,
                times TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (region, date)
            )
        ''')

        # Message log table to track sent messages
        await db.execute('''
            CREATE TABLE IF NOT EXISTS message_log (
                chat_id INTEGER,
                message_id INTEGER,
                type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                content_hash TEXT,
                PRIMARY KEY (chat_id, message_id)
            )
        ''')

        await db.commit()  # Commits changes to the database.
        logger.info("Database initialized successfully")





