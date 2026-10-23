"""Admin-only commands in private chat."""

from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo

router = Router(name="admin")
router.message.filter(F.chat.type == ChatType.PRIVATE)


@router.message(Command("stats"))
async def stats(message: Message, command: CommandObject, session: AsyncSession, settings: Settings) -> None:
    if message.from_user.id not in settings.admin_ids:
        return  # silently ignore non-admins

    days = int(command.args) if command.args and command.args.isdigit() else 7
    since = datetime.now(UTC) - timedelta(days=days)
    s = await repo.chat_stats(session, settings.group_id, since)
    attempts = s.captcha_passed + s.captcha_failed
    pass_rate = f"{s.captcha_passed / attempts:.0%}" if attempts else "—"

    await message.answer(
        f"📈 <b>Community stats — last {days} day(s)</b>\n\n"
        f"👥 Members tracked: {s.members} (verified: {s.verified})\n"
        f"➕ Joins: {s.joined}\n"
        f"✅ Captcha passed: {s.captcha_passed}\n"
        f"🤖 Bots / failed captcha: {s.captcha_failed} (pass rate {pass_rate})\n"
        f"🗑 Spam messages removed: {s.spam_deleted}\n"
        f"🔇 Mutes: {s.muted}\n\n"
        "Use /stats 30 for a different period."
    )
