"""Tests for event router and L1 classification."""
import time
from unittest.mock import MagicMock, patch
import pytest
from watchdog_event_router import EventRouter, EventLevel

class TestEventClassification:
    def setup_method(self):
        self.router = EventRouter(
            telegram=MagicMock(),
            state=MagicMock(),
            max_restarts=3,
            restart_window=600,
        )

    def test_disk_io_error_is_l1(self):
        level, action = self.router.classify("ERROR | disk I/O error writing to DB")
        assert level == EventLevel.L1
        assert action == "kill_zombies_restart"

    def test_connection_error_is_l1(self):
        level, action = self.router.classify("ERROR | ConnectionError: Remote host closed")
        assert level == EventLevel.L1
        assert action == "wait_and_retry"

    def test_margin_insufficient_is_l1(self):
        level, action = self.router.classify("WARNING | Margin is insufficient")
        assert level == EventLevel.L1
        assert action == "notify_only"

    def test_halt_daily_loss_is_l1(self):
        level, action = self.router.classify("WARNING | HALT: daily loss 10% >= 10%")
        assert level == EventLevel.L1
        assert action == "notify_only"

    def test_rate_limit_is_l1(self):
        level, action = self.router.classify("WARNING | Rate limit exceeded")
        assert level == EventLevel.L1
        assert action == "notify_only"

    def test_cancel_orders_known_bug_ignored(self):
        level, action = self.router.classify("ERROR | cancelAllOrders() requires a symbol argument")
        assert level == EventLevel.L1
        assert action == "ignore"

    def test_known_binance_error_is_l1(self):
        level, action = self.router.classify('ERROR | Order failed: {"code":-4164,"msg":"notional"}')
        assert level == EventLevel.L1
        assert action == "notify_only"

    def test_unknown_binance_error_is_l2(self):
        level, action = self.router.classify('ERROR | Order failed: {"code":-9999,"msg":"unknown"}')
        assert level == EventLevel.L2
        assert action == "claude_fix"

    def test_unknown_error_is_l2(self):
        level, action = self.router.classify("ERROR | NoneType has no attribute 'get'")
        assert level == EventLevel.L2
        assert action == "claude_fix"

    def test_unknown_critical_is_l2(self):
        level, action = self.router.classify("CRITICAL | Core module down: executor")
        assert level == EventLevel.L2
        assert action == "claude_fix"

    def test_info_line_ignored(self):
        level, action = self.router.classify("INFO | Cycle 100 completed")
        assert level == EventLevel.IGNORE
        assert action == "none"

    def test_debug_line_ignored(self):
        level, action = self.router.classify("DEBUG | Signal generated")
        assert level == EventLevel.IGNORE
        assert action == "none"

class TestRestartTracking:
    def setup_method(self):
        self.router = EventRouter(
            telegram=MagicMock(), state=MagicMock(),
            max_restarts=3, restart_window=600,
        )

    def test_under_restart_limit(self):
        self.router.record_restart()
        self.router.record_restart()
        assert not self.router.restart_limit_exceeded()

    def test_at_restart_limit(self):
        for _ in range(3):
            self.router.record_restart()
        assert self.router.restart_limit_exceeded()

    def test_old_restarts_expire(self):
        self.router._restart_window = 1
        for _ in range(3):
            self.router.record_restart()
        time.sleep(1.1)
        assert not self.router.restart_limit_exceeded()

class TestL1Handlers:
    def setup_method(self):
        self.telegram = MagicMock()
        self.state = MagicMock()
        self.router = EventRouter(
            telegram=self.telegram, state=self.state,
            max_restarts=3, restart_window=600,
        )

    @patch("watchdog_event_router.subprocess.run")
    def test_kill_zombies(self, mock_run):
        mock_run.return_value = MagicMock(stdout="12345\n12346\n", returncode=0)
        killed = self.router.kill_zombie_processes("crypto_system")
        assert killed >= 0

    def test_notify_only_sends_telegram(self):
        self.router.handle_l1("notify_only", "Margin is insufficient")
        self.telegram.send.assert_called_once()
        call_text = self.telegram.send.call_args[0][0]
        assert "[L1]" in call_text
