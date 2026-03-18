"""Tests for review data extraction."""
import json
import os
import sqlite3
import pytest
from watchdog_review_data import extract


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE trades (
        id INTEGER PRIMARY KEY, symbol TEXT, side TEXT,
        entry_price REAL, exit_price REAL, quantity REAL,
        leverage INTEGER, strategy TEXT, entry_time TEXT,
        exit_time TEXT, pnl REAL, fees REAL, status TEXT,
        stop_loss REAL, take_profit REAL
    )""")
    conn.execute("""CREATE TABLE equity_snapshots (
        id INTEGER PRIMARY KEY, timestamp TEXT, equity REAL
    )""")
    conn.execute("""CREATE TABLE evolution_log (
        id INTEGER PRIMARY KEY, timestamp TEXT, config_before TEXT,
        config_after TEXT, sharpe_before REAL, sharpe_after REAL
    )""")
    conn.execute("""CREATE TABLE strategy_performance (
        id INTEGER PRIMARY KEY, date TEXT, strategy TEXT,
        win_rate REAL, avg_pnl REAL, trade_count INTEGER
    )""")
    # Insert test data
    conn.execute(
        "INSERT INTO trades VALUES (1,'BTCUSDT','LONG',70000,71000,0.001,10,'trend','2026-03-16','2026-03-16',1.0,0.01,'CLOSED',69000,72000)"
    )
    conn.execute(
        "INSERT INTO equity_snapshots VALUES (1,'2026-03-16T00:00:00',100.0)"
    )
    conn.commit()
    conn.close()
    return db_path


class TestDataExtraction:
    def test_extracts_trades_today(self, test_db, tmp_path):
        output = str(tmp_path / "review_data")
        extract(test_db, "2026-03-16", output)
        with open(os.path.join(output, "trades_today.json")) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["symbol"] == "BTCUSDT"

    def test_extracts_equity_snapshots(self, test_db, tmp_path):
        output = str(tmp_path / "review_data")
        extract(test_db, "2026-03-16", output)
        with open(os.path.join(output, "equity_snapshots.json")) as f:
            data = json.load(f)
        assert len(data) == 1

    def test_handles_missing_tables(self, test_db, tmp_path):
        output = str(tmp_path / "review_data")
        extract(test_db, "2026-03-16", output)
        # These tables don't exist, should produce empty arrays
        with open(os.path.join(output, "rejected_signals.json")) as f:
            assert json.load(f) == []
        with open(os.path.join(output, "change_registry_7d.json")) as f:
            assert json.load(f) == []

    def test_all_output_files_created(self, test_db, tmp_path):
        output = str(tmp_path / "review_data")
        extract(test_db, "2026-03-16", output)
        expected_files = [
            "trades_today.json", "trades_7d.json", "equity_snapshots.json",
            "evolution_log.json", "strategy_performance.json", "system_health.json",
            "rejected_signals.json", "btc_daily.json", "directives.json",
            "watchdog_events.json", "change_registry_7d.json",
            "recommendation_history.json", "strategy_version.json",
            "watchdog_interventions.json",
        ]
        for filename in expected_files:
            assert os.path.exists(os.path.join(output, filename)), f"Missing: {filename}"
