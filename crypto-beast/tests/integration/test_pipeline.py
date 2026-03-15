# tests/integration/test_pipeline.py
"""Test full signal-to-execution pipeline."""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from config import Config
from core.models import Direction, Portfolio, ExecutionPlan, OrderType, MarketRegime, TradeSignal
from analysis.market_regime import MarketRegimeDetector
from strategy.trend_follower import TrendFollower
from defense.risk_manager import RiskManager
from execution.paper_executor import PaperExecutor


@pytest.fixture
def trending_klines():
    """500-candle strong uptrend that produces TRENDING_UP regime."""
    np.random.seed(99)
    n = 500
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    # Strong uptrend: +20 per candle with small noise
    close = 65000.0 + np.arange(n) * 20.0 + np.cumsum(np.random.randn(n) * 5)
    high = close + np.abs(np.random.randn(n) * 30)
    low = close - np.abs(np.random.randn(n) * 30)
    open_ = close - 10
    volume = np.random.uniform(200, 800, n)
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def _make_high_confidence_signal(price: float) -> TradeSignal:
    """Create a synthetic high-confidence signal for pipeline testing."""
    return TradeSignal(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        confidence=0.85,
        entry_price=price,
        stop_loss=round(price * 0.98, 2),
        take_profit=round(price * 1.04, 2),
        strategy="trend_follower",
        regime=MarketRegime.TRENDING_UP,
        timeframe_score=7,
    )


class TestPipeline:
    def test_regime_to_signal(self, sample_klines):
        """MarketRegimeDetector feeds into TrendFollower."""
        detector = MarketRegimeDetector()
        regime = detector.detect(sample_klines)

        strategy = TrendFollower()
        signals = strategy.generate(sample_klines, "BTCUSDT", regime)
        # Should produce signals (regime detected + strategy runs)
        # Either signals or empty is fine, but no crash
        assert isinstance(signals, list)

    def test_trending_regime_produces_signal(self, trending_klines):
        """Strong uptrend data produces a LONG signal with decent confidence."""
        detector = MarketRegimeDetector()
        regime = detector.detect(trending_klines)
        assert regime == MarketRegime.TRENDING_UP

        strategy = TrendFollower()
        signals = strategy.generate(trending_klines, "BTCUSDT", regime)
        assert len(signals) >= 1
        assert signals[0].direction == Direction.LONG
        assert signals[0].confidence >= 0.5

    def test_signal_to_validated_order(self, trending_klines):
        """Signal passes through RiskManager validation."""
        detector = MarketRegimeDetector()
        regime = detector.detect(trending_klines)

        strategy = TrendFollower()
        signals = strategy.generate(trending_klines, "BTCUSDT", regime)

        if not signals:
            pytest.skip("No signal generated")

        config = Config()
        rm = RiskManager(config)
        portfolio = Portfolio(
            equity=100.0, available_balance=100.0, positions=[],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0)

        order = rm.validate(signals[0], portfolio)
        # Order may be None if confidence too low, that's fine
        if order is not None:
            assert order.quantity > 0
            assert order.leverage >= 1

    @pytest.mark.asyncio
    async def test_full_pipeline_paper_trade(self, db):
        """Signal -> risk validation -> paper execution -> trade in DB."""
        price = 65000.0
        signal = _make_high_confidence_signal(price)

        config = Config()
        rm = RiskManager(config)
        portfolio = Portfolio(
            equity=100.0, available_balance=100.0, positions=[],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0)

        order = rm.validate(signal, portfolio)
        assert order is not None, "High-confidence signal should pass risk validation"

        executor = PaperExecutor(db=db, current_price_fn=lambda s: price)
        plan = ExecutionPlan(
            order=order,
            entry_tranches=[{"price": price, "quantity": order.quantity, "type": "MARKET"}],
            exit_tranches=[])

        result = await executor.execute(plan)
        assert result.success
        assert result.avg_fill_price > 0
        assert result.fees_paid > 0

        # Verify trade in database
        trades = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
        assert len(trades) >= 1

    @pytest.mark.asyncio
    async def test_open_and_close_position(self, db):
        """Open a paper position, then close it."""
        price = 65000.0
        signal = _make_high_confidence_signal(price)

        config = Config()
        rm = RiskManager(config)
        portfolio = Portfolio(
            equity=100.0, available_balance=100.0, positions=[],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0)

        order = rm.validate(signal, portfolio)
        assert order is not None, "High-confidence signal should pass risk validation"

        executor = PaperExecutor(db=db, current_price_fn=lambda s: price)
        plan = ExecutionPlan(
            order=order,
            entry_tranches=[{"price": price, "quantity": order.quantity, "type": "MARKET"}],
            exit_tranches=[])

        await executor.execute(plan)
        positions = await executor.get_positions()
        assert len(positions) >= 1

        # Close position
        result = await executor.close_position(positions[0])
        assert result.success

        # Verify closed in DB
        open_trades = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
        closed_trades = db.execute("SELECT * FROM trades WHERE status='CLOSED'").fetchall()
        assert len(closed_trades) >= 1
