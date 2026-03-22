"""Tests for MarketRegimeDetector."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from analysis.market_regime import MarketRegimeDetector
from core.models import MarketRegime


@pytest.fixture
def detector():
    return MarketRegimeDetector()


@pytest.fixture
def uptrend_data():
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 50.0  # Steady uptrend
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame(
        {"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


@pytest.fixture
def downtrend_data():
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 - np.arange(n) * 50.0
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame(
        {"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


@pytest.fixture
def sideways_data():
    n = 100
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 20
    high = close + 15
    low = close - 15
    open_ = close + np.random.randn(n) * 5
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame(
        {"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )


class TestMarketRegimeDetector:
    def test_uptrend_detected(self, detector, uptrend_data):
        result = detector.detect(uptrend_data)
        assert result == MarketRegime.TRENDING_UP

    def test_downtrend_detected(self, detector, downtrend_data):
        result = detector.detect(downtrend_data)
        assert result == MarketRegime.TRENDING_DOWN

    def test_ranging_detected(self, detector, sideways_data):
        result = detector.detect(sideways_data)
        assert result == MarketRegime.RANGING


def test_transitioning_on_regime_change():
    """#6: regime change should return TRANSITIONING."""
    detector = MarketRegimeDetector()

    # First call: strong uptrend
    n = 100
    close1 = 65000 + np.arange(n) * 100.0
    df1 = pd.DataFrame({
        "open": close1 - 10,
        "high": close1 + 50,
        "low": close1 - 50,
        "close": close1,
        "volume": np.random.uniform(500, 1500, n),
    })
    r1 = detector.detect(df1, symbol="BTCUSDT")

    # Second call: sudden reversal (prices drop)
    close2 = close1[-1] - np.arange(n) * 100.0
    df2 = pd.DataFrame({
        "open": close2 + 10,
        "high": close2 + 50,
        "low": close2 - 50,
        "close": close2,
        "volume": np.random.uniform(500, 1500, n),
    })
    r2 = detector.detect(df2, symbol="BTCUSDT")

    # Should detect transition (regime changed from TRENDING_UP to TRENDING_DOWN)
    assert r2 == MarketRegime.TRANSITIONING, f"Expected TRANSITIONING, got {r2}"
