import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from bot.config import get_settings
from bot.db.session import create_engine, create_sessionmaker, init_db
from bot.handlers import setup_routers
from bot.middlewares.db import DbSessionMiddleware
from bot.services.admins import AdminCache
from bot.services.captcha import CaptchaStore
from bot.services.spam import SpamConfig, SpamGuard

PRIVATE_COMMANDS = [
    BotCommand(command="invite", description="Get your personal invite link"),
    BotCommand(command="me", description="Your referral stats"),
    BotCommand(command="top", description="Referral leaderboard"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()

    engine = create_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = create_sessionmaker(engine)

    bot = Bot(settings.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(
        settings=settings,
        sessionmaker=sessionmaker,
        captcha_store=CaptchaStore(),
        admin_cache=AdminCache(),
        spam_guard=SpamGuard(
            SpamConfig(
                new_user_messages=settings.new_user_messages,
                flood_limit=settings.flood_limit,
                flood_window=settings.flood_window,
                banned_words=tuple(settings.banned_words),
            )
        ),
    )
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(setup_routers())

    await bot.set_my_commands(PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    try:
        # chat_member updates must be requested explicitly — resolve_used_update_types() does that
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
