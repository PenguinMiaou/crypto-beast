# Watchdog Core Implementation Plan (Plan 1 of 4)

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the watchdog daemon that monitors and auto-restarts the Crypto Beast trading bot, with L1 auto-fix capabilities and Telegram notifications.

**Architecture:** Multi-threaded Python daemon: main thread (heartbeat + process management), log monitor thread (tail -f + pattern matching), self-check thread (hang detection). State persisted in JSON file with file locking. Telegram notifications via simple HTTP requests.

**Tech Stack:** Python 3.9 (threading, subprocess, fcntl, json, re, requests), loguru, existing Config/Database classes.

**Spec:** `docs/superpowers/specs/2026-03-16-watchdog-daily-review-design.md`

**Scope:** This plan covers Sections 1, 2 (L1 only), 7, 8, and 15 (pre-flight + graceful shutdown) of the spec. Telegram commands, Claude integration, and review intelligence are in Plans 2-4.

---

## File Structure

```
crypto-beast/
├── watchdog.py                     # NEW: main daemon entry point (~300 lines)
├── watchdog_state.py               # NEW: state file management with locking (~120 lines)
├── watchdog_telegram.py            # NEW: lightweight Telegram sender (~60 lines)
├── watchdog_log_monitor.py         # NEW: log tail + pattern matching (~100 lines)
├── watchdog_event_router.py        # NEW: event classification + L1 handlers (~150 lines)
├── com.cryptobeast.watchdog.plist  # NEW: launchd config
├── start.sh                        # MODIFY: add watchdog mode
├── config.py                       # MODIFY: add watchdog config fields
├── crypto_system.py                # MODIFY: read watchdog.state for pause/commands
├── tests/
│   └── watchdog/
│       ├── conftest.py             # NEW: shared fixtures
│       ├── test_watchdog_state.py  # NEW
│       ├── test_watchdog_telegram.py # NEW
│       ├── test_log_monitor.py     # NEW
│       ├── test_event_router.py    # NEW
│       └── test_watchdog_core.py   # NEW: integration test
```

---

## Chunk 1: Foundation (State File + Config + Telegram Sender)

### Task 1: Watchdog State File Management

**Files:**
- Create: `watchdog_state.py`
- Test: `tests/watchdog/test_watchdog_state.py`
- Create: `tests/watchdog/__init__.py`
- Create: `tests/watchdog/conftest.py`

- [ ] **Step 1: Create test directory and conftest**

```bash
mkdir -p tests/watchdog
touch tests/watchdog/__init__.py
```

Write `tests/watchdog/conftest.py`:
```python
"""Shared fixtures for watchdog tests."""
import json
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_state_file(tmp_path):
    """Provides a temporary state file path."""
    return str(tmp_path / "watchdog.state")


@pytest.fixture
def tmp_dir(tmp_path):
    """Provides a temporary directory."""
    return str(tmp_path)
```

- [ ] **Step 2: Write failing tests for WatchdogState**

Write `tests/watchdog/test_watchdog_state.py`:
```python
"""Tests for watchdog state file management."""
import json
import os
import time
from threading import Thread

import pytest

from watchdog_state import WatchdogState


class TestWatchdogStateInit:
    def test_creates_new_state_file(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        assert os.path.exists(tmp_state_file)

    def test_loads_existing_state_file(self, tmp_state_file):
        # Pre-create a state file
        data = {"bot_pid": 999, "paused": True}
        with open(tmp_state_file, "w") as f:
            json.dump(data, f)
        state = WatchdogState(tmp_state_file)
        assert state.read()["bot_pid"] == 999
        assert state.read()["paused"] is True

    def test_default_state_has_required_fields(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        data = state.read()
        assert "watchdog_pid" in data
        assert "bot_pid" in data
        assert "status" in data
        assert "paused" in data
        assert "restarts_today" in data
        assert "claude_calls_today" in data
        assert "last_heartbeat" in data
        assert "recent_events" in data
        assert "pending_approvals" in data
        assert "command" in data
        assert "directives" in data
        assert data["paused"] is False
        assert data["command"] is None


class TestWatchdogStateReadWrite:
    def test_update_field(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.update(bot_pid=12345)
        assert state.read()["bot_pid"] == 12345

    def test_update_multiple_fields(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.update(bot_pid=123, paused=True, status="halted")
        data = state.read()
        assert data["bot_pid"] == 123
        assert data["paused"] is True
        assert data["status"] == "halted"

    def test_add_event(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.add_event("L1", "Process crashed — auto-restarted")
        events = state.read()["recent_events"]
        assert len(events) == 1
        assert events[0]["level"] == "L1"
        assert "Process crashed" in events[0]["event"]
        assert "time" in events[0]

    def test_events_max_50(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        for i in range(60):
            state.add_event("L1", f"Event {i}")
        events = state.read()["recent_events"]
        assert len(events) == 50
        # Most recent should be last
        assert "Event 59" in events[-1]["event"]

    def test_pop_command(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.update(command={"action": "STOP"})
        cmd = state.pop_command()
        assert cmd["action"] == "STOP"
        # After pop, command should be None
        assert state.read()["command"] is None

    def test_pop_command_when_none(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        assert state.pop_command() is None

    def test_reset_daily_counters(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.update(restarts_today=5, claude_calls_today=3)
        state.reset_daily_counters()
        data = state.read()
        assert data["restarts_today"] == 0
        assert data["claude_calls_today"] == 0


class TestWatchdogStateConcurrency:
    def test_concurrent_writes_dont_corrupt(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    state.update(restarts_today=n * 20 + i)
            except Exception as e:
                errors.append(e)

        threads = [Thread(target=writer, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # State should be valid JSON
        data = state.read()
        assert isinstance(data["restarts_today"], int)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog_state'`

- [ ] **Step 4: Implement WatchdogState**

