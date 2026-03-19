"""Tests for SmartOrder execution planning."""
import pytest
from datetime import datetime

from core.models import (
    Direction,
    ExecutionPlan,
    MarketRegime,
    OrderType,
    TradeSignal,
    ValidatedOrder,
)
from execution.smart_order import SmartOrder


@pytest.fixture
def long_signal() -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        confidence=0.85,
        entry_price=65000.0,
        stop_loss=63700.0,
        take_profit=68000.0,
        strategy="trend_follow",
        regime=MarketRegime.TRENDING_UP,
        timeframe_score=7,
        timestamp=datetime.utcnow(),
    )


@pytest.fixture
def short_signal() -> TradeSignal:
    return TradeSignal(
        symbol="ETHUSDT",
        direction=Direction.SHORT,
        confidence=0.80,
        entry_price=3500.0,
        stop_loss=3600.0,
        take_profit=3200.0,
        strategy="mean_revert",
        regime=MarketRegime.RANGING,
        timeframe_score=5,
        timestamp=datetime.utcnow(),
    )


@pytest.fixture
def long_order(long_signal: TradeSignal) -> ValidatedOrder:
    return ValidatedOrder(
        signal=long_signal,
        quantity=0.1,
        leverage=5,
        order_type=OrderType.MARKET,
        risk_amount=130.0,
        max_slippage=0.001,
    )


@pytest.fixture
def short_order(short_signal: TradeSignal) -> ValidatedOrder:
    return ValidatedOrder(
        signal=short_signal,
        quantity=1.0,
        leverage=3,
        order_type=OrderType.LIMIT,
        risk_amount=100.0,
        max_slippage=0.001,
    )


@pytest.fixture
def smart_order() -> SmartOrder:
    return SmartOrder(num_entry_tranches=3, time_limit_hours=4.0)


class TestHighUrgency:
    """High urgency should produce a single MARKET entry tranche."""

    def test_single_market_tranche(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.9)
        assert len(plan.entry_tranches) == 1
        assert plan.entry_tranches[0]["type"] == "MARKET"
        assert plan.entry_tranches[0]["quantity"] == long_order.quantity

    def test_no_trailing_stop_high_urgency(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.8)
        assert plan.trailing_stop is None

    def test_urgency_exactly_08(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.8)
        assert len(plan.entry_tranches) == 1
        assert plan.entry_tranches[0]["type"] == "MARKET"


class TestLowUrgency:
    """Low urgency should produce multiple LIMIT tranches (DCA)."""

    def test_multiple_tranches(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.2)
        assert len(plan.entry_tranches) > 1

    def test_first_tranche_market_rest_limit(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.2)
        assert plan.entry_tranches[0]["type"] == "MARKET"
        for t in plan.entry_tranches[1:]:
            assert t["type"] == "LIMIT"

    def test_tranche_quantities_sum_to_total(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.2)
        total_qty = sum(t["quantity"] for t in plan.entry_tranches)
        assert abs(total_qty - long_order.quantity) < 1e-6

    def test_long_tranches_decreasing_price(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.2)
        prices = [t["price"] for t in plan.entry_tranches]
        for i in range(1, len(prices)):
            assert prices[i] <= prices[i - 1]

    def test_short_tranches_increasing_price(
        self, smart_order: SmartOrder, short_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(short_order, urgency=0.2)
        prices = [t["price"] for t in plan.entry_tranches]
        for i in range(1, len(prices)):
            assert prices[i] >= prices[i - 1]

    def test_trailing_stop_present(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        assert plan.trailing_stop is not None
        assert plan.trailing_stop["activation_pct"] == 0.01
        assert plan.trailing_stop["trail_pct"] == 0.005
        assert plan.trailing_stop["quantity_pct"] == 0.3


class TestExitPlan:
    """Exit plan should have 3 TP levels with correct quantities."""

    def test_three_exit_levels(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        assert len(plan.exit_tranches) == 3

    def test_exit_quantities_sum_to_total(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        total_exit_qty = sum(e["quantity"] for e in plan.exit_tranches)
        assert abs(total_exit_qty - long_order.quantity) < 1e-6

    def test_exit_trigger_names(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        triggers = [e["trigger"] for e in plan.exit_tranches]
        assert triggers == ["TP_50", "TP_75", "TP_100"]

    def test_long_exit_prices_ascending(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        prices = [e["price"] for e in plan.exit_tranches]
        for i in range(1, len(prices)):
            assert prices[i] >= prices[i - 1]

    def test_short_exit_prices_descending(
        self, smart_order: SmartOrder, short_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(short_order, urgency=0.5)
        prices = [e["price"] for e in plan.exit_tranches]
        for i in range(1, len(prices)):
            assert prices[i] <= prices[i - 1]


class TestTrailingStop:
    """Trailing stop presence depends on urgency."""

    def test_present_below_07(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        assert plan.trailing_stop is not None

    def test_absent_at_07(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.7)
        assert plan.trailing_stop is None

    def test_absent_above_08(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.9)
        assert plan.trailing_stop is None


class TestExecutionPlanFields:
    """Verify ExecutionPlan fields are set correctly."""

    def test_time_limit(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        assert plan.time_limit_hours == 4.0

    def test_order_reference(
        self, smart_order: SmartOrder, long_order: ValidatedOrder
    ):
        plan = smart_order.plan_execution(long_order, urgency=0.5)
        assert plan.order is long_order
