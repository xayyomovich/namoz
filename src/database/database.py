import os
# from src.bot.bot import logger
from src.config.settings import DATABASE_PATH
import aiosqlite
import hashlib
import json


async def initialize_database():
    """Initialize database with necessary tables.
    - Creates directories if they don’t exist and sets up users, prayer_times, and message_log tables.
    - Ensures the database is ready for bot operations.
    """
    db_dir = os.path.dirname(DATABASE_PATH)
    os.makedirs(db_dir, exist_ok=True)  # Creates database directory if it doesn’t exist.
    from src.bot.bot import logger
    logger.info(f"Database path: {DATABASE_PATH}")

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


async def migrate_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if content_hash column exists
        cursor = await db.execute("PRAGMA table_info(message_log)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'content_hash' not in column_names:
            await db.execute('ALTER TABLE message_log ADD COLUMN content_hash TEXT')
            await db.commit()
            from src.bot.bot import logger
            logger.info("Added content_hash column to message_log table")


def compute_content_hash(text: str, reply_markup=None) -> str:
    """
    Compute a hash of the message text and reply markup.
    Args:
        text (str): The message text.
        reply_markup: The reply markup (e.g., InlineKeyboardMarkup).
    Returns:
        str: The MD5 hash of the content.
    """
    # Convert reply_markup to a string (if it exists)
    markup_str = json.dumps(reply_markup, sort_keys=True) if reply_markup else ""
    # Combine text and markup, encode, and compute MD5 hash
    content = f"{text}{markup_str}".encode('utf-8')
    return hashlib.md5(content).hexdigest()
# mijgona pittkalla, shabushin


async def get_message_hash(chat_id, message_id) -> str:
    """Get the content hash of a logged message.
    Args:
        chat_id (int): Telegram chat ID.
        message_id (int): ID of the message.
    Returns:
        str: The content hash, or None if not found.
    """
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=10) as db:
            cursor = await db.execute(
                'SELECT content_hash FROM message_log WHERE chat_id = ? AND message_id = ?',
                (chat_id, message_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else None
    except Exception as e:
        from src.bot.bot import logger
        logger.error(f"Error getting message hash for chat {chat_id}, message {message_id}: {e}")
        return None