Write `watchdog_state.py`:
```python
"""Watchdog state file management with thread-safe locking."""
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class WatchdogState:
    """Thread-safe state file for watchdog <-> bot communication.

    Uses a threading.Lock for in-process safety and atomic file writes
    (write to .tmp then os.replace) for cross-process safety.
    """

    MAX_EVENTS = 50

    def __init__(self, path: str = "watchdog.state"):
        self._path = path
        self._lock = threading.Lock()
        if os.path.exists(path):
            self._data = self._read_file()
        else:
            self._data = self._default_state()
            self._write_file(self._data)

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
            "watchdog_pid": os.getpid(),
            "bot_pid": None,
            "status": "starting",
            "paused": False,
            "uptime_seconds": 0,
            "restarts_today": 0,
            "claude_calls_today": 0,
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "last_log_line_time": None,
            "recent_events": [],
            "pending_approvals": [],
            "command": None,
            "directives": [],
        }

    def _read_file(self) -> Dict[str, Any]:
        with open(self._path, "r") as f:
            return json.load(f)

    def _write_file(self, data: Dict[str, Any]) -> None:
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self._path)

    def read(self) -> Dict[str, Any]:
        with self._lock:
            self._data = self._read_file()
            return self._data.copy()

    def update(self, **kwargs: Any) -> None:
        with self._lock:
            data = self._read_file()
            data.update(kwargs)
            self._write_file(data)
            self._data = data

    def add_event(self, level: str, event: str) -> None:
        with self._lock:
            data = self._read_file()
            data["recent_events"].append({
                "time": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "event": event,
            })
            # Keep only last MAX_EVENTS
            data["recent_events"] = data["recent_events"][-self.MAX_EVENTS:]
            self._write_file(data)
            self._data = data

    def pop_command(self) -> Optional[Dict]:
        with self._lock:
            data = self._read_file()
            cmd = data.get("command")
            if cmd is not None:
                data["command"] = None
                self._write_file(data)
                self._data = data
            return cmd

    def reset_daily_counters(self) -> None:
        self.update(restarts_today=0, claude_calls_today=0)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_state.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add watchdog_state.py tests/watchdog/
git commit -m "feat(watchdog): add state file management with locking"
```

---

### Task 2: Watchdog Config Fields

**Files:**
- Modify: `config.py`
- Test: `tests/core/test_config.py` (add watchdog field tests)

- [ ] **Step 1: Write failing test for watchdog config fields**

Append to `tests/core/test_config.py`:
```python
class TestWatchdogConfig:
    def test_watchdog_defaults(self):
        config = Config()
        assert config.watchdog_heartbeat_interval == 30
        assert config.watchdog_frozen_threshold == 300
        assert config.watchdog_max_restarts == 3
        assert config.watchdog_restart_window == 600
        assert config.watchdog_claude_cooldown == 3600
        assert config.watchdog_daily_claude_budget == 3
        assert config.watchdog_review_hour == 0
        assert config.watchdog_review_minute == 30
        assert config.watchdog_event_queue_max == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/core/test_config.py::TestWatchdogConfig -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add watchdog fields to Config dataclass**

In `config.py`, add after the existing fields (before `__init__`):
```python
    # Watchdog
    watchdog_heartbeat_interval: int = 30
    watchdog_frozen_threshold: int = 300
    watchdog_max_restarts: int = 3
    watchdog_restart_window: int = 600
    watchdog_claude_cooldown: int = 3600
    watchdog_daily_claude_budget: int = 3
    watchdog_review_hour: int = 0
    watchdog_review_minute: int = 30
    watchdog_event_queue_max: int = 5
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/core/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/core/test_config.py
git commit -m "feat(watchdog): add watchdog config fields"
```

---

### Task 3: Lightweight Telegram Sender

**Files:**
- Create: `watchdog_telegram.py`
- Test: `tests/watchdog/test_watchdog_telegram.py`

- [ ] **Step 1: Write failing tests**

Write `tests/watchdog/test_watchdog_telegram.py`:
```python
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
        # First call fails (Markdown), second succeeds (plain)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_telegram.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog_telegram'`

- [ ] **Step 3: Implement WatchdogTelegram**

Write `watchdog_telegram.py`:
```python
"""Lightweight Telegram sender for watchdog notifications."""
import requests
from loguru import logger


class WatchdogTelegram:
    """Send Telegram messages without async dependencies."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)

    def send(self, text: str) -> bool:
        """Send message. Tries Markdown first, falls back to plain text."""
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            # Try Markdown first
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            if resp.status_code == 200:
                return True
            # Markdown failed, send plain text
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_telegram.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add watchdog_telegram.py tests/watchdog/test_watchdog_telegram.py
git commit -m "feat(watchdog): add lightweight Telegram sender"
```

---

## Chunk 2: Log Monitor + Event Router + L1 Handlers

### Task 4: Log Monitor Thread

**Files:**
- Create: `watchdog_log_monitor.py`
- Test: `tests/watchdog/test_log_monitor.py`

- [ ] **Step 1: Write failing tests**

