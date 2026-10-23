"""Anti-spam for group messages: links from new users, flood, banned words."""

import logging
from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType, MessageEntityType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ChatPermissions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import EventKind
from bot.services.admins import AdminCache
from bot.services.spam import SpamGuard, Violation
from bot.utils import delete_later, safe_delete

log = logging.getLogger(__name__)
router = Router(name="moderation")
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))

LINK_ENTITIES = {MessageEntityType.URL, MessageEntityType.TEXT_LINK}
REASONS = {
    Violation.LINK_FROM_NEW_USER: "new members can't post links yet",
    Violation.FLOOD: "too many messages, slow down",
    Violation.BANNED_WORD: "message contains a banned word",
}


@router.message(F.new_chat_members | F.left_chat_member)
async def delete_service_messages(message: Message, bot: Bot, settings: Settings) -> None:
    """Remove 'X joined / X left' noise — the captcha message already covers joins."""
    if message.chat.id == settings.group_id:
        await safe_delete(bot, message.chat.id, message.message_id)


@router.message()
async def moderate(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    spam_guard: SpamGuard,
    admin_cache: AdminCache,
) -> None:
    if message.chat.id != settings.group_id or message.from_user is None or message.sender_chat:
        return  # other chats, channel posts and anonymous admins are not moderated
    user = message.from_user
    if user.is_bot or await admin_cache.is_admin(bot, message.chat.id, user.id):
        return

    member, created = await repo.upsert_member(session, message.chat.id, user.id, user.full_name, user.username)
    if created:
        # No join event seen: the user was in the group before the bot was added.
        # Treat them as an established member instead of a newcomer.
        member.verified = True
        member.messages_count = settings.new_user_messages

    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    has_link = any(e.type in LINK_ENTITIES for e in entities)

    violation = spam_guard.check(message.chat.id, user.id, text, member.messages_count, has_link)
    if violation is None:
        member.messages_count += 1
        return

    await safe_delete(bot, message.chat.id, message.message_id)
    await repo.log_event(session, message.chat.id, user.id, EventKind.SPAM_DELETED)
    member.strikes += 1

    if member.strikes >= settings.max_strikes:
        member.strikes = 0
        until = datetime.now(UTC) + timedelta(minutes=settings.mute_minutes)
        try:
            await bot.restrict_chat_member(
                message.chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until
            )
        except TelegramAPIError as e:
            log.warning("Could not mute %s: %s", user.id, e)
            return
        await repo.log_event(session, message.chat.id, user.id, EventKind.MUTED)
        text_out = f"🔇 {user.mention_html()} muted for {settings.mute_minutes} min ({REASONS[violation]})."
    else:
        left = settings.max_strikes - member.strikes
        text_out = f"⚠️ {user.mention_html()}, message removed: {REASONS[violation]}. Warnings left before mute: {left}."

    notice = await bot.send_message(message.chat.id, text_out)
    delete_later(bot, message.chat.id, notice.message_id, 20)
