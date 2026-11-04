"""Bale bot application entry helpers."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


async def create_bot(token: str):
    """Create Bale Bot instance if library is available."""
    if not token:
        raise ValueError("BALE_TOKEN is empty")
    try:
        from bale import Bot  # python-bale-bot
    except ImportError as exc:
        raise RuntimeError(
            "python-bale-bot is not installed. pip install -r requirements.txt"
        ) from exc
    bot = Bot(token)
    log.info("Bale Bot instance created")
    return bot


def register_handlers(bot, app_ctx: dict) -> None:
    """Register message handlers. Lightweight until gameplay expands."""
    try:
        from bale import Message
    except ImportError:
        log.warning("Bale types unavailable — handlers not registered")
        return

    @bot.listen("message")
    async def on_message(message: Message):
        text = (message.content or "").strip() if hasattr(message, "content") else ""
        if not text:
            return
        lower = text.lower()
        if lower in ("/start", "start", "شروع"):
            gdate = await app_ctx["world"].current_game_date()
            await message.reply(
                f"WORLD WAR\nGame date: {gdate.isoformat()}\n"
                f"Use /status for DB health. Country selection comes next."
            )
        elif lower in ("/status", "status"):
            ok = await app_ctx["db"].health_check()
            mode = app_ctx["settings"].database_mode
            await message.reply(f"DB mode={mode} health={'ok' if ok else 'FAIL'}")
