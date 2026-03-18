"""Tests for main watchdog daemon."""
import json
import os
import signal
import subprocess
import time
from threading import Event
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from crypto_guardian import WatchdogDaemon


@pytest.fixture
def mock_deps(tmp_path):
    """Create a WatchdogDaemon with mocked dependencies."""
    tmp_dir = str(tmp_path)
    state_path = os.path.join(tmp_dir, "watchdog.state")
    log_path = os.path.join(tmp_dir, "bot.log")
    os.makedirs(os.path.join(tmp_dir, "logs"), exist_ok=True)

    # Create a fake bot script
    bot_script = os.path.join(tmp_dir, "fake_bot.py")
    with open(bot_script, "w") as f:
        f.write("import time, signal, sys\n")
        f.write("signal.signal(signal.SIGTERM, lambda s,f: sys.exit(0))\n")
        f.write("while True: time.sleep(0.1)\n")

    with open(log_path, "w") as f:
        f.write("")

    daemon = WatchdogDaemon.__new__(WatchdogDaemon)
    daemon._base_dir = tmp_dir
    daemon._state_path = state_path
    daemon._bot_command = ["python", bot_script]
    daemon._log_path = log_path
    daemon._mode = "paper"
    daemon._heartbeat_interval = 1
    daemon._frozen_threshold = 5
    daemon._max_restarts = 3
    daemon._restart_window = 60
    daemon._shutting_down = Event()
    daemon._bot_process = None
    daemon._telegram = MagicMock()
    daemon._start_time = time.time()
    daemon._log_monitor = None
    daemon._network_retry_count = 0

    from watchdog_state import WatchdogState
    daemon._state = WatchdogState(state_path)

    from watchdog_event_router import EventRouter
    daemon._event_router = EventRouter(
        telegram=daemon._telegram,
        state=daemon._state,
        max_restarts=3,
        restart_window=60,
    )

    return daemon, tmp_dir


class TestProcessManagement:
    def test_start_bot_process(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        assert daemon._bot_process is not None
        assert daemon._bot_process.poll() is None  # Still running
        daemon._bot_process.terminate()
        daemon._bot_process.wait(timeout=5)

    def test_stop_bot_graceful(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        daemon.stop_bot(timeout=5)
        assert daemon._bot_process is None or daemon._bot_process.poll() is not None

    def test_detect_crashed_bot(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        daemon._bot_process.terminate()
        daemon._bot_process.wait(timeout=5)
        assert daemon.is_bot_running() is False

    def test_is_bot_running_when_no_process(self, mock_deps):
        daemon, tmp_dir = mock_deps
        assert daemon.is_bot_running() is False


class TestPreflightChecks:
    def test_preflight_missing_env(self, mock_deps):
        daemon, tmp_dir = mock_deps
        errors = daemon.run_preflight_checks(tmp_dir)
        assert any(".env" in e for e in errors)

    def test_preflight_env_present(self, mock_deps):
        daemon, tmp_dir = mock_deps
        with open(os.path.join(tmp_dir, ".env"), "w") as f:
            f.write("BINANCE_API_KEY=test\nBINANCE_API_SECRET=test\n")
            f.write("TELEGRAM_BOT_TOKEN=test\nTELEGRAM_CHAT_ID=test\n")
        os.makedirs(os.path.join(tmp_dir, ".venv"), exist_ok=True)
        errors = daemon.run_preflight_checks(tmp_dir)
        assert not any(".env" in e for e in errors)
        assert not any(".venv" in e for e in errors)


class TestCommandHandling:
    def test_stop_command(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        daemon._handle_command("STOP")
        assert daemon._shutting_down.is_set()

    def test_restart_command(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        old_pid = daemon._bot_process.pid
        daemon._handle_command("RESTART")
        # Should have restarted
        assert daemon._bot_process is not None
        daemon.stop_bot(timeout=5)

    def test_dict_command(self, mock_deps):
        daemon, tmp_dir = mock_deps
        daemon.start_bot()
        daemon._handle_command({"action": "SHUTDOWN"})
        # Bot should be stopped but watchdog still running
        assert not daemon._shutting_down.is_set()
        assert daemon._bot_process is None or daemon._bot_process.poll() is not None
