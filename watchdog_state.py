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
