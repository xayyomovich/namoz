import aiosqlite
from src.config.log_config import logger
import asyncio
from src.config.settings import DATABASE_PATH


class Database:
    def __init__(self):
        self.connection = None
        self.semaphore = asyncio.Semaphore(1)

    async def init(self):
        try:
            self.connection = await aiosqlite.connect(DATABASE_PATH)
            await self.connection.execute("PRAGMA foreign_keys = ON")
            await self.connection.execute("PRAGMA journal_mode = WAL")
            await self.connection.commit()
            logger.info("Database connection initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def close(self):
        if self.connection:
            await self.connection.close()
            logger.info("Database connection closed")
            self.connection = None

    async def execute(self, query, parameters=()):
        async with self.semaphore:
            try:
                cursor = await self.connection.execute(query, parameters)
                await self.connection.commit()
                return cursor
            except Exception as e:
                await self.connection.rollback()
                logger.error(f"Query failed: {query}, params: {parameters}, error: {e}")
                raise

    async def fetchone(self, query, parameters=()):
        cursor = await self.execute(query, parameters)
        result = await cursor.fetchone()
        await cursor.close()
        return result

    async def fetchall(self, query, parameters=()):
        cursor = await self.execute(query, parameters)
        result = await cursor.fetchall()
        await cursor.close()
        return result


facke_pooling = Database()