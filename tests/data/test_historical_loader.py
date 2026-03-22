import pytest
from unittest.mock import MagicMock
from data.historical_loader import HistoricalDataLoader


def test_loader_creates_cache_table(db):
    loader = HistoricalDataLoader(MagicMock(), db)
    result = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='klines_cache'").fetchone()
    assert result is not None


def test_loader_load_cached_empty(db):
    loader = HistoricalDataLoader(MagicMock(), db)
    df = loader.load_cached("BTCUSDT", "5m", "2026-01-01", "2026-03-01")
    assert len(df) == 0


def test_loader_load_cached_with_data(db):
    loader = HistoricalDataLoader(MagicMock(), db)
    # Insert test data
    import time
    ts = int(time.mktime(time.strptime("2026-02-01", "%Y-%m-%d"))) * 1000
    db.execute(
        "INSERT INTO klines_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "5m", ts, 65000, 65100, 64900, 65050, 1000)
    )
    df = loader.load_cached("BTCUSDT", "5m", "2026-01-01", "2026-03-01")
    assert len(df) == 1
    assert df.iloc[0]["close"] == 65050
