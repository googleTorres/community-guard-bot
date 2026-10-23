import asyncio
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Challenge:
    question: str
    answer: int
    options: list[int]


def make_challenge(rng: random.Random | None = None, n_options: int = 4) -> Challenge:
    """Simple arithmetic captcha with shuffled multiple-choice answers."""
    rng = rng or random.Random()
    a, b = rng.randint(1, 9), rng.randint(1, 9)
    answer = a + b
    options = {answer}
    while len(options) < n_options:
        candidate = answer + rng.randint(-5, 5)
        if candidate > 0:
            options.add(candidate)
    shuffled = list(options)
    rng.shuffle(shuffled)
    return Challenge(question=f"{a} + {b}", answer=answer, options=shuffled)


@dataclass
class PendingCaptcha:
    answer: int
    message_id: int
    timeout_task: asyncio.Task | None = field(default=None, repr=False)


class CaptchaStore:
    """In-memory storage of unsolved captchas, keyed by (chat_id, user_id).

    Pending captchas don't survive a restart: users who joined right before a restart
    stay restricted until an admin lets them in or they rejoin. Swap for Redis if that matters.
    """

    def __init__(self) -> None:
        self._items: dict[tuple[int, int], PendingCaptcha] = {}

    def add(self, chat_id: int, user_id: int, pending: PendingCaptcha) -> None:
        old = self._items.pop((chat_id, user_id), None)
        if old and old.timeout_task:
            old.timeout_task.cancel()
        self._items[(chat_id, user_id)] = pending

    def get(self, chat_id: int, user_id: int) -> PendingCaptcha | None:
        return self._items.get((chat_id, user_id))

    def pop(self, chat_id: int, user_id: int, cancel_timeout: bool = True) -> PendingCaptcha | None:
        pending = self._items.pop((chat_id, user_id), None)
        if pending and cancel_timeout and pending.timeout_task:
            pending.timeout_task.cancel()
        return pending

    def __len__(self) -> int:
        return len(self._items)
