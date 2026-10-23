from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Member(Base):
    """A user in a group the bot protects."""

    __tablename__ = "members"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(256), default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified: Mapped[bool] = mapped_column(default=False)

    # Who invited this member (user_id of the referrer), credited only after verification
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # Personal invite link this member shares with others
    invite_link: Mapped[str | None] = mapped_column(String(128), nullable=True)

    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    strikes: Mapped[int] = mapped_column(Integer, default=0)


class Event(Base):
    """Audit log used for admin statistics."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now())

    __table_args__ = (Index("ix_events_chat_kind_created", "chat_id", "kind", "created_at"),)


class EventKind:
    JOINED = "joined"
    CAPTCHA_PASSED = "captcha_passed"
    CAPTCHA_FAILED = "captcha_failed"
    CAPTCHA_TIMEOUT = "captcha_timeout"
    SPAM_DELETED = "spam_deleted"
    MUTED = "muted"
