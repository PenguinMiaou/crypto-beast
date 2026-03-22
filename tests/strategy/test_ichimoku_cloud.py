# tests/strategy/test_ichimoku_cloud.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from core.models import MarketRegime, Direction


@pytest.fixture
def uptrend_data():
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 80.0
    return pd.DataFrame({
        "open_time": dates,
        "open": close - 20,
        "high": close + 30,
        "low": close - 30,
        "close": close,
        "volume": np.random.uniform(500, 1500, n),
    })


def test_ichimoku_no_signal_short_data():
    from strategy.ichimoku_cloud import IchimokuCloud
    df = pd.DataFrame({
        "open": [1] * 10,
        "high": [2] * 10,
        "low": [0.5] * 10,
        "close": [1.5] * 10,
        "volume": [100] * 10,
    })
    signals = IchimokuCloud().generate(df, "BTCUSDT", MarketRegime.RANGING)
    assert signals == []


def test_ichimoku_signal_has_correct_fields(uptrend_data):
    from strategy.ichimoku_cloud import IchimokuCloud
    signals = IchimokuCloud().generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
    for sig in signals:
        assert sig.strategy == "ichimoku_cloud"
        assert 0.3 <= sig.confidence <= 0.95
        assert sig.stop_loss > 0
        assert sig.take_profit > 0