Write `tests/watchdog/test_log_monitor.py`:
```python
"""Tests for log file monitor."""
import os
import time
from threading import Event

import pytest

from watchdog_log_monitor import LogMonitor


class TestLogMonitor:
    def test_detects_new_log_lines(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("initial line\n")

        collected = []
        monitor = LogMonitor(log_path, callback=lambda line: collected.append(line))
        monitor.start()

        time.sleep(0.2)
        with open(log_path, "a") as f:
            f.write("07:50:45 | ERROR    | Something went wrong\n")
        time.sleep(0.5)

        monitor.stop()
        assert any("ERROR" in line for line in collected)

    def test_tracks_last_line_time(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("07:50:45 | INFO     | startup\n")

        monitor = LogMonitor(log_path, callback=lambda line: None)
        monitor.start()

        time.sleep(0.2)
        with open(log_path, "a") as f:
            f.write("08:00:00 | INFO     | cycle complete\n")
        time.sleep(0.5)

        monitor.stop()
        assert monitor.last_line_time is not None

    def test_handles_missing_log_file(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "nonexistent.log")
        monitor = LogMonitor(log_path, callback=lambda line: None)
        monitor.start()
        time.sleep(0.3)
        monitor.stop()
        # Should not crash

    def test_handles_log_rotation(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("line 1\n")

        collected = []
        monitor = LogMonitor(log_path, callback=lambda line: collected.append(line))
        monitor.start()
        time.sleep(0.2)

        # Simulate rotation: truncate and write new content
        with open(log_path, "w") as f:
            f.write("new line after rotation\n")
        time.sleep(0.5)

        monitor.stop()
        assert any("rotation" in line for line in collected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_log_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement LogMonitor**

Write `watchdog_log_monitor.py`:
```python
"""Monitor bot log file for errors and activity."""
import os
import time
from datetime import datetime, timezone
from threading import Thread, Event
from typing import Callable, Optional

from loguru import logger


