"""End-to-end handler flow with a mocked Telegram API."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import CallbackQuery, Chat, ChatInviteLink, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, User

from bot.db import repo
from bot.db.session import create_engine, create_sessionmaker, init_db
from bot.handlers.verification import CaptchaCb, on_answer, on_join
from bot.services.captcha import CaptchaStore

GROUP = -1001
REFERRER = User(id=1, is_bot=False, first_name="Alice")
NEWBIE = User(id=2, is_bot=False, first_name="Bob")
CHAT = Chat(id=GROUP, type="supergroup", title="Test")


@pytest.fixture
async def env():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sm = create_sessionmaker(engine)
    bot = AsyncMock()
    bot.send_message.return_value = MagicMock(message_id=555)
    bot.get_chat.return_value = MagicMock(permissions=None)
    yield SimpleNamespace(
        bot=bot, sm=sm, store=CaptchaStore(), settings=SimpleNamespace(group_id=GROUP, captcha_timeout=120)
    )
    await engine.dispose()


def join_event(link_name: str | None) -> ChatMemberUpdated:
    link = None
    if link_name:
        link = ChatInviteLink(
            invite_link="https://t.me/+abc",
            creator=REFERRER,
            creates_join_request=False,
            is_primary=False,
            is_revoked=False,
            name=link_name,
        )
    return ChatMemberUpdated(
        chat=CHAT,
        from_user=NEWBIE,
        date=datetime.now(UTC),
        old_chat_member=ChatMemberLeft(user=NEWBIE),
        new_chat_member=ChatMemberMember(user=NEWBIE),
        invite_link=link,
    )


async def run_join(env, link_name):
    async with env.sm() as s:
        await on_join(join_event(link_name), env.bot, s, env.settings, env.store, env.sm)
        await s.commit()


def callback(env, value: int, from_user: User = NEWBIE) -> CallbackQuery:
    msg = MagicMock(chat=CHAT)
    cb = CallbackQuery(id="1", from_user=from_user, chat_instance="x", data="x").as_(env.bot)
    object.__setattr__(cb, "message", msg)
    return cb


async def run_answer(env, value, from_user=NEWBIE):
    async with env.sm() as s:
        await on_answer(
            callback(env, value, from_user),
            CaptchaCb(user_id=NEWBIE.id, value=value),
            env.bot,
            s,
            env.settings,
            env.store,
        )
        await s.commit()


async def test_join_restricts_and_sends_captcha(env):
    await run_join(env, "ref:1")
    env.bot.restrict_chat_member.assert_awaited_once()
    assert env.store.get(GROUP, NEWBIE.id) is not None
    async with env.sm() as s:
        m = await repo.get_member(s, GROUP, NEWBIE.id)
        assert m.referrer_id == 1 and not m.verified
    env.store.pop(GROUP, NEWBIE.id)  # cancel timeout task


async def test_correct_answer_verifies_and_credits_referrer(env):
    async with env.sm() as s:
        alice, _ = await repo.upsert_member(s, GROUP, REFERRER.id, "Alice", None)
        alice.verified = True
        await s.commit()

    await run_join(env, "ref:1")
    answer = env.store.get(GROUP, NEWBIE.id).answer
    await run_answer(env, answer)

    assert env.store.get(GROUP, NEWBIE.id) is None
    env.bot.ban_chat_member.assert_not_awaited()
    async with env.sm() as s:
        assert (await repo.get_member(s, GROUP, NEWBIE.id)).verified
        assert await repo.referral_count(s, GROUP, REFERRER.id) == 1
    # referrer got a private notification
    assert any(c.args[0] == REFERRER.id for c in env.bot.send_message.await_args_list)


async def test_wrong_answer_kicks(env):
    await run_join(env, None)
    answer = env.store.get(GROUP, NEWBIE.id).answer
    await run_answer(env, answer + 100)
    env.bot.ban_chat_member.assert_awaited_once()
    async with env.sm() as s:
        assert not (await repo.get_member(s, GROUP, NEWBIE.id)).verified


async def test_other_user_cannot_solve(env):
    await run_join(env, None)
    answer = env.store.get(GROUP, NEWBIE.id).answer
    await run_answer(env, answer, from_user=REFERRER)
    assert env.store.get(GROUP, NEWBIE.id) is not None  # still pending
    env.store.pop(GROUP, NEWBIE.id)


async def test_rejoin_does_not_change_referrer(env):
    await run_join(env, "ref:1")
    env.store.pop(GROUP, NEWBIE.id)
    await run_join(env, "ref:777")
    env.store.pop(GROUP, NEWBIE.id)
    async with env.sm() as s:
        assert (await repo.get_member(s, GROUP, NEWBIE.id)).referrer_id == 1
