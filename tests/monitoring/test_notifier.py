"""Tests for monitoring/notifier.py"""
import pytest
from unittest.mock import patch
from monitoring.notifier import Notifier


class TestNotifierSend:
    def test_send_records_to_history(self):
        n = Notifier()
        result = n.send("Test Title", "Test message", level="info")
        assert result is True
        history = n.get_history()
        assert len(history) == 1
        assert history[0]["title"] == "Test Title"
        assert history[0]["message"] == "Test message"
        assert history[0]["level"] == "info"
        assert "timestamp" in history[0]

    def test_send_multiple_records(self):
        n = Notifier()
        n.send("A", "msg1")
        n.send("B", "msg2")
        assert len(n.get_history()) == 2

    def test_send_warning_without_telegram_config(self):
        n = Notifier()
        result = n.send("Warn", "something", level="warning")
        assert result is True  # no telegram configured, returns True

    @patch.object(Notifier, "_send_telegram", return_value=True)
    @patch.object(Notifier, "_send_macos")
    def test_send_warning_with_telegram(self, mock_macos, mock_tg):
        n = Notifier(telegram_token="tok", telegram_chat_id="123")
        result = n.send("Alert", "msg", level="warning")
        assert result is True
        mock_tg.assert_called_once_with("Alert", "msg")

    @patch.object(Notifier, "_send_telegram", return_value=True)
    @patch.object(Notifier, "_send_macos")
    def test_send_critical_triggers_telegram(self, mock_macos, mock_tg):
        n = Notifier(telegram_token="tok", telegram_chat_id="123")
        n.send("Critical", "msg", level="critical")
        mock_tg.assert_called_once()

    @patch.object(Notifier, "_send_telegram")
    @patch.object(Notifier, "_send_macos")
    def test_send_info_triggers_telegram(self, mock_macos, mock_tg):
        n = Notifier(telegram_token="tok", telegram_chat_id="123")
        n.send("Info", "msg", level="info")
        mock_tg.assert_called_once()


class TestNotifierFormat:
    def test_format_trade_with_pnl(self):
        n = Notifier()
        trade = {"side": "LONG", "symbol": "BTCUSDT", "entry_price": 50000.0, "pnl": 120.50}
        result = n.format_trade_notification(trade)
        assert "LONG" in result
        assert "BTCUSDT" in result
        assert "50000.00" in result
        assert "+120.50" in result

    def test_format_trade_without_pnl(self):
        n = Notifier()
        trade = {"side": "SHORT", "symbol": "ETHUSDT", "entry_price": 3000.0}
        result = n.format_trade_notification(trade)
        assert "SHORT" in result
        assert "ETHUSDT" in result
        assert "3000.00" in result
        assert "PnL" not in result

    def test_format_trade_negative_pnl(self):
        n = Notifier()
        trade = {"side": "LONG", "symbol": "BTCUSDT", "entry_price": 50000.0, "pnl": -80.25}
        result = n.format_trade_notification(trade)
        assert "-80.25" in result

    def test_format_daily_summary(self):
        n = Notifier()
        trades = [
            {"pnl": 100},
            {"pnl": -50},
            {"pnl": 200},
        ]
        result = n.format_daily_summary(trades, equity=10250.0)
        assert "Trades: 3" in result
        assert "W/L: 2/1" in result
        assert "+250.00" in result
        assert "10250.00" in result

    def test_format_daily_summary_empty(self):
        n = Notifier()
        result = n.format_daily_summary([], equity=10000.0)
        assert "Trades: 0" in result
        assert "W/L: 0/0" in result


class TestNotifierHistory:
    def test_get_history_returns_copy(self):
        n = Notifier()
        n.send("T", "M")
        h1 = n.get_history()
        h2 = n.get_history()
        assert h1 == h2
        assert h1 is not h2  # different list objects

    def test_modifying_returned_history_does_not_affect_internal(self):
        n = Notifier()
        n.send("T", "M")
        h = n.get_history()
        h.clear()
        assert len(n.get_history()) == 1


class TestMacOSNotification:
    @patch("subprocess.run")
    def test_macos_notification_calls_osascript(self, mock_run):
        n = Notifier()
        n._send_macos("Title", "Body")
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert args[0][0][0] == "osascript"

    @patch("subprocess.run", side_effect=Exception("fail"))
    def test_macos_notification_does_not_crash_on_error(self, mock_run):
        n = Notifier()
        # Should not raise
        n._send_macos("Title", "Body")
