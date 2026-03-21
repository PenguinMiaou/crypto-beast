# tests/strategy/test_scalper.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime


@pytest.fixture
def sharp_drop_data():
    """Last few candles drop sharply to create RSI(2) < 10."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    close[-3:] = [64500, 64000, 63500]
    high = close + 50
    low = close - 50
    open_ = close + 20
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def sharp_rise_data():
    """Last few candles rise sharply to create RSI(2) > 90."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    close[-3:] = [65500, 66000, 66500]
    high = close + 50
    low = close - 50
    open_ = close - 20
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestScalper:
    def test_long_signal_sharp_drop(self, sharp_drop_data):
        from strategy.scalper import Scalper

        s = Scalper()
        signals = s.generate(sharp_drop_data, "BTCUSDT", MarketRegime.RANGING)
        long_signals = [sig for sig in signals if sig.direction == Direction.LONG]
        assert len(long_signals) > 0

    def test_short_signal_sharp_rise(self, sharp_rise_data):
        from strategy.scalper import Scalper

        s = Scalper()
        signals = s.generate(sharp_rise_data, "BTCUSDT", MarketRegime.RANGING)
        short_signals = [sig for sig in signals if sig.direction == Direction.SHORT]
        assert len(short_signals) > 0

    def test_tight_stops(self, sharp_drop_data):
        from strategy.scalper import Scalper

        s = Scalper()
        signals = s.generate(sharp_drop_data, "BTCUSDT", MarketRegime.RANGING)
        if signals:
            sig = signals[0]
            if sig.direction == Direction.LONG:
                assert sig.stop_loss < sig.entry_price
                assert sig.take_profit > sig.entry_price
                # Stop should be within ATR range (tight)
                assert (sig.entry_price - sig.stop_loss) < (sig.take_profit - sig.entry_price)

    def test_strategy_name(self, sharp_drop_data):
        from strategy.scalper import Scalper

        s = Scalper()
        signals = s.generate(sharp_drop_data, "BTCUSDT", MarketRegime.RANGING)
        if signals:
            assert signals[0].strategy == "scalper"


@pytest.fixture
def sample_klines():
    """Klines that trigger a LONG signal (sharp drop creates RSI(2) < 10)."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.full(n, 65000.0)
    close[-3:] = [64500, 64000, 63500]
    high = close + 50
    low = close - 50
    open_ = close + 20
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


def test_scalper_rr_ratio(sample_klines):
    """Fix #6: Scalper R:R should be >= 4.0."""
    from strategy.scalper import Scalper
    scalper = Scalper()
    signals = scalper.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
    for sig in signals:
        sl_dist = abs(sig.entry_price - sig.stop_loss)
        tp_dist = abs(sig.take_profit - sig.entry_price)
        if sl_dist > 0:
            rr = tp_dist / sl_dist
            assert rr >= 4.0, f"Scalper R:R {rr:.1f} < 4.0"
