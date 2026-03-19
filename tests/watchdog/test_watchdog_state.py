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
        assert "Event 59" in events[-1]["event"]

    def test_pop_command(self, tmp_state_file):
        state = WatchdogState(tmp_state_file)
        state.update(command={"action": "STOP"})
        cmd = state.pop_command()
        assert cmd["action"] == "STOP"
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
        data = state.read()
        assert isinstance(data["restarts_today"], int)
