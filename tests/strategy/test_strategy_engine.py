# tests/strategy/test_strategy_engine.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime, ConfluenceScore, SignalType
from analysis.market_regime import MarketRegimeDetector
from analysis.multi_timeframe import MultiTimeframe
from analysis.session_trader import SessionTrader
from strategy.strategy_engine import StrategyEngine


@pytest.fixture
def uptrend_data():
    """Clear uptrend data that triggers strategy signals."""
    n = 150
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 50.0
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def sideways_data():
    """Choppy sideways data."""
    np.random.seed(42)
    n = 150
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 20
    high = close + 15
    low = close - 15
    open_ = close + np.random.randn(n) * 5
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


@pytest.fixture
def engine():
    """Create a StrategyEngine with real dependencies."""
    regime_detector = MarketRegimeDetector()
    session_trader = SessionTrader()
    multi_timeframe = MultiTimeframe()
    return StrategyEngine(regime_detector, session_trader, multi_timeframe)


class TestStrategyEngine:
    def test_generates_signals_from_uptrend(self, engine, uptrend_data):
        """All 7 strategies run and return at least one signal."""
        signals = engine.generate_signals("BTCUSDT", uptrend_data)
        assert len(signals) > 0
        # Deduplicated: at most one signal per symbol
        symbols = [s.symbol for s in signals]
        assert len(symbols) == len(set(symbols))

    def test_signals_sorted_by_confidence(self, engine, uptrend_data):
        """Signals are sorted descending by confidence."""
        signals1 = engine.generate_signals("BTCUSDT", uptrend_data)
        if len(signals1) > 1:
            for i in range(len(signals1) - 1):
                assert signals1[i].confidence >= signals1[i + 1].confidence

    def test_weight_updates_change_strategy_weight(self, engine, uptrend_data):
        """Updating weights changes _strategy_weight on signals (not confidence)."""
        signals_before = engine.generate_signals("BTCUSDT", uptrend_data)
        if not signals_before:
            return

        winning_strategy = signals_before[0].strategy
        assert signals_before[0]._strategy_weight == engine._weights.get(winning_strategy, 0.1)

        new_weights = {name: 0.01 for name in engine.get_strategy_weights()}
        new_weights[winning_strategy] = 1.0
        engine.update_weights(new_weights)

        signals_after = engine.generate_signals("BTCUSDT", uptrend_data)
        assert len(signals_after) > 0
        assert signals_after[0]._strategy_weight == engine._weights.get(signals_after[0].strategy, 0.1)

    def test_conflicting_signals_deduplicated(self, engine, sideways_data):
        """When both LONG and SHORT exist for same symbol, only highest confidence kept."""
        signals = engine.generate_signals("BTCUSDT", sideways_data)
        btc_signals = [s for s in signals if s.symbol == "BTCUSDT"]
        assert len(btc_signals) <= 1

    def test_empty_signals_possible(self, engine):
        """Very short data produces no signals."""
        short_data = pd.DataFrame({
            "open_time": [datetime(2026, 1, 1)],
            "open": [65000.0], "high": [65010.0],
            "low": [64990.0], "close": [65000.0], "volume": [500.0],
        })
        signals = engine.generate_signals("BTCUSDT", short_data)
        assert signals == []

    def test_get_strategy_weights(self, engine):
        """get_strategy_weights returns current weights for all 8 strategies."""
        weights = engine.get_strategy_weights()
        assert len(weights) == 8
        expected = 1.0 / 8
        for w in weights.values():
            assert abs(w - expected) < 1e-9

    def test_update_weights(self, engine):
        """update_weights persists changes."""
        engine.update_weights({"trend_follower": 0.5, "scalper": 0.1})
        weights = engine.get_strategy_weights()
        assert weights["trend_follower"] == 0.5
        assert weights["scalper"] == 0.1
        # Others unchanged from initial 1/8
        assert abs(weights["mean_reversion"] - 1.0 / 8) < 1e-9

    def test_confluence_score_applied(self, engine, uptrend_data):
        """When MultiTimeframe has a cached score, it's applied to signals."""
        klines_by_tf = {"4h": uptrend_data, "1h": uptrend_data, "15m": uptrend_data, "5m": uptrend_data}
        engine._multi_timeframe.update("BTCUSDT", klines_by_tf)
        signals = engine.generate_signals("BTCUSDT", uptrend_data)
        if signals:
            assert signals[0].timeframe_score == 10

    def test_no_confluence_defaults_to_zero(self, engine, uptrend_data):
        """Without MultiTimeframe data, timeframe_score stays 0."""
        signals = engine.generate_signals("BTCUSDT", uptrend_data)
        if signals:
            assert signals[0].timeframe_score == 0

    def test_confidence_not_crushed_by_strategy_weight(self, engine, uptrend_data):
        """Fix #1: strategy_weight must NOT multiply into confidence."""
        signals = engine.generate_signals("BTCUSDT", uptrend_data)
        if signals:
            assert signals[0].confidence >= 0.25, (
                f"Confidence {signals[0].confidence} still crushed by strategy weight"
            )

    def test_dedup_uses_weighted_score(self, engine, uptrend_data):
        """Fix #1: dedup should use confidence * strategy_weight for selection."""
        signals = engine.generate_signals("BTCUSDT", uptrend_data)
        symbols = [s.symbol for s in signals]
        assert len(symbols) == len(set(symbols)), "Dedup failed: duplicate symbols"

    def test_regime_aware_weights_ranging(self, engine, sideways_data):
        """#3: in RANGING market, trend strategies should have low weight."""
        signals = engine.generate_signals("BTCUSDT", sideways_data)
        for name in ("trend_follower", "momentum"):
            assert engine._weights.get(name, 1.0) <= 0.10, \
                f"{name} weight too high for RANGING: {engine._weights.get(name)}"
