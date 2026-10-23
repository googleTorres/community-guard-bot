import random

from bot.handlers.verification import parse_referrer
from bot.services.captcha import CaptchaStore, PendingCaptcha, make_challenge
from bot.services.spam import SpamConfig, SpamGuard, Violation, contains_link


def test_challenge_contains_answer_once():
    rng = random.Random(42)
    for _ in range(200):
        c = make_challenge(rng)
        assert c.options.count(c.answer) == 1
        assert len(set(c.options)) == 4
        assert all(o > 0 for o in c.options)
        a, b = map(int, c.question.split(" + "))
        assert a + b == c.answer


def test_captcha_store_replace_and_pop():
    store = CaptchaStore()
    store.add(1, 2, PendingCaptcha(answer=5, message_id=10))
    store.add(1, 2, PendingCaptcha(answer=7, message_id=11))
    assert len(store) == 1
    assert store.pop(1, 2).answer == 7
    assert store.pop(1, 2) is None


def test_parse_referrer():
    assert parse_referrer("ref:123", 999) == 123
    assert parse_referrer("ref:123", 123) is None  # self-referral
    assert parse_referrer("ref:abc", 1) is None
    assert parse_referrer("promo", 1) is None
    assert parse_referrer(None, 1) is None


def test_contains_link():
    for text in ["visit https://x.co", "t.me/scamgroup", "go to www.site", "cheap-pills.xyz now"]:
        assert contains_link(text), text
    for text in ["hello everyone", "the price is 3.5 today", "e.g. this"]:
        assert not contains_link(text), text


def guard(**kw) -> SpamGuard:
    return SpamGuard(SpamConfig(**kw))


def test_links_blocked_only_for_new_users():
    g = guard(new_user_messages=5)
    assert g.check(1, 1, "join t.me/xyz", messages_count=0, now=0) == Violation.LINK_FROM_NEW_USER
    assert g.check(1, 2, "join t.me/xyz", messages_count=5, now=0) is None
    assert g.check(1, 3, "see this", messages_count=0, has_link_entity=True, now=0) == Violation.LINK_FROM_NEW_USER


def test_banned_words_case_insensitive():
    g = guard(banned_words=("Free Crypto",))
    assert g.check(1, 1, "Get FREE CRYPTO now", messages_count=100, now=0) == Violation.BANNED_WORD


def test_flood_sliding_window():
    g = guard(flood_limit=3, flood_window=10)
    assert [g.check(1, 1, "hi", 100, now=t) for t in (0, 1, 2)] == [None, None, None]
    assert g.check(1, 1, "hi", 100, now=3) == Violation.FLOOD
    # other users are independent
    assert g.check(1, 2, "hi", 100, now=3) is None
    # window has passed
    assert g.check(1, 1, "hi", 100, now=30) is None
