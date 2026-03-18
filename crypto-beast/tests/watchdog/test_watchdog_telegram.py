"""Tests for watchdog Telegram sender."""
from unittest.mock import patch, MagicMock
import pytest
from watchdog_telegram import WatchdogTelegram

class TestWatchdogTelegram:
    def test_init_with_credentials(self):
        tg = WatchdogTelegram("test_token", "test_chat")
        assert tg.token == "test_token"
        assert tg.chat_id == "test_chat"

    def test_init_without_credentials(self):
        tg = WatchdogTelegram("", "")
        assert tg.enabled is False

    def test_enabled_with_both_credentials(self):
        tg = WatchdogTelegram("tok", "chat")
        assert tg.enabled is True

    @patch("watchdog_telegram.requests.post")
    def test_send_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        tg = WatchdogTelegram("tok", "chat")
        result = tg.send("[L1] Bot restarted")
        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["chat_id"] == "chat"
        assert "[L1] Bot restarted" in call_args[1]["json"]["text"]

    @patch("watchdog_telegram.requests.post")
    def test_send_markdown_fallback_to_plain(self, mock_post):
        mock_post.side_effect = [
            MagicMock(status_code=400),
            MagicMock(status_code=200),
        ]
        tg = WatchdogTelegram("tok", "chat")
        result = tg.send("Message with $pecial chars")
        assert result is True
        assert mock_post.call_count == 2

    @patch("watchdog_telegram.requests.post")
    def test_send_when_disabled(self, mock_post):
        tg = WatchdogTelegram("", "")
        result = tg.send("test")
        assert result is False
        mock_post.assert_not_called()

    @patch("watchdog_telegram.requests.post")
    def test_send_network_error(self, mock_post):
        mock_post.side_effect = Exception("Network error")
        tg = WatchdogTelegram("tok", "chat")
        result = tg.send("test")
        assert result is False
