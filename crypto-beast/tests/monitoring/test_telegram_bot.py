"""Tests for TelegramBot interactive commands."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from monitoring.telegram_bot import TelegramBot


@pytest.fixture
def bot():
    """Create a TelegramBot with no real connections."""
    return TelegramBot(
        token="test-token",
        chat_id="12345",
        db=None,
        exchange=None,
        bot_state={"mode": "PAPER", "starting_capital": 100},
    )


@pytest.fixture
def bot_with_reply(bot):
    """Bot with _reply mocked so we can inspect sent messages."""
    bot._reply = AsyncMock()
    return bot


class TestHelp:
    @pytest.mark.asyncio
    async def test_help_contains_commands(self, bot_with_reply):
        await bot_with_reply._cmd_help([])
        bot_with_reply._reply.assert_called_once()
        text = bot_with_reply._reply.call_args[0][0]
        assert "/status" in text
        assert "/positions" in text
        assert "/pause" in text
        assert "/resume" in text
        assert "/health" in text
        assert "Crypto Beast" in text


class TestPauseResume:
    def test_initial_state_not_paused(self, bot):
        assert bot.is_paused is False

    @pytest.mark.asyncio
    async def test_pause_sets_flag(self, bot_with_reply):
        await bot_with_reply._cmd_pause([])
        assert bot_with_reply.is_paused is True
        text = bot_with_reply._reply.call_args[0][0]
        assert "PAUSED" in text

    @pytest.mark.asyncio
    async def test_resume_clears_flag(self, bot_with_reply):
        bot_with_reply._paused = True
        await bot_with_reply._cmd_resume([])
        assert bot_with_reply.is_paused is False
        text = bot_with_reply._reply.call_args[0][0]
        assert "RESUMED" in text

    @pytest.mark.asyncio
    async def test_pause_resume_cycle(self, bot_with_reply):
        assert bot_with_reply.is_paused is False
        await bot_with_reply._cmd_pause([])
        assert bot_with_reply.is_paused is True
        await bot_with_reply._cmd_resume([])
        assert bot_with_reply.is_paused is False


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_without_db(self, bot_with_reply):
        """Should not crash when db is None."""
        await bot_with_reply._cmd_status([])
        bot_with_reply._reply.assert_called_once()
        text = bot_with_reply._reply.call_args[0][0]
        assert "System Status" in text
        assert "PAPER" in text

    @pytest.mark.asyncio
    async def test_status_shows_paused(self, bot_with_reply):
        bot_with_reply._paused = True
        await bot_with_reply._cmd_status([])
        text = bot_with_reply._reply.call_args[0][0]
        assert "PAUSED" in text


class TestCommandRouting:
    @pytest.mark.asyncio
    async def test_known_command_routed(self, bot_with_reply):
        update = {
            "update_id": 1,
            "message": {
                "text": "/help",
                "chat": {"id": 12345},
            },
        }
        await bot_with_reply._handle_update(update)
        bot_with_reply._reply.assert_called_once()
        text = bot_with_reply._reply.call_args[0][0]
        assert "Crypto Beast" in text

    @pytest.mark.asyncio
    async def test_unknown_command(self, bot_with_reply):
        update = {
            "update_id": 2,
            "message": {
                "text": "/foobar",
                "chat": {"id": 12345},
            },
        }
        await bot_with_reply._handle_update(update)
        bot_with_reply._reply.assert_called_once()
        text = bot_with_reply._reply.call_args[0][0]
        assert "Unknown command" in text

    @pytest.mark.asyncio
    async def test_ignores_unauthorized_chat(self, bot_with_reply):
        update = {
            "update_id": 3,
            "message": {
                "text": "/help",
                "chat": {"id": 99999},
            },
        }
        await bot_with_reply._handle_update(update)
        bot_with_reply._reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_non_command_text(self, bot_with_reply):
        update = {
            "update_id": 4,
            "message": {
                "text": "hello there",
                "chat": {"id": 12345},
            },
        }
        await bot_with_reply._handle_update(update)
        bot_with_reply._reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_with_bot_suffix(self, bot_with_reply):
        """Handle /help@CryptoBeastBot style commands."""
        update = {
            "update_id": 5,
            "message": {
                "text": "/help@CryptoBeastBot",
                "chat": {"id": 12345},
            },
        }
        await bot_with_reply._handle_update(update)
        bot_with_reply._reply.assert_called_once()
        text = bot_with_reply._reply.call_args[0][0]
        assert "Crypto Beast" in text


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_no_db_no_exchange(self, bot_with_reply):
        await bot_with_reply._cmd_health([])
        text = bot_with_reply._reply.call_args[0][0]
        assert "Database: N/A" in text
        assert "Exchange: N/A" in text
        assert "ACTIVE" in text


class TestBalance:
    @pytest.mark.asyncio
    async def test_balance_no_exchange(self, bot_with_reply):
        await bot_with_reply._cmd_balance([])
        text = bot_with_reply._reply.call_args[0][0]
        assert "Exchange not available" in text


class TestPositions:
    @pytest.mark.asyncio
    async def test_positions_no_db(self, bot_with_reply):
        await bot_with_reply._cmd_positions([])
        text = bot_with_reply._reply.call_args[0][0]
        assert "DB not available" in text


class TestClose:
    @pytest.mark.asyncio
    async def test_close_no_args(self, bot_with_reply):
        await bot_with_reply._cmd_close([])
        text = bot_with_reply._reply.call_args[0][0]
        assert "Usage" in text
