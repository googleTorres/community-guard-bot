"""New member verification: restrict on join, solve a captcha to get in."""

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import JOIN_TRANSITION, ChatMemberUpdatedFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, ChatMemberUpdated, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.db import repo
from bot.db.models import EventKind
from bot.services.captcha import CaptchaStore, PendingCaptcha, make_challenge
from bot.utils import delete_later, kick, run_in_background, safe_delete

log = logging.getLogger(__name__)
router = Router(name="verification")

MUTED = ChatPermissions(can_send_messages=False)
# Used only if the chat has no default permissions set
DEFAULT_PERMISSIONS = ChatPermissions(
    can_send_messages=True,
    can_send_audios=True,
    can_send_documents=True,
    can_send_photos=True,
    can_send_videos=True,
    can_send_video_notes=True,
    can_send_voice_notes=True,
    can_send_polls=True,
    can_send_other_messages=True,
    can_add_web_page_previews=True,
)

REF_PREFIX = "ref:"


class CaptchaCb(CallbackData, prefix="cap"):
    user_id: int
    value: int


def parse_referrer(link_name: str | None, joined_user_id: int) -> int | None:
    """Invite links created by the bot are named 'ref:<user_id>'."""
    if not link_name or not link_name.startswith(REF_PREFIX):
        return None
    try:
        referrer = int(link_name.removeprefix(REF_PREFIX))
    except ValueError:
        return None
    return None if referrer == joined_user_id else referrer


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_join(
    event: ChatMemberUpdated,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    captcha_store: CaptchaStore,
    sessionmaker: async_sessionmaker,
) -> None:
    if event.chat.id != settings.group_id:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return

    member, created = await repo.upsert_member(session, event.chat.id, user.id, user.full_name, user.username)
    await repo.log_event(session, event.chat.id, user.id, EventKind.JOINED)

    # Credit referrals only on the first join, so leave/rejoin can't be farmed
    if created:
        link_name = event.invite_link.name if event.invite_link else None
        member.referrer_id = parse_referrer(link_name, user.id)

    if member.verified:
        return  # already passed the captcha before

    try:
        await bot.restrict_chat_member(event.chat.id, user.id, permissions=MUTED)
    except TelegramAPIError as e:
        log.error("Cannot restrict %s — is the bot an admin with 'Ban users' right? %s", user.id, e)
        return

    challenge = make_challenge()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(opt), callback_data=CaptchaCb(user_id=user.id, value=opt).pack())
                for opt in challenge.options
            ]
        ]
    )
    msg = await bot.send_message(
        event.chat.id,
        f"👋 Welcome, {user.mention_html()}!\n"
        f"To prove you're human, solve: <b>{challenge.question} = ?</b>\n"
        f"You have {settings.captcha_timeout} seconds.",
        reply_markup=keyboard,
    )

    pending = PendingCaptcha(answer=challenge.answer, message_id=msg.message_id)
    pending.timeout_task = run_in_background(
        _captcha_timeout(bot, event.chat.id, user.id, settings.captcha_timeout, captcha_store, sessionmaker)
    )
    captcha_store.add(event.chat.id, user.id, pending)


async def _captcha_timeout(
    bot: Bot,
    chat_id: int,
    user_id: int,
    delay: int,
    store: CaptchaStore,
    sessionmaker: async_sessionmaker,
) -> None:
    await asyncio.sleep(delay)
    pending = store.pop(chat_id, user_id, cancel_timeout=False)
    if pending is None:
        return
    await safe_delete(bot, chat_id, pending.message_id)
    await kick(bot, chat_id, user_id)
    async with sessionmaker() as session:
        await repo.log_event(session, chat_id, user_id, EventKind.CAPTCHA_TIMEOUT)
        await session.commit()


@router.callback_query(CaptchaCb.filter(), F.message)
async def on_answer(
    cb: CallbackQuery,
    callback_data: CaptchaCb,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    captcha_store: CaptchaStore,
) -> None:
    chat_id = cb.message.chat.id
    user = cb.from_user

    if user.id != callback_data.user_id:
        await cb.answer("This captcha is not for you 🙂", show_alert=True)
        return

    pending = captcha_store.pop(chat_id, user.id)
    if pending is None:
        await cb.answer("This captcha has expired.")
        return
    await safe_delete(bot, chat_id, pending.message_id)

    if callback_data.value != pending.answer:
        await kick(bot, chat_id, user.id)
        await repo.log_event(session, chat_id, user.id, EventKind.CAPTCHA_FAILED)
        await cb.answer("Wrong answer. You can try to join again in a minute.", show_alert=True)
        return

    chat = await bot.get_chat(chat_id)
    await bot.restrict_chat_member(chat_id, user.id, permissions=chat.permissions or DEFAULT_PERMISSIONS)

    member, _ = await repo.upsert_member(session, chat_id, user.id, user.full_name, user.username)
    member.verified = True
    await repo.log_event(session, chat_id, user.id, EventKind.CAPTCHA_PASSED)
    await cb.answer("✅ Verified, welcome!")

    welcome = await bot.send_message(chat_id, f"✅ {user.mention_html()} is verified. Welcome to the community!")
    delete_later(bot, chat_id, welcome.message_id, 60)

    if member.referrer_id:
        await session.flush()
        total = await repo.referral_count(session, chat_id, member.referrer_id)
        try:
            await bot.send_message(
                member.referrer_id,
                f"🎉 <b>{escape(user.full_name)}</b> joined with your invite link!\n"
                f"Your total referrals: <b>{total}</b>",
            )
        except TelegramAPIError:
            pass  # referrer hasn't started the bot in private — that's fine
