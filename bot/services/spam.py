import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import StrEnum

LINK_RE = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|tg://|\b[a-z0-9-]+\.(com|net|org|io|xyz|ru|me|link|top|app)\b)",
    re.IGNORECASE,
)


class Violation(StrEnum):
    LINK_FROM_NEW_USER = "link"
    FLOOD = "flood"
    BANNED_WORD = "banned_word"


@dataclass(frozen=True)
class SpamConfig:
    new_user_messages: int = 5
    flood_limit: int = 5
    flood_window: float = 10.0
    banned_words: tuple[str, ...] = ()


def contains_link(text: str) -> bool:
    return bool(LINK_RE.search(text))


class SpamGuard:
    """Stateless rules + an in-memory sliding window for flood detection."""

    def __init__(self, config: SpamConfig) -> None:
        self.config = config
        self._words = tuple(w.lower() for w in config.banned_words if w)
        self._history: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def check(
        self,
        chat_id: int,
        user_id: int,
        text: str,
        messages_count: int,
        has_link_entity: bool = False,
        now: float | None = None,
    ) -> Violation | None:
        now = time.monotonic() if now is None else now

        if self._is_flood(chat_id, user_id, now):
            return Violation.FLOOD

        lowered = text.lower()
        if any(word in lowered for word in self._words):
            return Violation.BANNED_WORD

        is_new = messages_count < self.config.new_user_messages
        if is_new and (has_link_entity or contains_link(text)):
            return Violation.LINK_FROM_NEW_USER

        return None

    def _is_flood(self, chat_id: int, user_id: int, now: float) -> bool:
        window = self._history[(chat_id, user_id)]
        window.append(now)
        while window and now - window[0] > self.config.flood_window:
            window.popleft()
        return len(window) > self.config.flood_limit
