# Community Guard Bot

A Telegram bot that keeps a community clean and helps it grow:
**captcha verification for new members, anti-spam moderation, and a referral program with a leaderboard.**

Built for crypto/Web3 communities, online courses and any group that suffers from bots and spam.

## Features

**🛡 Verification**
- New members are muted on join and get a one-tap math captcha
- Wrong answer or no answer within the timeout → removed (can retry after a minute)
- Service "X joined / X left" messages are cleaned up automatically

**🚫 Anti-spam**
- Links (including `t.me/` invites and hidden text links) are blocked for new members until they've sent a few normal messages
- Flood protection with a sliding window (e.g. max 5 messages per 10 seconds)
- Configurable banned-words list
- Strike system: warnings → temporary mute after N violations
- Admins are never moderated

**🏆 Referrals**
- Every verified member gets a personal invite link (`/invite`)
- A referral counts only after the invited person **passes the captcha**, so bot farms don't inflate numbers
- Leave-and-rejoin can't be used to reassign or farm referrals
- Referrers get a private notification for each new member
- `/top` leaderboard and `/me` personal stats

**📈 Admin stats**
- `/stats [days]` — joins, captcha pass rate, removed spam, mutes

## Tech stack

Python 3.13 · aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL / SQLite · Docker Compose · pytest

```
bot/
├── handlers/      # verification, moderation, private commands, admin
├── services/      # captcha, spam rules, admin cache — pure logic, unit-tested
├── db/            # models, session, repository queries
├── middlewares/   # DB session per update
└── config.py      # all settings from environment variables
tests/             # unit tests + end-to-end handler flow with mocked Telegram API
```

## Quick start

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Add the bot to your group as **admin** with rights: *Delete messages*, *Ban users*, *Invite users via link*.
3. Configure:
   ```bash
   cp .env.example .env   # set BOT_TOKEN, GROUP_ID, ADMIN_IDS
   ```
4. Run with Docker (PostgreSQL included):
   ```bash
   docker compose up -d --build
   ```
   Or locally with SQLite:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m bot
   ```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | Token from @BotFather |
| `GROUP_ID` | — | Group to protect (`-100…`) |
| `ADMIN_IDS` | `[]` | User IDs allowed to use `/stats` |
| `DATABASE_URL` | SQLite file | Any SQLAlchemy async URL |
| `CAPTCHA_TIMEOUT` | `120` | Seconds to solve the captcha |
| `NEW_USER_MESSAGES` | `5` | Messages before a member may post links |
| `FLOOD_LIMIT` / `FLOOD_WINDOW` | `5` / `10` | Max messages per window (seconds) |
| `MAX_STRIKES` / `MUTE_MINUTES` | `3` / `60` | Violations before mute, mute length |
| `BANNED_WORDS` | `[]` | JSON list, case-insensitive |
| `LEADERBOARD_SIZE` | `10` | Rows in `/top` |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Possible extensions

Multi-group support from one instance · web admin panel · Redis for captcha state · AI-based spam detection · rewards for top referrers (roles, Telegram Stars, crypto payouts) · webhooks instead of polling.
