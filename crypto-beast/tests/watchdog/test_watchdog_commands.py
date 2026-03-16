"""Tests for watchdog Telegram commands."""
import json
import os
import sqlite3
from unittest.mock import MagicMock, patch
import pytest
from watchdog_commands import WatchdogCommands
from watchdog_state import WatchdogState


@pytest.fixture
def setup_commands(tmp_path):
    """Create WatchdogCommands with mocked Telegram and temp DB."""
    db_path = str(tmp_path / "test.db")
    state_path = str(tmp_path / "watchdog.state")

    # Create test DB with trades table
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE trades (
        id INTEGER PRIMARY KEY, symbol TEXT, side TEXT,
        entry_price REAL, exit_price REAL, quantity REAL,
        leverage INTEGER, strategy TEXT, entry_time TEXT,
        exit_time TEXT, pnl REAL, fees REAL, status TEXT,
        stop_loss REAL, take_profit REAL
    )""")
    conn.execute(
        "INSERT INTO trades VALUES (1,'BTCUSDT','LONG',70000,71000,0.001,10,'trend','2026-03-16','2026-03-16',1.0,0.01,'CLOSED',69000,72000)"
    )
    conn.execute(
        "INSERT INTO trades VALUES (2,'ETHUSDT','LONG',2100,NULL,0.05,5,'momentum','2026-03-16',NULL,NULL,0.01,'OPEN',2050,2200)"
    )
    conn.commit()
    conn.close()

    telegram = MagicMock()
    state = WatchdogState(state_path)
    env = {"BINANCE_API_KEY": "test", "BINANCE_API_SECRET": "test"}

    cmds = WatchdogCommands(
        telegram=telegram, state=state, db_path=db_path, env=env
    )
    return cmds, telegram, state


class TestBasicCommands:
    def test_help(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/help", [])
        tg.send.assert_called_once()
        text = tg.send.call_args[0][0]
        assert "/status" in text
        assert "/positions" in text

    def test_status(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/status", [])
        tg.send.assert_called_once()
        text = tg.send.call_args[0][0]
        assert "系统状态" in text

    def test_positions(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/positions", [])
        tg.send.assert_called_once()
        text = tg.send.call_args[0][0]
        assert "ETHUSDT" in text
        assert "LONG" in text

    def test_pnl(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/pnl", [])
        tg.send.assert_called_once()

    def test_trades(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/trades", [])
        tg.send.assert_called_once()
        text = tg.send.call_args[0][0]
        assert "BTCUSDT" in text

    def test_unknown_command(self, setup_commands):
        cmds, tg, _ = setup_commands
        cmds.handle("/foo", [])
        tg.send.assert_called_once()
        text = tg.send.call_args[0][0]
        assert "Unknown" in text


class TestControlCommands:
    def test_pause(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/pause", [])
        assert state.read()["paused"] is True

    def test_resume(self, setup_commands):
        cmds, tg, state = setup_commands
        state.update(paused=True)
        cmds.handle("/resume", [])
        assert state.read()["paused"] is False

    def test_close_writes_command(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/close", ["BTCUSDT"])
        cmd = state.read()["command"]
        assert cmd["action"] == "CLOSE"
        assert cmd["args"] == "BTCUSDT"

    def test_closeall_writes_command(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/closeall", [])
        cmd = state.read()["command"]
        assert cmd["action"] == "CLOSEALL"

    def test_restart_writes_command(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/restart", [])
        cmd = state.read()["command"]
        assert cmd["action"] == "RESTART"

    def test_stopall_requires_confirm(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/stopall", [])
        # Should NOT write STOP yet
        assert state.read()["command"] is None
        text = tg.send.call_args[0][0]
        assert "confirm" in text.lower() or "确认" in text


class TestDirectives:
    def test_add_directive(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/directive", ["保守一点"])
        directives = state.read()["directives"]
        assert len(directives) == 1
        assert directives[0]["text"] == "保守一点"
        assert directives[0]["id"] == 1

    def test_list_directives(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/directive", ["保守一点"])
        tg.reset_mock()
        cmds.handle("/directives", [])
        text = tg.send.call_args[0][0]
        assert "保守一点" in text

    def test_delete_directive(self, setup_commands):
        cmds, tg, state = setup_commands
        cmds.handle("/directive", ["保守一点"])
        cmds.handle("/deldirective", ["1"])
        assert len(state.read()["directives"]) == 0


class TestWatchdogStatus:
    def test_watchdog_command(self, setup_commands):
        cmds, tg, state = setup_commands
        state.update(watchdog_pid=12345, bot_pid=12346, status="running")
        cmds.handle("/watchdog", [])
        text = tg.send.call_args[0][0]
        assert "12345" in text
        assert "12346" in text
