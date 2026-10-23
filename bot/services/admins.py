import time

from aiogram import Bot


class AdminCache:
    """Caches chat administrators to avoid an API call on every message."""

    def __init__(self, ttl: float = 300.0) -> None:
        self.ttl = ttl
        self._cache: dict[int, tuple[float, set[int]]] = {}

    async def is_admin(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        cached = self._cache.get(chat_id)
        if cached is None or time.monotonic() - cached[0] > self.ttl:
            admins = await bot.get_chat_administrators(chat_id)
            cached = (time.monotonic(), {a.user.id for a in admins})
            self._cache[chat_id] = cached
        return user_id in cached[1]
