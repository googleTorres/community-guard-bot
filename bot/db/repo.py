from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Event, EventKind, Member


async def get_member(session: AsyncSession, chat_id: int, user_id: int) -> Member | None:
    return await session.get(Member, (chat_id, user_id))


async def upsert_member(
    session: AsyncSession, chat_id: int, user_id: int, full_name: str, username: str | None
) -> tuple[Member, bool]:
    """Return (member, created). Updates the display name if the member already exists."""
    member = await get_member(session, chat_id, user_id)
    if member is None:
        member = Member(chat_id=chat_id, user_id=user_id, full_name=full_name, username=username)
        session.add(member)
        await session.flush()
        return member, True
    member.full_name = full_name
    member.username = username
    return member, False


async def log_event(session: AsyncSession, chat_id: int, user_id: int, kind: str) -> None:
    session.add(Event(chat_id=chat_id, user_id=user_id, kind=kind))


async def referral_count(session: AsyncSession, chat_id: int, user_id: int) -> int:
    stmt = select(func.count()).where(
        Member.chat_id == chat_id, Member.referrer_id == user_id, Member.verified.is_(True)
    )
    return (await session.execute(stmt)).scalar_one()


@dataclass(frozen=True)
class LeaderboardRow:
    user_id: int
    full_name: str
    username: str | None
    referrals: int


async def leaderboard(session: AsyncSession, chat_id: int, limit: int = 10) -> list[LeaderboardRow]:
    counts = (
        select(Member.referrer_id.label("uid"), func.count().label("cnt"))
        .where(
            Member.chat_id == chat_id,
            Member.verified.is_(True),
            Member.referrer_id.is_not(None),
        )
        .group_by(Member.referrer_id)
        .subquery()
    )
    stmt = (
        select(counts.c.uid, counts.c.cnt, Member.full_name, Member.username)
        .outerjoin(Member, (Member.chat_id == chat_id) & (Member.user_id == counts.c.uid))
        .order_by(counts.c.cnt.desc(), counts.c.uid)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        LeaderboardRow(user_id=r.uid, full_name=r.full_name or str(r.uid), username=r.username, referrals=r.cnt)
        for r in rows
    ]


@dataclass(frozen=True)
class ChatStats:
    members: int
    verified: int
    joined: int
    captcha_passed: int
    captcha_failed: int
    spam_deleted: int
    muted: int


async def chat_stats(session: AsyncSession, chat_id: int, since: datetime) -> ChatStats:
    members = (await session.execute(select(func.count()).where(Member.chat_id == chat_id))).scalar_one()
    verified = (
        await session.execute(select(func.count()).where(Member.chat_id == chat_id, Member.verified.is_(True)))
    ).scalar_one()

    stmt = (
        select(Event.kind, func.count()).where(Event.chat_id == chat_id, Event.created_at >= since).group_by(Event.kind)
    )
    by_kind = {kind: cnt for kind, cnt in (await session.execute(stmt)).all()}
    return ChatStats(
        members=members,
        verified=verified,
        joined=by_kind.get(EventKind.JOINED, 0),
        captcha_passed=by_kind.get(EventKind.CAPTCHA_PASSED, 0),
        captcha_failed=by_kind.get(EventKind.CAPTCHA_FAILED, 0) + by_kind.get(EventKind.CAPTCHA_TIMEOUT, 0),
        spam_deleted=by_kind.get(EventKind.SPAM_DELETED, 0),
        muted=by_kind.get(EventKind.MUTED, 0),
    )
