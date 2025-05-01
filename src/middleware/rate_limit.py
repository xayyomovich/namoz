from datetime import datetime, timedelta
from aiogram.types import Update
from src.config.log_config import logger


class TelegramRateLimiter:
    def __init__(self, rate_limit=5, per_seconds=3, ban_duration=300):
        self.rate_limit = rate_limit
        self.per_seconds = per_seconds
        self.ban_duration = ban_duration
        self.requests = {}  # to store request timestamps
        self.banned_until = {}
        self.ban_message_sent = {}

    async def check_limit(self, chat_id):
        now = datetime.now()

        # Check if user is banned
        if chat_id in self.banned_until:
            if now < self.banned_until[chat_id]:
                return False, self.ban_message_sent.get(chat_id, False)
            else:
                del self.banned_until[chat_id]
                self.requests[chat_id] = []
                self.ban_message_sent.pop(chat_id, None)

        # Initialize request list if new chat_id
        if chat_id not in self.requests:
            self.requests[chat_id] = []

        # Remove requests older than per_seconds
        self.requests[chat_id] = [ts for ts in self.requests[chat_id] if
                                  now - ts <= timedelta(seconds=self.per_seconds)]

        # Add new request
        self.requests[chat_id].append(now)

        # Check if rate limit exceeded
        if len(self.requests[chat_id]) > self.rate_limit:
            self.banned_until[chat_id] = now + timedelta(seconds=self.ban_duration)
            self.ban_message_sent[chat_id] = False
            return False, False

        return True, False


telegram_limiter = TelegramRateLimiter(rate_limit=5, per_seconds=3, ban_duration=300)


async def rate_limit_middleware(handler, event: Update, data: dict):
    chat_id = event.message.chat.id if event.message else event.callback_query.message.chat.id
    allowed, message_sent = await telegram_limiter.check_limit(chat_id)
    if allowed:
        return await handler(event, data)
    else:
        if event.message and not message_sent:
            logger.warning(f"Rate limit exceeded for chat {chat_id}")
            await event.message.answer("Iltimos 5 daqiqadan so'ng qayta uruning, siz limitdan oshdingiz🫨🤒")
            telegram_limiter.ban_message_sent[chat_id] = True
        return
