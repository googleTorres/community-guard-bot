from datetime import UTC, datetime, timedelta

import pytest

from bot.db import repo
from bot.db.models import EventKind
from bot.db.session import create_engine, create_sessionmaker, init_db

CHAT = -100


@pytest.fixture
async def session():
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    async with create_sessionmaker(engine)() as s:
        yield s
    await engine.dispose()


async def add(session, user_id, referrer=None, verified=True, name=None):
    m, _ = await repo.upsert_member(session, CHAT, user_id, name or f"User {user_id}", None)
    m.referrer_id = referrer
    m.verified = verified
    return m


async def test_upsert_updates_name(session):
    m, created = await repo.upsert_member(session, CHAT, 1, "Old", None)
    assert created
    m2, created2 = await repo.upsert_member(session, CHAT, 1, "New", "new")
    assert not created2 and m2 is m and m.full_name == "New"


async def test_leaderboard_counts_only_verified(session):
    await add(session, 1, name="Alice")
    await add(session, 2, name="Bob")
    await add(session, 10, referrer=1)
    await add(session, 11, referrer=1)
    await add(session, 12, referrer=1, verified=False)  # didn't pass captcha
    await add(session, 13, referrer=2)
    await add(session, 14, referrer=999)  # referrer not tracked
    await session.flush()

    rows = await repo.leaderboard(session, CHAT, limit=10)
    assert [(r.user_id, r.referrals) for r in rows] == [(1, 2), (2, 1), (999, 1)]
    assert rows[0].full_name == "Alice"
    assert rows[2].full_name == "999"
    assert await repo.referral_count(session, CHAT, 1) == 2


async def test_chat_stats(session):
    await add(session, 1)
    await add(session, 2, verified=False)
    for kind in [
        EventKind.JOINED,
        EventKind.JOINED,
        EventKind.CAPTCHA_PASSED,
        EventKind.CAPTCHA_TIMEOUT,
        EventKind.CAPTCHA_FAILED,
        EventKind.SPAM_DELETED,
    ]:
        await repo.log_event(session, CHAT, 1, kind)
    await repo.log_event(session, -999, 1, EventKind.JOINED)  # another chat
    await session.flush()

    s = await repo.chat_stats(session, CHAT, since=datetime.now(UTC) - timedelta(days=1))
    assert (s.members, s.verified, s.joined, s.captcha_passed, s.captcha_failed, s.spam_deleted, s.muted) == (
        2,
        1,
        2,
        1,
        2,
        1,
        0,
    )
