# tests/strategy/test_trend_follower.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime, TradeSignal


@pytest.fixture
def uptrend_data():
    """Create data with clear uptrend (price steadily increasing)."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 50  # Steady uptrend
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def downtrend_data():
    """Create data with clear downtrend."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 - np.arange(n) * 50
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def sideways_data():
    """Create choppy sideways data."""
    n = 100
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 20  # Small random noise
    high = close + 15
    low = close - 15
    open_ = close + np.random.randn(n) * 5
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestTrendFollower:
    def test_generates_long_signal_in_uptrend(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        # Should generate at least one LONG signal in uptrend
        long_signals = [s for s in signals if s.direction == Direction.LONG]
        assert len(long_signals) > 0

    def test_generates_short_signal_in_downtrend(self, downtrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(downtrend_data, "BTCUSDT", MarketRegime.TRENDING_DOWN)
        short_signals = [s for s in signals if s.direction == Direction.SHORT]
        assert len(short_signals) > 0

    def test_low_confidence_in_sideways(self, sideways_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(sideways_data, "BTCUSDT", MarketRegime.RANGING)
        # In sideways, signals should have low confidence or be empty
        if signals:
            avg_confidence = sum(s.confidence for s in signals) / len(signals)
            assert avg_confidence < 0.7

    def test_signal_has_stop_loss_and_take_profit(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        if signals:
            s = signals[0]
            if s.direction == Direction.LONG:
                assert s.stop_loss < s.entry_price
                assert s.take_profit > s.entry_price
            else:
                assert s.stop_loss > s.entry_price
                assert s.take_profit < s.entry_price

    def test_signal_strategy_name(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        if signals:
            assert signals[0].strategy == "trend_follower"

    def test_confidence_varies_with_strength(self, uptrend_data, downtrend_data):
        """Fix #15: confidence should vary with signal strength."""
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals_up = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        signals_down = tf.generate(downtrend_data, "BTCUSDT", MarketRegime.TRENDING_DOWN)
        signals = signals_up + signals_down
        if len(signals) >= 2:
            confs = [s.confidence for s in signals]
            assert max(confs) - min(confs) >= 0.02, f"Confidence too uniform: {confs[:5]}"
