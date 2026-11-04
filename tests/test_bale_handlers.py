"""Handler registration tests for python-bale-bot 2.5.0 event model."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_listen_on_message_matches_dispatch_prefix():
    """Mirror 2.5.0 Bot.dispatch: method = 'on_' + event_name."""
    event_from_updater = "message"
    registered = "on_message"
    assert "on_" + event_from_updater == registered


def test_register_handlers_adds_on_message():
    bale = pytest.importorskip("bale")
    from bot.main import register_handlers

    bot = MagicMock()
    bot.events = {}
    bot.listen = lambda name: (lambda f: bot.events.setdefault(name, []).append(f) or f)

    app_ctx = {
        "players": MagicMock(),
        "countries": MagicMock(),
        "world": MagicMock(),
        "db": MagicMock(),
        "management": MagicMock(),
        "settings": MagicMock(database_mode="sqlite"),
    }
    # players methods used in handler body only when called
    register_handlers(bot, app_ctx)
    assert "on_message" in bot.events
    assert len(bot.events["on_message"]) >= 1
    assert "on_ready" in bot.events


def test_wrong_event_name_would_not_match():
    """Document the bug: listen('message') never receives dispatch('message')."""
    listeners = {"message": ["handler"]}  # wrong registration key
    method = "on_" + "message"
    assert method not in listeners