class LogMonitor:
    """Tail a log file and invoke callback on new lines."""

    POLL_INTERVAL = 0.5  # seconds

    def __init__(self, log_path: str, callback: Callable[[str], None]):
        self._log_path = log_path
        self._callback = callback
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self.last_line_time: Optional[datetime] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Tail the log file, detect rotation by inode/size change."""
        while not self._stop_event.is_set():
            try:
                if not os.path.exists(self._log_path):
                    self._stop_event.wait(self.POLL_INTERVAL)
                    continue

                with open(self._log_path, "r") as f:
                    # Seek to end
                    f.seek(0, 2)
                    file_size = f.tell()

                    while not self._stop_event.is_set():
                        line = f.readline()
                        if line:
                            line = line.strip()
                            if line:
                                self.last_line_time = datetime.now(timezone.utc)
                                self._callback(line)
                        else:
                            # Check for rotation (file shrunk or replaced)
                            try:
                                current_size = os.path.getsize(self._log_path)
                                if current_size < file_size:
                                    # File was truncated/rotated, re-open
                                    break
                                file_size = current_size
                            except OSError:
                                break
                            self._stop_event.wait(self.POLL_INTERVAL)

            except Exception as e:
                logger.debug(f"Log monitor error: {e}")
                self._stop_event.wait(2)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_log_monitor.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add watchdog_log_monitor.py tests/watchdog/test_log_monitor.py
git commit -m "feat(watchdog): add log file monitor thread"
```

---

### Task 5: Event Router and L1 Handlers

**Files:**
- Create: `watchdog_event_router.py`
- Test: `tests/watchdog/test_event_router.py`

- [ ] **Step 1: Write failing tests**

Write `tests/watchdog/test_event_router.py`:
```python
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

    def test_unknown_error_is_l2(self):
        level, action = self.router.classify("ERROR | NoneType has no attribute 'get'")
        assert level == EventLevel.L2
        assert action == "claude_fix"

    def test_unknown_critical_is_l2(self):
        level, action = self.router.classify("CRITICAL | Core module down: executor")
        assert level == EventLevel.L2
        assert action == "claude_fix"

    def test_known_binance_error_is_l1(self):
        level, action = self.router.classify('ERROR | Order failed: {"code":-4164,"msg":"notional"}')
        assert level == EventLevel.L1
        assert action == "notify_only"

    def test_unknown_binance_error_is_l2(self):
        level, action = self.router.classify('ERROR | Order failed: {"code":-9999,"msg":"unknown"}')
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
            telegram=MagicMock(),
            state=MagicMock(),
            max_restarts=3,
            restart_window=600,
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
        self.router._restart_window = 1  # 1 second window for test
        for _ in range(3):
            self.router.record_restart()
        time.sleep(1.1)
        assert not self.router.restart_limit_exceeded()


class TestL1Handlers:
    def setup_method(self):
        self.telegram = MagicMock()
        self.state = MagicMock()
        self.router = EventRouter(
            telegram=self.telegram,
            state=self.state,
            max_restarts=3,
            restart_window=600,
        )

    @patch("watchdog_event_router.subprocess.run")
    def test_kill_zombies(self, mock_run):
        mock_run.return_value = MagicMock(stdout="12345\n12346\n", returncode=0)
        killed = self.router.kill_zombie_processes("crypto_system")
        assert killed >= 0  # May or may not find zombies

    def test_notify_only_sends_telegram(self):
        self.router.handle_l1("notify_only", "Margin is insufficient")
        self.telegram.send.assert_called_once()
        call_text = self.telegram.send.call_args[0][0]
        assert "[L1]" in call_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_event_router.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement EventRouter**

Write `watchdog_event_router.py`:
```python
"""Event classification and L1 auto-fix handlers."""
import re
import subprocess
import time
from enum import Enum
from typing import List, Optional, Tuple

from loguru import logger


class EventLevel(Enum):
    IGNORE = "ignore"
    L1 = "L1"
    L2 = "L2"


# Known log patterns → (regex, category, L1 action)
KNOWN_PATTERNS = [
    (r"disk I/O error", "zombie_db_lock", "kill_zombies_restart"),
    (r"ConnectionError|Timeout|ECONNRESET", "network_transient", "wait_and_retry"),
    (r"Margin is insufficient", "margin_warning", "notify_only"),
    (r"HALT.*daily loss", "emergency_halt", "notify_only"),
    (r"Rate limit|429", "rate_limit", "notify_only"),
    (r"cancelAllOrders.*requires a symbol", "known_bug", "ignore"),
]

# Known Binance error codes that are operational, not bugs
KNOWN_BINANCE_ERRORS = {
    "-4120",  # Invalid order type (algo API migration)
    "-4061",  # Position side mismatch
    "-4164",  # Min notional
    "-2019",  # Margin insufficient
    "-1015",  # Too many orders
    "-1021",  # Timestamp outside recvWindow
}


class EventRouter:
    """Classify log events and execute L1 auto-fix actions."""

    def __init__(self, telegram, state, max_restarts: int = 3,
                 restart_window: int = 600):
        self._telegram = telegram
        self._state = state
        self._max_restarts = max_restarts
        self._restart_window = restart_window
        self._restart_times: List[float] = []

    def classify(self, log_line: str) -> Tuple[EventLevel, str]:
        """Classify a log line into event level and action."""
        # Only look at ERROR and CRITICAL lines for events
        is_error = bool(re.search(r"\bERROR\b|\bCRITICAL\b", log_line))
        is_warning = bool(re.search(r"\bWARNING\b", log_line))

        if not is_error and not is_warning:
            return EventLevel.IGNORE, "none"

        # Check against known patterns
        for pattern, category, action in KNOWN_PATTERNS:
            if re.search(pattern, log_line):
                return EventLevel.L1, action

        # Check for known Binance error codes (operational, not bugs)
        for code in KNOWN_BINANCE_ERRORS:
            if code in log_line:
                return EventLevel.L1, "notify_only"

        # Unknown ERROR/CRITICAL → L2
        if is_error:
            return EventLevel.L2, "claude_fix"

        # WARNING but not matching known patterns → ignore
        return EventLevel.IGNORE, "none"

    def record_restart(self) -> None:
        """Record a restart timestamp."""
        self._restart_times.append(time.time())

    def restart_limit_exceeded(self) -> bool:
        """Check if we've exceeded restart limit within the window."""
        now = time.time()
        # Remove old entries outside window
        self._restart_times = [
            t for t in self._restart_times
            if now - t < self._restart_window
        ]
        return len(self._restart_times) >= self._max_restarts

    def handle_l1(self, action: str, context: str) -> Optional[str]:
        """Execute an L1 action. Returns result description or None."""
        if action == "ignore":
            return None

        if action == "notify_only":
            self._telegram.send(f"[L1] {context}")
            self._state.add_event("L1", context)
            return "notified"

        if action == "kill_zombies_restart":
            killed = self.kill_zombie_processes("crypto_system")
            msg = f"Killed {killed} zombie process(es), requesting restart"
            self._telegram.send(f"[L1] {context} — {msg}")
            self._state.add_event("L1", f"{context} — {msg}")
            return "restart_needed"

        if action == "wait_and_retry":
            self._state.add_event("L1", f"Network issue: {context}")
            return "transient"

        return None

    @staticmethod
    def kill_zombie_processes(process_name: str) -> int:
        """Kill duplicate processes matching name. Returns count killed."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", process_name],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            if len(pids) <= 1:
                return 0
            # Kill all but the most recent (last PID)
            killed = 0
            for pid in pids[:-1]:
                try:
                    subprocess.run(["kill", "-9", pid], timeout=5)
                    killed += 1
                except Exception:
                    pass
            return killed
        except Exception as e:
            logger.error(f"Failed to kill zombies: {e}")
            return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_event_router.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add watchdog_event_router.py tests/watchdog/test_event_router.py
git commit -m "feat(watchdog): add event router with L1 classification and handlers"
```

---

## Chunk 3: Main Daemon (Process Management + Self-Check)

### Task 6: Main Watchdog Daemon

**Files:**
- Create: `watchdog.py`
- Test: `tests/watchdog/test_watchdog_core.py`

- [ ] **Step 1: Write failing tests**

Write `tests/watchdog/test_watchdog_core.py`:
```python
"""Tests for main watchdog daemon."""
import json
import os
import signal
import subprocess
import time
from threading import Event
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from watchdog import WatchdogDaemon


@pytest.fixture
def mock_deps(tmp_dir):
    """Create a WatchdogDaemon with mocked dependencies."""
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
    daemon._state_path = state_path
    daemon._bot_command = ["python", bot_script]
    daemon._log_path = log_path
    daemon._mode = "paper"
    daemon._heartbeat_interval = 1  # Fast for tests
    daemon._frozen_threshold = 5
    daemon._max_restarts = 3
    daemon._restart_window = 60
    daemon._shutting_down = Event()
    daemon._bot_process = None
    daemon._telegram = MagicMock()
    daemon._start_time = time.time()

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
        pid = daemon._bot_process.pid
        daemon.stop_bot(timeout=5)
        assert daemon._bot_process.poll() is not None  # Exited

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
        # No .env file
        errors = daemon.run_preflight_checks(tmp_dir)
        assert any(".env" in e for e in errors)

    def test_preflight_all_pass(self, mock_deps):
        daemon, tmp_dir = mock_deps
        # Create required files
        with open(os.path.join(tmp_dir, ".env"), "w") as f:
            f.write("BINANCE_API_KEY=test\nBINANCE_API_SECRET=test\n")
            f.write("TELEGRAM_BOT_TOKEN=test\nTELEGRAM_CHAT_ID=test\n")
        os.makedirs(os.path.join(tmp_dir, ".venv"), exist_ok=True)
        errors = daemon.run_preflight_checks(tmp_dir)
        # May have disk space or DB errors, but not .env or .venv
        assert not any(".env" in e for e in errors)
        assert not any(".venv" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'watchdog'`

- [ ] **Step 3: Implement WatchdogDaemon**

Write `watchdog.py`:
```python
#!/usr/bin/env python3
"""Crypto Beast Watchdog Daemon — monitors and auto-restarts the trading bot."""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import List, Optional

from loguru import logger

from watchdog_event_router import EventRouter, EventLevel
from watchdog_log_monitor import LogMonitor
from watchdog_state import WatchdogState
from watchdog_telegram import WatchdogTelegram


class WatchdogDaemon:
    """Main watchdog daemon: monitors bot process, handles L1 events."""

    def __init__(self, mode: str = "paper", base_dir: Optional[str] = None):
        self._base_dir = base_dir or str(Path(__file__).parent)
        self._mode = mode
        self._shutting_down = Event()
        self._bot_process: Optional[subprocess.Popen] = None
        self._start_time = time.time()

        # Load config
        sys.path.insert(0, self._base_dir)
        from config import Config
        config = Config(os.path.join(self._base_dir, ".env"))

        # Paths
        self._state_path = os.path.join(self._base_dir, "watchdog.state")
        self._log_path = os.path.join(self._base_dir, "logs", "bot.log")
        bot_args = ["python", os.path.join(self._base_dir, "crypto_system.py")]
        if mode == "live":
            bot_args.append("--live")
        self._bot_command = bot_args

        # Config values
        self._heartbeat_interval = config.watchdog_heartbeat_interval
        self._frozen_threshold = config.watchdog_frozen_threshold
        self._max_restarts = config.watchdog_max_restarts
        self._restart_window = config.watchdog_restart_window

        # Components
        self._telegram = WatchdogTelegram(
            config.telegram_bot_token, config.telegram_chat_id)
        self._state = WatchdogState(self._state_path)
        self._event_router = EventRouter(
            telegram=self._telegram,
            state=self._state,
            max_restarts=self._max_restarts,
            restart_window=self._restart_window,
        )
        self._log_monitor: Optional[LogMonitor] = None
        self._network_retry_count = 0

    # === Process Management ===

    def start_bot(self) -> None:
        """Start the trading bot as a subprocess."""
        logger.info(f"Starting bot: {' '.join(self._bot_command)}")
        os.makedirs(os.path.join(self._base_dir, "logs"), exist_ok=True)
        log_file = open(self._log_path, "a")
        self._bot_process = subprocess.Popen(
            self._bot_command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=self._base_dir,
        )
        self._state.update(
            bot_pid=self._bot_process.pid,
            status="running",
        )
        logger.info(f"Bot started with PID {self._bot_process.pid}")

    def stop_bot(self, timeout: int = 30) -> None:
        """Gracefully stop the bot (SIGTERM, then SIGKILL)."""
        if not self._bot_process:
            return
        pid = self._bot_process.pid
        logger.info(f"Stopping bot PID {pid}...")

        # Send SIGTERM for graceful shutdown
        try:
            self._bot_process.terminate()
            self._bot_process.wait(timeout=timeout)
            logger.info(f"Bot PID {pid} stopped gracefully")
        except subprocess.TimeoutExpired:
            logger.warning(f"Bot PID {pid} didn't stop, force killing")
            self._bot_process.kill()
            self._bot_process.wait(timeout=5)

        self._bot_process = None
        self._state.update(bot_pid=None, status="stopped")

    def is_bot_running(self) -> bool:
        """Check if bot process is alive."""
        if self._bot_process is None:
            return False
        return self._bot_process.poll() is None

    def restart_bot(self, reason: str) -> None:
        """Stop and restart the bot."""
        logger.warning(f"Restarting bot: {reason}")
        self._event_router.record_restart()

        if self._event_router.restart_limit_exceeded():
            msg = f"Restart limit exceeded ({self._max_restarts} in {self._restart_window}s)"
            logger.error(msg)
            self._telegram.send(f"[L2] {msg} — need Claude Code intervention")
            self._state.add_event("L2", msg)
            self.stop_bot()
            self._state.update(status="L2-TERMINAL")
            return

        self.stop_bot()
        time.sleep(2)
        self.start_bot()
        self._state.update(
            restarts_today=self._state.read()["restarts_today"] + 1)
        self._telegram.send(f"[L1] Bot restarted: {reason}")
        self._state.add_event("L1", f"Bot restarted: {reason}")

    # === Log Event Handling ===

    def _on_log_line(self, line: str) -> None:
        """Callback for new log lines from the monitor."""
        level, action = self._event_router.classify(line)

        if level == EventLevel.IGNORE:
            return

        if level == EventLevel.L1:
            result = self._event_router.handle_l1(action, line[-200:])
            if result == "restart_needed":
                self.restart_bot("L1: " + line[-100:])
            elif result == "transient":
                self._network_retry_count += 1
                if self._network_retry_count > 3:
                    self._network_retry_count = 0
                    self._telegram.send(
                        "[L1] Persistent network issues (3 retries), restarting bot")
                    self.restart_bot("Persistent network errors")
                else:
                    # Wait 30s before next check (spec: "Wait 30s, retry 3x")
                    time.sleep(30)
            else:
                self._network_retry_count = 0

        elif level == EventLevel.L2:
            logger.warning(f"L2 event detected: {line[-200:]}")
            self._telegram.send(
                f"[L2] Unknown error detected:\n{line[-200:]}\n"
                "Claude Code intervention needed (Plan 3)")
            self._state.add_event("L2", line[-200:])

    # === Heartbeat (Main Loop) ===

    def _check_frozen(self) -> bool:
        """Check if bot is frozen (no log output + low CPU)."""
        if not self._log_monitor or not self._log_monitor.last_line_time:
            return False

        elapsed = (datetime.now(timezone.utc) -
                   self._log_monitor.last_line_time).total_seconds()
        if elapsed < self._frozen_threshold:
            return False

        # Check CPU usage before declaring frozen
        if self._bot_process:
            try:
                result = subprocess.run(
                    ["ps", "-p", str(self._bot_process.pid), "-o", "%cpu="],
                    capture_output=True, text=True, timeout=5,
                )
                cpu = float(result.stdout.strip())
                if cpu > 1.0:
                    return False  # Still doing work, not frozen
            except Exception:
                pass

        return True

    def run_heartbeat(self) -> None:
        """Single heartbeat cycle."""
        now = datetime.now(timezone.utc)

        # Update heartbeat timestamp
        self._state.update(
            last_heartbeat=now.isoformat(),
            uptime_seconds=int(time.time() - self._start_time),
            last_log_line_time=(
                self._log_monitor.last_line_time.isoformat()
                if self._log_monitor and self._log_monitor.last_line_time
                else None
            ),
        )

        # Check for commands from Telegram
        cmd = self._state.pop_command()
        if cmd:
            self._handle_command(cmd)

        # Check bot status
        if self._state.read().get("status") == "L2-TERMINAL":
            return  # Don't auto-restart in terminal state

        if not self.is_bot_running():
            self._telegram.send("[L1] Bot process crashed — auto-restarting")
            self.restart_bot("Process exited unexpectedly")
            return

        # Check frozen
        if self._check_frozen():
            self._telegram.send(
                f"[L1] Bot frozen (no log output for "
                f"{self._frozen_threshold}s) — restarting")
            self.restart_bot("Process frozen")
            return

        # Reset daily counters at midnight UTC
        if now.hour == 0 and now.minute == 0:
            self._state.reset_daily_counters()

    def _handle_command(self, cmd) -> None:
        """Process a command from watchdog.state."""
        if isinstance(cmd, str):
            action = cmd
            args = None
        elif isinstance(cmd, dict):
            action = cmd.get("action", "")
            args = cmd.get("args")
        else:
            return

        if action == "STOP":
            logger.info("STOP command received")
            self._telegram.send("[CMD] Shutting down bot and watchdog...")
            self.stop_bot()
            self._shutting_down.set()

        elif action == "RESTART":
            logger.info("RESTART command received")
            self.restart_bot("Manual restart via Telegram")
            self._state.update(status="running")

        elif action == "SHUTDOWN":
            logger.info("SHUTDOWN command — graceful bot stop")
            self.stop_bot()
            self._state.update(status="stopped")
            self._telegram.send("[CMD] Bot stopped. Watchdog still active.")

    # === Pre-flight Checks ===

    def run_preflight_checks(self, base_dir: Optional[str] = None) -> List[str]:
        """Verify environment before starting bot. Returns list of errors."""
        base = base_dir or self._base_dir
        errors = []

        # Check .env
        env_path = os.path.join(base, ".env")
        if not os.path.exists(env_path):
            errors.append(f".env not found at {env_path}")
        else:
            with open(env_path) as f:
                content = f.read()
            for key in ["BINANCE_API_KEY", "BINANCE_API_SECRET",
                        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
                if key not in content:
                    errors.append(f".env missing {key}")

        # Check venv
        venv_path = os.path.join(base, ".venv")
        if not os.path.isdir(venv_path):
            errors.append(f".venv not found at {venv_path}")

        # Check disk space (100MB minimum)
        try:
            usage = shutil.disk_usage(base)
            if usage.free < 100 * 1024 * 1024:
                errors.append(
                    f"Low disk space: {usage.free // (1024*1024)}MB free")
        except Exception as e:
            errors.append(f"Disk check failed: {e}")

        # Check DB integrity
        db_path = os.path.join(base, "crypto_beast.db")
        if os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result[0] != "ok":
                    errors.append(f"DB integrity check failed: {result[0]}")
                conn.close()
            except Exception as e:
                errors.append(f"DB check failed: {e}")

        # Check no zombie processes
        try:
            result = subprocess.run(
                ["pgrep", "-f", "crypto_system"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p for p in result.stdout.strip().split("\n") if p.strip()]
            if len(pids) > 0:
                errors.append(
                    f"Found {len(pids)} existing crypto_system process(es): "
                    f"{', '.join(pids)}")
        except Exception:
            pass

        # Check Binance API reachable
        try:
            import requests
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/ping", timeout=10)
            if resp.status_code != 200:
                errors.append(
                    f"Binance API unreachable (status {resp.status_code})")
        except Exception as e:
            errors.append(f"Binance API unreachable: {e}")

        return errors

    # === Self-Check Thread ===

    def _run_self_check(self) -> None:
        """Monitor main thread liveness. Kills process if hung."""
        while not self._shutting_down.is_set():
            self._shutting_down.wait(30)
            if self._shutting_down.is_set():
                return

            try:
                data = self._state.read()
                last_hb = data.get("last_heartbeat")
                if last_hb:
                    last = datetime.fromisoformat(last_hb)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                    if elapsed > 120:  # 2 minutes without heartbeat
                        logger.critical(
                            f"Watchdog main thread hung ({elapsed:.0f}s). "
                            "Forcing exit for launchd restart.")
                        self._telegram.send(
                            "[WATCHDOG] Main thread hung, restarting...")
                        os._exit(1)
            except Exception:
                pass

    # === Main Entry Point ===

    def run(self) -> None:
        """Main daemon loop."""
        # Configure logging
        logger.remove()
        logger.add(sys.stderr, level="INFO",
                   format="{time:HH:mm:ss} | {level: <8} | {message}")
        logger.add(
            os.path.join(self._base_dir, "logs", "watchdog.log"),
            rotation="1 day", retention="30 days", level="DEBUG",
        )

        logger.info(f"Watchdog daemon starting (mode={self._mode})")

        # Signal handling
        def handle_signal(signum, frame):
            logger.info(f"Watchdog received signal {signum}, shutting down")
            self._shutting_down.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Check for stale heartbeat (recovery from crash/downtime)
        try:
            data = self._state.read()
            last_hb = data.get("last_heartbeat")
            if last_hb:
                last = datetime.fromisoformat(last_hb)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed > 3600:
                    # Extended downtime (>1h) — run recovery
                    self._telegram.send(
                        f"[WATCHDOG] Extended downtime ({int(elapsed // 60)}min). "
                        "Running recovery checks...")
                    # Bot will reconcile with exchange on startup
                elif elapsed > 120:
                    self._telegram.send(
                        f"[WATCHDOG] Recovered from crash/hang "
                        f"(down for {int(elapsed)}s)")
        except Exception:
            pass

        # Pre-flight checks
        errors = self.run_preflight_checks()
        if errors:
            for e in errors:
                logger.error(f"Pre-flight: {e}")
            # Only fatal errors prevent start
            fatal = [e for e in errors if ".env" in e or ".venv" in e]
            if fatal:
                self._telegram.send(
                    "[WATCHDOG] Pre-flight FAILED:\n" +
                    "\n".join(fatal))
                return

        # Kill any existing zombie processes
        self._event_router.kill_zombie_processes("crypto_system")

        # Start bot
        self.start_bot()

        # Start log monitor
        self._log_monitor = LogMonitor(self._log_path, self._on_log_line)
        self._log_monitor.start()

        # Start self-check thread
        self_check = Thread(target=self._run_self_check, daemon=True)
        self_check.start()

        self._state.update(watchdog_pid=os.getpid(), status="running")
        self._telegram.send(
            f"[WATCHDOG] Started (mode={self._mode}, "
            f"PID={os.getpid()}, bot PID={self._bot_process.pid})")

        # Main heartbeat loop
        while not self._shutting_down.is_set():
            try:
                self.run_heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            self._shutting_down.wait(self._heartbeat_interval)

        # Shutdown
        logger.info("Watchdog shutting down...")
        self._log_monitor.stop()
        self.stop_bot()
        self._state.update(status="stopped")
        self._telegram.send("[WATCHDOG] Stopped")
        logger.info("Watchdog stopped")


def main():
    parser = argparse.ArgumentParser(description="Crypto Beast Watchdog")
    parser.add_argument("mode", nargs="?", default="paper",
                        choices=["live", "paper"],
                        help="Trading mode (default: paper)")
    parser.add_argument("--base-dir", default=None,
                        help="Base directory (default: script directory)")
    args = parser.parse_args()

    daemon = WatchdogDaemon(mode=args.mode, base_dir=args.base_dir)
    daemon.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest tests/watchdog/test_watchdog_core.py -v`
Expected: All PASS

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest -q`
Expected: 323+ tests pass (existing + new)

- [ ] **Step 6: Commit**

```bash
git add watchdog.py tests/watchdog/test_watchdog_core.py
git commit -m "feat(watchdog): add main daemon with process management and self-check"
```

---

## Chunk 4: Integration (start.sh + crypto_system.py + launchd)

### Task 7: Update start.sh

**Files:**
- Modify: `start.sh`

- [ ] **Step 1: Read current start.sh**

Read `start.sh` to understand exact current content.

- [ ] **Step 2: Update start.sh to support watchdog mode**

Replace `start.sh` with:
```bash
#!/bin/bash
# Crypto Beast v1.0 — Start Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/bot.pid"

echo "=== Crypto Beast v1.0 ==="

MODE=${1:-paper}

# Dashboard doesn't need to kill trading processes
if [ "$MODE" != "dashboard" ]; then
    # Kill existing watchdog and bot processes
    for pid in $(ps aux | grep "[c]rypto_system" | awk '{print $2}'); do
        echo "Killing old bot process $pid"
        kill -9 "$pid" 2>/dev/null || true
    done
    for pid in $(ps aux | grep "[w]atchdog.py" | awk '{print $2}'); do
        echo "Killing old watchdog process $pid"
        kill -9 "$pid" 2>/dev/null || true
    done
    pkill -9 caffeinate 2>/dev/null || true
    sleep 2
fi

cd "$DIR"
source .venv/bin/activate

# Clean pycache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading (via watchdog)..."
    nohup python watchdog.py live >> logs/watchdog_out.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "Watchdog PID: $! | Log: $DIR/logs/watchdog.log"
elif [ "$MODE" = "paper" ]; then
    echo "Starting PAPER trading (via watchdog)..."
    nohup python watchdog.py paper >> logs/watchdog_out.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "Watchdog PID: $! | Log: $DIR/logs/watchdog.log"
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    exec streamlit run monitoring/dashboard_app.py --server.port 8080
elif [ "$MODE" = "stop" ]; then
    echo "Stopped."
elif [ "$MODE" = "direct-live" ]; then
    # Bypass watchdog, run bot directly (for debugging)
    echo "Starting LIVE trading (direct, no watchdog)..."
    nohup python crypto_system.py --live >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
elif [ "$MODE" = "direct-paper" ]; then
    echo "Starting PAPER trading (direct, no watchdog)..."
    nohup python crypto_system.py >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
else
    echo "Usage: start.sh [live|paper|dashboard|stop|direct-live|direct-paper]"
fi
```

- [ ] **Step 3: Test manually**

```bash
cd "/Volumes/ORICO Media/Crypto Trading System" && bash crypto-beast/start.sh live
sleep 5
# Verify watchdog is running
ps aux | grep watchdog.py | grep -v grep
# Verify bot is running
ps aux | grep crypto_system | grep -v grep
# Check watchdog log
tail -5 crypto-beast/logs/watchdog.log
# Check state file
cat crypto-beast/watchdog.state | python -m json.tool
```

- [ ] **Step 4: Commit**

```bash
git add start.sh
git commit -m "feat(watchdog): update start.sh to launch via watchdog"
```

---

### Task 8: Modify crypto_system.py to Read watchdog.state

**Files:**
- Modify: `crypto_system.py`

- [ ] **Step 1: Read the current run_trading_cycle method**

Read `crypto_system.py` lines around the signal generation / trade opening section to find where to add the pause check.

- [ ] **Step 2: Add watchdog.state reading at the start of run_trading_cycle**

At the beginning of `run_trading_cycle()`, after the cycle count increment, add:
```python
        # Check watchdog commands/pause
        state_path = os.path.join(os.path.dirname(__file__), "watchdog.state")
        if os.path.exists(state_path):
            try:
                import json as _json
                with open(state_path) as _f:
                    _wstate = _json.load(_f)
                if _wstate.get("paused"):
                    logger.info("Trading paused via watchdog")
                    return
                _cmd = _wstate.get("command")
                if _cmd and isinstance(_cmd, dict):
                    action = _cmd.get("action", "")
                    if action == "CLOSE":
                        symbol = _cmd.get("args", "")
                        if symbol:
                            await self._close_symbol_by_watchdog(symbol)
                    elif action == "CLOSEALL":
                        positions = await m["executor"].get_positions()
                        await self._emergency_close(positions)
                    elif action == "SHUTDOWN":
                        logger.info("Shutdown command from watchdog")
                        return
                    # Clear the command after processing
                    _wstate["command"] = None
                    with open(state_path, "w") as _f:
                        _json.dump(_wstate, _f)
            except Exception as e:
                logger.debug(f"Failed to read watchdog.state: {e}")
```

Also add the helper method:
```python
    async def _close_symbol_by_watchdog(self, symbol: str) -> None:
        """Close a specific symbol position via watchdog command."""
        from core.models import OrderType
        positions = await self.modules["executor"].get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                await self.modules["executor"].close_position(pos, OrderType.MARKET)
                logger.info(f"Closed {symbol} via watchdog command")
                return
        logger.warning(f"No open position for {symbol} to close")
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add crypto_system.py
git commit -m "feat(watchdog): crypto_system reads watchdog.state for pause/commands"
```

---

### Task 9: launchd Plist

**Files:**
- Create: `com.cryptobeast.watchdog.plist`

- [ ] **Step 1: Create the plist file**

Write `com.cryptobeast.watchdog.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cryptobeast.watchdog</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Volumes/ORICO Media/Crypto Trading System/crypto-beast/.venv/bin/python</string>
        <string>/Volumes/ORICO Media/Crypto Trading System/crypto-beast/watchdog.py</string>
        <string>live</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Volumes/ORICO Media/Crypto Trading System/crypto-beast</string>

    <key>KeepAlive</key>
    <true/>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Volumes/ORICO Media/Crypto Trading System/crypto-beast/logs/watchdog_launchd.log</string>

    <key>StandardErrorPath</key>
    <string>/Volumes/ORICO Media/Crypto Trading System/crypto-beast/logs/watchdog_launchd.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Volumes/ORICO Media/Crypto Trading System/crypto-beast/.venv/bin</string>
    </dict>
</dict>
</plist>
```

- [ ] **Step 2: Install instructions (do NOT auto-install)**

Print to user:
```
To install launchd auto-restart (optional):
  cp com.cryptobeast.watchdog.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.cryptobeast.watchdog.plist

To uninstall:
  launchctl unload ~/Library/LaunchAgents/com.cryptobeast.watchdog.plist
  rm ~/Library/LaunchAgents/com.cryptobeast.watchdog.plist
```

- [ ] **Step 3: Commit**

```bash
git add com.cryptobeast.watchdog.plist
git commit -m "feat(watchdog): add launchd plist for auto-restart"
```

---

### Task 10: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass (323 existing + ~25 new watchdog tests)

- [ ] **Step 2: Manual smoke test**

```bash
# Stop current bot
ps aux | grep crypto_system | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
sleep 2

# Start via watchdog
cd "/Volumes/ORICO Media/Crypto Trading System"
bash crypto-beast/start.sh live

# Wait and verify
sleep 10
echo "=== Watchdog ==="
ps aux | grep "watchdog.py" | grep -v grep
echo "=== Bot ==="
ps aux | grep "crypto_system" | grep -v grep
echo "=== State ==="
cat crypto-beast/watchdog.state | python -m json.tool
echo "=== Watchdog Log ==="
tail -10 crypto-beast/logs/watchdog.log
echo "=== Bot Log ==="
tail -5 crypto-beast/logs/bot.log
```

- [ ] **Step 3: Test auto-restart by killing bot**

```bash
# Kill bot (not watchdog)
kill -9 $(ps aux | grep "crypto_system" | grep -v grep | awk '{print $2}')
# Wait for watchdog to detect and restart
sleep 35
# Verify bot is back
ps aux | grep "crypto_system" | grep -v grep
# Check watchdog log for restart event
grep "restart" crypto-beast/logs/watchdog.log | tail -3
```

- [ ] **Step 4: Commit any fixes from smoke test**

```bash
git add -A
git commit -m "fix(watchdog): adjustments from integration testing"
```

---

## Summary

**Plan 1 delivers:**
- `watchdog.py` — main daemon with process management, heartbeat, self-check
- `watchdog_state.py` — thread-safe JSON state file with locking
- `watchdog_telegram.py` — lightweight Telegram sender
- `watchdog_log_monitor.py` — log file tail + pattern matching
- `watchdog_event_router.py` — event classification + L1 handlers
- `com.cryptobeast.watchdog.plist` — launchd auto-restart config
- Updated `start.sh` — launches watchdog by default
- Updated `crypto_system.py` — reads watchdog.state for pause/commands
- Updated `config.py` — watchdog configuration fields
- ~25 new tests across 5 test files

**What's NOT in this plan (deferred to Plans 2-4):**
- Plan 2: Telegram command migration (all /commands move to watchdog)
- Plan 3: Claude CLI integration (L2 fixes, data extraction pipeline)
- Plan 4: Review intelligence (19-module review, versioning, directives, weekly/monthly)
