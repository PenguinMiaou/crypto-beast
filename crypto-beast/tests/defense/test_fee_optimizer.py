"""Tests for FeeOptimizer maker/taker optimization."""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import patch

from core.models import TradeSignal, Direction, MarketRegime, OrderType
from defense.fee_optimizer import FeeOptimizer


def _make_signal(confidence: float = 0.7) -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        confidence=confidence,
        entry_price=50000.0,
        stop_loss=49000.0,
        take_profit=52000.0,
        strategy="test",
        regime=MarketRegime.TRENDING_UP,
        timeframe_score=5,
    )


class TestRecommendOrderType:
    def test_high_urgency_returns_market(self):
        opt = FeeOptimizer()
        signal = _make_signal(confidence=0.5)
        assert opt.recommend_order_type(signal, urgency=0.8) == OrderType.MARKET

    def test_high_confidence_returns_market(self):
        opt = FeeOptimizer()
        signal = _make_signal(confidence=0.85)
        assert opt.recommend_order_type(signal, urgency=0.3) == OrderType.MARKET

    def test_low_urgency_low_confidence_returns_limit(self):
        opt = FeeOptimizer()
        signal = _make_signal(confidence=0.5)
        assert opt.recommend_order_type(signal, urgency=0.3) == OrderType.LIMIT

    def test_boundary_urgency_returns_limit(self):
        """Urgency exactly 0.7 should not trigger MARKET."""
        opt = FeeOptimizer()
        signal = _make_signal(confidence=0.5)
        assert opt.recommend_order_type(signal, urgency=0.7) == OrderType.LIMIT

    def test_boundary_confidence_returns_limit(self):
        """Confidence exactly 0.8 should not trigger MARKET."""
        opt = FeeOptimizer()
        signal = _make_signal(confidence=0.8)
        assert opt.recommend_order_type(signal, urgency=0.3) == OrderType.LIMIT


class TestEstimateFee:
    def test_limit_uses_maker_fee(self):
        opt = FeeOptimizer()
        notional = 10000.0
        fee = opt.estimate_fee(notional, OrderType.LIMIT)
        assert fee == pytest.approx(10000.0 * 0.0002)

    def test_market_uses_taker_fee(self):
        opt = FeeOptimizer()
        notional = 10000.0
        fee = opt.estimate_fee(notional, OrderType.MARKET)
        assert fee == pytest.approx(10000.0 * 0.0004)


class TestBudgetTracking:
    def test_record_fee_reduces_budget(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(2.0)
        assert opt.budget_remaining() == pytest.approx(3.0)

    def test_multiple_fees_accumulate(self):
        opt = FeeOptimizer(daily_fee_budget=10.0)
        opt.record_fee(3.0)
        opt.record_fee(4.0)
        assert opt.budget_remaining() == pytest.approx(3.0)

    def test_budget_remaining_never_negative(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(6.0)
        assert opt.budget_remaining() == 0.0

    def test_is_within_budget_true(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(2.0)
        assert opt.is_within_budget(2.0) is True

    def test_is_within_budget_false(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(4.0)
        assert opt.is_within_budget(2.0) is False

    def test_is_within_budget_exact_boundary(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(3.0)
        assert opt.is_within_budget(2.0) is True  # 3+2=5 == budget


class TestDailyReset:
    def test_reset_on_new_day(self):
        opt = FeeOptimizer(daily_fee_budget=5.0)
        opt.record_fee(4.0)
        assert opt.budget_remaining() == pytest.approx(1.0)

        # Simulate date change by moving _last_reset to yesterday
        opt._last_reset = (datetime.utcnow() - timedelta(days=1)).date()

        # Next call should reset
        assert opt.budget_remaining() == pytest.approx(5.0)
