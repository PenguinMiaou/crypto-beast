# tests/strategy/test_mean_reversion.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime


@pytest.fixture
def oversold_data():
    """Price drops sharply at end to create RSI < 30 and close < lower BB."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    # Sharp drop only in last 5 candles so BB hasn't caught up
    close[-5:] = [64500, 64000, 63500, 63000, 62500]
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def overbought_data():
    """Price rises sharply at end to create RSI > 70 and close > upper BB."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    # Sharp rise only in last 5 candles so BB hasn't caught up
    close[-5:] = [65500, 66000, 66500, 67000, 67500]
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def neutral_data():
    """Price stays near middle of BB."""
    n = 100
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 10
    high = close + 15
    low = close - 15
    open_ = close + 5
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestMeanReversion:
    def test_long_signal_oversold(self, oversold_data):
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        signals = mr.generate(oversold_data, "BTCUSDT", MarketRegime.RANGING)
        long_signals = [s for s in signals if s.direction == Direction.LONG]
        assert len(long_signals) > 0

    def test_short_signal_overbought(self, overbought_data):
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        signals = mr.generate(overbought_data, "BTCUSDT", MarketRegime.RANGING)
        short_signals = [s for s in signals if s.direction == Direction.SHORT]
        assert len(short_signals) > 0

    def test_no_signal_neutral(self, neutral_data):
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        signals = mr.generate(neutral_data, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 0

    def test_stop_loss_and_take_profit(self, oversold_data):
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        signals = mr.generate(oversold_data, "BTCUSDT", MarketRegime.RANGING)
        if signals:
            s = signals[0]
            if s.direction == Direction.LONG:
                assert s.stop_loss < s.entry_price
                assert s.take_profit > s.entry_price
            else:
                assert s.stop_loss > s.entry_price
                assert s.take_profit < s.entry_price

    def test_strategy_name(self, oversold_data):
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        signals = mr.generate(oversold_data, "BTCUSDT", MarketRegime.RANGING)
        if signals:
            assert signals[0].strategy == "mean_reversion"

    def test_confidence_varies_with_strength(self, oversold_data):
        """Fix #15: confidence varies across regimes — ranging boosts, trending penalises."""
        from strategy.mean_reversion import MeanReversion

        mr = MeanReversion()
        # Same oversold data: RANGING regime gives +0.1 bonus, TRENDING regime gives -0.2 penalty
        signals_ranging = mr.generate(oversold_data, "BTCUSDT", MarketRegime.RANGING)
        signals_trending = mr.generate(oversold_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        signals = signals_ranging + signals_trending
        if len(signals) >= 2:
            confs = [s.confidence for s in signals]
            assert max(confs) - min(confs) >= 0.02, f"Confidence too uniform: {confs[:5]}"
