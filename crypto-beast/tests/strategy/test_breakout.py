# tests/strategy/test_breakout.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime


@pytest.fixture
def squeeze_breakout_data():
    """Tight range for 120 candles then sharp breakout upward with high volume."""
    n = 150
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    # Alternating tiny moves to create minimal BB width, then strong breakout
    close[:145] = 65000 + np.where(np.arange(145) % 2 == 0, 1, -1)
    close[145:] = [65200, 65500, 65800, 66200, 66600]  # Strong breakout at end
    high = close + np.where(np.arange(n) < 145, 1, 80)
    low = close - np.where(np.arange(n) < 145, 1, 30)
    open_ = close - 5
    volume = np.where(np.arange(n) < 145, np.random.uniform(100, 300, n), np.random.uniform(800, 1500, n))
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def wide_bb_data():
    """Wide BB - no squeeze condition."""
    n = 150
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 500  # High volatility throughout
    high = close + 200
    low = close - 200
    open_ = close - 50
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestBreakout:
    def test_signal_on_squeeze_breakout(self, squeeze_breakout_data):
        from strategy.breakout import Breakout

        b = Breakout()
        signals = b.generate(squeeze_breakout_data, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) > 0
        assert signals[0].direction == Direction.LONG

    def test_no_signal_wide_bb(self, wide_bb_data):
        from strategy.breakout import Breakout

        b = Breakout()
        signals = b.generate(wide_bb_data, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 0

    def test_strategy_name(self, squeeze_breakout_data):
        from strategy.breakout import Breakout

        b = Breakout()
        signals = b.generate(squeeze_breakout_data, "BTCUSDT", MarketRegime.RANGING)
        if signals:
            assert signals[0].strategy == "breakout"
