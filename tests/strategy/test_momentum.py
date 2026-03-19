# tests/strategy/test_momentum.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime


@pytest.fixture
def uptrend_data():
    """Steady uptrend to create positive increasing MACD histogram."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.cumsum(np.linspace(10, 100, n))  # Accelerating uptrend
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def downtrend_data():
    """Steady downtrend to create negative decreasing MACD histogram."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 - np.cumsum(np.linspace(10, 100, n))  # Accelerating downtrend
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestMomentum:
    def test_long_signal_uptrend(self, uptrend_data):
        from strategy.momentum import Momentum

        m = Momentum()
        signals = m.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        long_signals = [s for s in signals if s.direction == Direction.LONG]
        assert len(long_signals) > 0

    def test_short_signal_downtrend(self, downtrend_data):
        from strategy.momentum import Momentum

        m = Momentum()
        signals = m.generate(downtrend_data, "BTCUSDT", MarketRegime.TRENDING_DOWN)
        short_signals = [s for s in signals if s.direction == Direction.SHORT]
        assert len(short_signals) > 0

    def test_strategy_name(self, uptrend_data):
        from strategy.momentum import Momentum

        m = Momentum()
        signals = m.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        if signals:
            assert signals[0].strategy == "momentum"
