"""Tests for new DB tables created by watchdog system."""
import sqlite3
import os
import pytest
import sys

# Ensure crypto-beast is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture
def test_db(tmp_path):
    """Create a DB with all tables including new ones."""
    db_path = str(tmp_path / "test.db")
    from core.database import Database
    db = Database(db_path)
    db.initialize()
    return db_path


class TestNewTables:
    def test_rejected_signals_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) "
            "VALUES ('BTCUSDT','LONG','trend','risk_limit','70000','2026-03-16')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM rejected_signals").fetchone()
        assert row is not None
        conn.close()

    def test_recommendation_history_table(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO recommendation_history (date, module, description) "
            "VALUES ('2026-03-16','SL/TP','Increase BTC SL to 3.5%')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM recommendation_history").fetchone()
        assert row is not None
        conn.close()

    def test_strategy_versions_table(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO strategy_versions (version, date, description, source) "
            "VALUES ('v1.0','2026-03-16','Initial','manual')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM strategy_versions WHERE version='v1.0'").fetchone()
        assert row is not None
        conn.close()

    def test_change_registry_table(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO change_registry (timestamp, source, file_changed, description) "
            "VALUES ('2026-03-16','daily_review','config.py','Adjusted SL')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM change_registry").fetchone()
        assert row is not None
        conn.close()

    def test_watchdog_interventions_table(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO watchdog_interventions (timestamp, level, event, action, outcome) "
            "VALUES ('2026-03-16','L1','crash','restart','resolved')"
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watchdog_interventions").fetchone()
        assert row is not None
        conn.close()
