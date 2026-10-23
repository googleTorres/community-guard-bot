"""Private chat with the bot: personal invite links, leaderboard, own stats."""

from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.handlers.verification import REF_PREFIX

router = Router(name="private")
router.message.filter(F.chat.type == ChatType.PRIVATE)

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
NOT_MEMBER = "You need to be a verified member of the community to use this. Join the group and pass the captcha first."


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(
        "👋 Hi! I protect the community from spam and reward people who bring new members.\n\n"
        "/invite — get your personal invite link\n"
        "/me — your referral stats\n"
        "/top — referral leaderboard"
    )


@router.message(Command("invite"))
async def invite(message: Message, bot: Bot, session: AsyncSession, settings: Settings) -> None:
    member = await repo.get_member(session, settings.group_id, message.from_user.id)
    if member is None or not member.verified:
        await message.answer(NOT_MEMBER)
        return

    if member.invite_link is None:
        link = await bot.create_chat_invite_link(settings.group_id, name=f"{REF_PREFIX}{member.user_id}")
        member.invite_link = link.invite_link

    await message.answer(
        "🔗 Your personal invite link:\n"
        f"{member.invite_link}\n\n"
        "Every person who joins with it and passes verification counts as your referral."
    )


@router.message(Command("me"))
async def me(message: Message, session: AsyncSession, settings: Settings) -> None:
    member = await repo.get_member(session, settings.group_id, message.from_user.id)
    if member is None or not member.verified:
        await message.answer(NOT_MEMBER)
        return
    count = await repo.referral_count(session, settings.group_id, member.user_id)
    await message.answer(f"📊 You've brought <b>{count}</b> verified member(s). Get your link with /invite")


@router.message(Command("top"))
async def top(message: Message, session: AsyncSession, settings: Settings) -> None:
    rows = await repo.leaderboard(session, settings.group_id, settings.leaderboard_size)
    if not rows:
        await message.answer("🏆 No referrals yet. Be the first — /invite")
        return
    lines = ["🏆 <b>Top referrers</b>\n"]
    for i, row in enumerate(rows, start=1):
        name = f"@{row.username}" if row.username else escape(row.full_name)
        lines.append(f"{MEDALS.get(i, f'{i}.')} {name} — {row.referrals}")
    await message.answer("\n".join(lines))
