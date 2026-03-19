"""Tests for PatternScanner."""

from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd
import pytest

from analysis.pattern_scanner import PatternScanner
from core.models import Direction


@pytest.fixture
def scanner():
    return PatternScanner(lookback=50)


@pytest.fixture
def double_bottom_data():
    n = 60
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    # W shape: drop, rise, drop, rise
    close[:15] = 65000 - np.arange(15) * 100  # Drop to 63500
    close[15:30] = 63500 + np.arange(15) * 100  # Rise to 65000
    close[30:45] = 65000 - np.arange(15) * 100  # Drop to 63500 again
    close[45:] = 63500 + np.arange(15) * 120  # Rise above neckline
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def double_top_data():
    n = 60
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    # M shape: rise, drop, rise, drop
    close[:15] = 65000 + np.arange(15) * 100  # Rise to 66400
    close[15:30] = 66400 - np.arange(15) * 100  # Drop to 65000
    close[30:45] = 65000 + np.arange(15) * 100  # Rise to 66400 again
    close[45:] = 66400 - np.arange(15) * 120  # Drop below neckline
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def flat_data():
    n = 60
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    high = close + 5
    low = close - 5
    open_ = close
    volume = np.full(n, 1000.0)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


class TestPatternScanner:
    def test_double_bottom_detected(self, scanner, double_bottom_data):
        patterns = scanner.scan(double_bottom_data, "BTCUSDT", "5m")
        names = [p.name for p in patterns]
        assert "double_bottom" in names
        db = [p for p in patterns if p.name == "double_bottom"][0]
        assert db.direction == Direction.LONG
        assert db.confidence == 0.65

    def test_double_top_detected(self, scanner, double_top_data):
        patterns = scanner.scan(double_top_data, "BTCUSDT", "5m")
        names = [p.name for p in patterns]
        assert "double_top" in names
        dt = [p for p in patterns if p.name == "double_top"][0]
        assert dt.direction == Direction.SHORT
        assert dt.confidence == 0.65

    def test_flat_data_no_patterns(self, scanner, flat_data):
        patterns = scanner.scan(flat_data, "BTCUSDT", "5m")
        assert len(patterns) == 0

    def test_short_data_returns_empty(self, scanner):
        short_df = pd.DataFrame({
            "open_time": [datetime(2026, 1, 1)],
            "open": [65000], "high": [65100], "low": [64900],
            "close": [65050], "volume": [1000],
        })
        patterns = scanner.scan(short_df, "BTCUSDT", "5m")
        assert patterns == []
