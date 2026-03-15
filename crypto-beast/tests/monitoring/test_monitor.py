"""Tests for monitoring/monitor.py"""
import sqlite3
import pytest
from monitoring.monitor import MonitorData


@pytest.fixture
def db_with_tables():
    """Create an in-memory SQLite DB with the required tables and sample data."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE equity_snapshots (
            timestamp TEXT, equity REAL, drawdown_pct REAL
        )
    """)
    conn.execute("""
        CREATE TABLE trades (
            id INTEGER PRIMARY KEY, symbol TEXT, side TEXT,
            entry_price REAL, exit_price REAL, quantity REAL,
            leverage REAL, pnl REAL, fees REAL, strategy TEXT,
            entry_time TEXT, exit_time TEXT, status TEXT
        )
    """)
    conn.commit()
    return conn


class TestMonitorDataState:
    def test_update_stores_state(self):
        md = MonitorData()
        md.update({"equity": 10000})
        state = md.get_system_state()
        assert state is not None
        assert state["equity"] == 10000
        assert "last_update" in state

    def test_get_system_state_none_initially(self):
        md = MonitorData()
        assert md.get_system_state() is None

    def test_update_overwrites_previous(self):
        md = MonitorData()
        md.update({"a": 1})
        md.update({"b": 2})
        state = md.get_system_state()
        assert "b" in state
        # previous state replaced
        assert "a" not in state


class TestMonitorDataNoDB:
    def test_get_equity_history_no_db(self):
        md = MonitorData(db=None)
        assert md.get_equity_history() == []

    def test_get_trade_history_no_db(self):
        md = MonitorData(db=None)
        assert md.get_trade_history() == []

    def test_get_strategy_performance_no_db(self):
        md = MonitorData(db=None)
        assert md.get_strategy_performance() == {}


class TestMonitorDataWithDB:
    def test_get_equity_history_empty(self, db_with_tables):
        md = MonitorData(db=db_with_tables)
        assert md.get_equity_history() == []

    def test_get_equity_history_with_data(self, db_with_tables):
        db_with_tables.execute(
            "INSERT INTO equity_snapshots VALUES (?, ?, ?)",
            ("2025-01-01T00:00:00", 10500.0, 2.5)
        )
        db_with_tables.commit()
        md = MonitorData(db=db_with_tables)
        result = md.get_equity_history()
        assert len(result) == 1
        assert result[0]["equity"] == 10500.0
        assert result[0]["drawdown_pct"] == 2.5

    def test_get_trade_history_empty(self, db_with_tables):
        md = MonitorData(db=db_with_tables)
        assert md.get_trade_history() == []

    def test_get_trade_history_with_data(self, db_with_tables):
        db_with_tables.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "BTCUSDT", "LONG", 50000, 51000, 0.1, 5, 500, 10, "momentum",
             "2025-01-01T00:00:00", "2025-01-01T01:00:00", "CLOSED")
        )
        db_with_tables.commit()
        md = MonitorData(db=db_with_tables)
        result = md.get_trade_history()
        assert len(result) == 1
        assert result[0]["symbol"] == "BTCUSDT"
        assert result[0]["pnl"] == 500
        assert result[0]["strategy"] == "momentum"

    def test_get_trade_history_respects_limit(self, db_with_tables):
        for i in range(5):
            db_with_tables.execute(
                "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (i + 1, "BTCUSDT", "LONG", 50000, 51000, 0.1, 5, 100, 5, "strat",
                 f"2025-01-0{i+1}T00:00:00", f"2025-01-0{i+1}T01:00:00", "CLOSED")
            )
        db_with_tables.commit()
        md = MonitorData(db=db_with_tables)
        result = md.get_trade_history(limit=3)
        assert len(result) == 3

    def test_get_strategy_performance_empty(self, db_with_tables):
        md = MonitorData(db=db_with_tables)
        assert md.get_strategy_performance() == {}

    def test_get_strategy_performance_with_data(self, db_with_tables):
        trades = [
            (1, "BTCUSDT", "LONG", 50000, 51000, 0.1, 5, 500, 10, "momentum",
             "2025-01-01T00:00:00", "2025-01-01T01:00:00", "CLOSED"),
            (2, "ETHUSDT", "SHORT", 3000, 2900, 1, 3, 300, 5, "momentum",
             "2025-01-02T00:00:00", "2025-01-02T01:00:00", "CLOSED"),
            (3, "BTCUSDT", "LONG", 50000, 49000, 0.1, 5, -500, 10, "momentum",
             "2025-01-03T00:00:00", "2025-01-03T01:00:00", "CLOSED"),
            (4, "ETHUSDT", "LONG", 3000, 3100, 1, 2, 100, 5, "mean_reversion",
             "2025-01-04T00:00:00", "2025-01-04T01:00:00", "CLOSED"),
        ]
        for t in trades:
            db_with_tables.execute(
                "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", t
            )
        db_with_tables.commit()
        md = MonitorData(db=db_with_tables)
        result = md.get_strategy_performance()
        assert "momentum" in result
        assert "mean_reversion" in result
        assert result["momentum"]["trades"] == 3
        assert result["momentum"]["wins"] == 2
        assert result["momentum"]["total_pnl"] == 300
        assert result["momentum"]["win_rate"] == pytest.approx(2 / 3)
        assert result["mean_reversion"]["trades"] == 1
        assert result["mean_reversion"]["wins"] == 1
        assert result["mean_reversion"]["win_rate"] == 1.0

    def test_strategy_performance_ignores_open_trades(self, db_with_tables):
        db_with_tables.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1, "BTCUSDT", "LONG", 50000, None, 0.1, 5, None, 0, "momentum",
             "2025-01-01T00:00:00", None, "OPEN")
        )
        db_with_tables.commit()
        md = MonitorData(db=db_with_tables)
        result = md.get_strategy_performance()
        assert result == {}
