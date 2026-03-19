# tests/data/test_data_feed.py
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch


class TestDataFeed:
    def test_init(self):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m", "15m"])
        assert "BTCUSDT" in feed.symbols
        assert "5m" in feed.intervals

    def test_store_and_retrieve_klines(self, sample_klines):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        feed._cache["BTCUSDT"]["5m"] = sample_klines
        result = feed.get_klines("BTCUSDT", "5m", limit=100)
        assert len(result) == 100
        assert isinstance(result, pd.DataFrame)

    def test_get_klines_returns_latest(self, sample_klines):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        feed._cache["BTCUSDT"]["5m"] = sample_klines
        result = feed.get_klines("BTCUSDT", "5m", limit=10)
        # Should return the last 10 rows
        assert result.iloc[-1]["close"] == sample_klines.iloc[-1]["close"]

    def test_get_klines_unknown_symbol_returns_empty(self):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        result = feed.get_klines("XYZUSDT", "5m", limit=10)
        assert len(result) == 0
