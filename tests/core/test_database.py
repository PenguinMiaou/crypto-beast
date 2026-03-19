import asyncio
from datetime import datetime

import pytest
import pytest_asyncio


@pytest.fixture
def db(tmp_path):
    from core.database import Database

    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    database.initialize()
    return database


class TestDatabase:
    def test_initialize_creates_tables(self, db):
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "trades" in table_names
        assert "equity_snapshots" in table_names
        assert "strategy_performance" in table_names
        assert "evolution_log" in table_names
        assert "klines" in table_names
        assert "whale_events" in table_names
        assert "trade_reviews" in table_names
        assert "review_reports" in table_names
        assert "system_health" in table_names

    def test_wal_mode_enabled(self, db):
        result = db.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_insert_and_query_trade(self, db):
        db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("BTCUSDT", "LONG", 65000.0, 0.001, 10, "trend_follower", datetime.utcnow().isoformat(), "OPEN"),
        )
        trades = db.execute("SELECT * FROM trades").fetchall()
        assert len(trades) == 1
        assert trades[0][1] == "BTCUSDT"

    def test_insert_equity_snapshot(self, db):
        db.execute(
            "INSERT INTO equity_snapshots (timestamp, equity, unrealized_pnl) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), 100.0, 0.0),
        )
        snaps = db.execute("SELECT * FROM equity_snapshots").fetchall()
        assert len(snaps) == 1

    def test_backup(self, db, tmp_path):
        db.execute(
            "INSERT INTO equity_snapshots (timestamp, equity, unrealized_pnl) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), 100.0, 0.0),
        )
        backup_path = str(tmp_path / "backup.db")
        db.backup(backup_path)
        from core.database import Database

        backup_db = Database(backup_path)
        snaps = backup_db.execute("SELECT * FROM equity_snapshots").fetchall()
        assert len(snaps) == 1
