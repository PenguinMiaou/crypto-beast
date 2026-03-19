"""Tests for MultiTimeframe confluence scoring."""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from analysis.multi_timeframe import MultiTimeframe
from core.models import ConfluenceScore, SignalType


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_klines(trend: str = "up", n: int = 100) -> pd.DataFrame:
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    if trend == "up":
        close = 65000 + np.arange(n, dtype=float) * 50
    elif trend == "down":
        close = 65000 - np.arange(n, dtype=float) * 50
    else:
        close = 65000 + np.random.default_rng(42).normal(0, 20, n)
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.default_rng(42).uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


ALL_TFS = ["4h", "1h", "15m", "5m"]


def _all_tf_klines(trend: str) -> dict:
    return {tf: make_klines(trend) for tf in ALL_TFS}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMultiTimeframe:
    def setup_method(self):
        self.mt = MultiTimeframe()

    # --- All bullish ---
    def test_all_bullish_score_plus_10(self):
        result = self.mt.update("BTCUSDT", _all_tf_klines("up"))
        assert result.score == 10
        assert result.direction == SignalType.BULLISH
        assert result.symbol == "BTCUSDT"
        for tf in ALL_TFS:
            assert result.breakdown[tf] == 1

    # --- All bearish ---
    def test_all_bearish_score_minus_10(self):
        result = self.mt.update("BTCUSDT", _all_tf_klines("down"))
        assert result.score == -10
        assert result.direction == SignalType.BEARISH
        for tf in ALL_TFS:
            assert result.breakdown[tf] == -1

    # --- Mixed signals ---
    def test_mixed_signals_intermediate_score(self):
        klines = {
            "4h": make_klines("up"),    # +4
            "1h": make_klines("up"),    # +3
            "15m": make_klines("down"), # -2
            "5m": make_klines("down"),  # -1
        }
        result = self.mt.update("ETHUSDT", klines)
        # Expected: 4 + 3 - 2 - 1 = 4
        assert result.score == 4
        assert result.direction == SignalType.BULLISH

    def test_mixed_signals_negative(self):
        klines = {
            "4h": make_klines("down"),  # -4
            "1h": make_klines("down"),  # -3
            "15m": make_klines("up"),   # +2
            "5m": make_klines("up"),    # +1
        }
        result = self.mt.update("ETHUSDT", klines)
        # Expected: -4 - 3 + 2 + 1 = -4
        assert result.score == -4
        assert result.direction == SignalType.BEARISH

    # --- filter_signal ---
    def test_filter_signal_passes_when_aligned_and_strong(self):
        self.mt.update("BTCUSDT", _all_tf_klines("up"))
        assert self.mt.filter_signal("BTCUSDT", SignalType.BULLISH) is True

    def test_filter_signal_rejects_weak_score(self):
        klines = {
            "4h": make_klines("up"),
            "1h": make_klines("up"),
            "15m": make_klines("down"),
            "5m": make_klines("down"),
        }
        self.mt.update("ETHUSDT", klines)
        # |score| = 4, below threshold of 6
        assert self.mt.filter_signal("ETHUSDT", SignalType.BULLISH) is False

    def test_filter_signal_rejects_opposite_direction(self):
        self.mt.update("BTCUSDT", _all_tf_klines("up"))
        assert self.mt.filter_signal("BTCUSDT", SignalType.BEARISH) is False

    def test_filter_signal_rejects_unknown_symbol(self):
        assert self.mt.filter_signal("UNKNOWN", SignalType.BULLISH) is False

    # --- get_confluence ---
    def test_get_confluence_returns_cached(self):
        original = self.mt.update("BTCUSDT", _all_tf_klines("up"))
        cached = self.mt.get_confluence("BTCUSDT")
        assert cached is original

    def test_get_confluence_none_for_unknown(self):
        assert self.mt.get_confluence("UNKNOWN") is None

    # --- Edge: missing timeframes ---
    def test_partial_timeframes(self):
        klines = {
            "4h": make_klines("up"),   # +4
            "1h": make_klines("up"),   # +3
        }
        result = self.mt.update("BTCUSDT", klines)
        assert result.score == 7
        assert result.direction == SignalType.BULLISH
        assert "15m" not in result.breakdown
        assert "5m" not in result.breakdown
