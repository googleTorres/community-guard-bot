import asyncio
import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

log = logging.getLogger(__name__)

# Keep references to fire-and-forget tasks so they aren't garbage-collected mid-flight.
_background: set[asyncio.Task] = set()


def run_in_background(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


async def safe_delete(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError as e:
        log.debug("Could not delete message %s in %s: %s", message_id, chat_id, e)


def delete_later(bot: Bot, chat_id: int, message_id: int, delay: float) -> None:
    async def _job() -> None:
        await asyncio.sleep(delay)
        await safe_delete(bot, chat_id, message_id)

    run_in_background(_job())


async def kick(bot: Bot, chat_id: int, user_id: int, cooldown: timedelta = timedelta(minutes=1)) -> None:
    """Remove a user from the chat. They can rejoin after `cooldown` (Telegram treats bans
    shorter than 30 seconds as permanent, so keep it above that)."""
    try:
        await bot.ban_chat_member(chat_id, user_id, until_date=datetime.now(UTC) + cooldown)
    except TelegramAPIError as e:
        log.warning("Could not kick %s from %s: %s", user_id, chat_id, e)
