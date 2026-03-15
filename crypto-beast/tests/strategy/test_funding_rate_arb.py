"""Tests for FundingRateArb strategy."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from core.models import Direction, MarketRegime
from strategy.funding_rate_arb import FundingRateArb


@pytest.fixture
def strategy():
    return FundingRateArb(extreme_threshold=0.001)


@pytest.fixture
def sample_klines():
    n = 30
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = np.linspace(65000, 65500, n)
    high = close + 50
    low = close - 50
    open_ = close - 10
    volume = np.full(n, 1000.0)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


class TestFundingRateArb:
    def test_strategy_name(self, strategy):
        assert strategy.name == "funding_rate_arb"

    def test_high_positive_funding_short(self, strategy, sample_klines):
        """High positive funding -> SHORT signal."""
        strategy.update_funding_rate("BTCUSDT", 0.003)
        signals = strategy.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 1
        assert signals[0].direction == Direction.SHORT
        assert signals[0].strategy == "funding_rate_arb"

    def test_high_negative_funding_long(self, strategy, sample_klines):
        """High negative funding -> LONG signal."""
        strategy.update_funding_rate("BTCUSDT", -0.003)
        signals = strategy.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 1
        assert signals[0].direction == Direction.LONG

    def test_normal_funding_no_signal(self, strategy, sample_klines):
        """Normal funding rate -> no signal."""
        strategy.update_funding_rate("BTCUSDT", 0.0005)
        signals = strategy.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 0

    def test_no_funding_data_no_signal(self, strategy, sample_klines):
        """No funding data -> no signal."""
        signals = strategy.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 0

    def test_short_klines_no_signal(self, strategy):
        """Not enough klines -> no signal."""
        strategy.update_funding_rate("BTCUSDT", 0.003)
        short_df = pd.DataFrame({
            "open_time": [datetime(2026, 1, 1)],
            "open": [65000], "high": [65100], "low": [64900],
            "close": [65050], "volume": [1000],
        })
        signals = strategy.generate(short_df, "BTCUSDT", MarketRegime.RANGING)
        assert len(signals) == 0

    def test_confidence_capped_at_07(self, strategy, sample_klines):
        """Confidence should not exceed 0.7."""
        strategy.update_funding_rate("BTCUSDT", 0.05)  # Very extreme
        signals = strategy.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
        assert signals[0].confidence <= 0.7
