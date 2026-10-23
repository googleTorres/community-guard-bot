from aiogram import Router

from bot.handlers import admin, moderation, private, verification


def setup_routers() -> Router:
    root = Router(name="root")
    # Order matters: moderation has a catch-all group message handler, admin goes before private.
    root.include_routers(verification.router, admin.router, private.router, moderation.router)
    return root
