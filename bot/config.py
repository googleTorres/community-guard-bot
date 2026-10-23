from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: SecretStr
    group_id: int
    admin_ids: list[int] = []
    database_url: str = "sqlite+aiosqlite:///bot.db"

    # Verification
    captcha_timeout: int = 120  # seconds to solve the captcha before being removed

    # Anti-spam
    new_user_messages: int = 5  # links are blocked until a member has sent this many messages
    flood_limit: int = 5  # max messages ...
    flood_window: int = 10  # ... per this many seconds
    max_strikes: int = 3  # violations before a mute
    mute_minutes: int = 60
    banned_words: list[str] = []

    # Referrals
    leaderboard_size: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
