# tests/strategy/test_enhanced_bb_rsi.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from core.models import MarketRegime, Direction


@pytest.fixture
def ranging_data():
    np.random.seed(42)
    n = 150
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 200
    return pd.DataFrame({
        "open_time": dates,
        "open": close + 10,
        "high": close + 50,
        "low": close - 50,
        "close": close,
        "volume": np.random.uniform(500, 1500, n),
    })


def test_enhanced_bb_rsi_generates_in_ranging(ranging_data):
    from strategy.enhanced_bb_rsi import EnhancedBbRsi
    signals = EnhancedBbRsi().generate(ranging_data, "BTCUSDT", MarketRegime.RANGING)
    assert isinstance(signals, list)
    for sig in signals:
        assert sig.strategy == "enhanced_bb_rsi"
        assert 0.3 <= sig.confidence <= 0.95


def test_enhanced_bb_rsi_no_signal_strong_trend():
    from strategy.enhanced_bb_rsi import EnhancedBbRsi
    n = 150
    close = 65000 + np.arange(n) * 200.0
    df = pd.DataFrame({
        "open": close - 10,
        "high": close + 30,
        "low": close - 30,
        "close": close,
        "volume": np.random.uniform(500, 1500, n),
    })
    signals = EnhancedBbRsi().generate(df, "BTCUSDT", MarketRegime.TRENDING_UP)
    assert len(signals) == 0, "Should not trade in strong trend (ADX > 28)"
