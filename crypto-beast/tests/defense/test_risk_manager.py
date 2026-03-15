# tests/defense/test_risk_manager.py
import pytest

from core.models import (
    Direction,
    MarketRegime,
    OrderType,
    Portfolio,
    Position,
    TradeSignal,
    ValidatedOrder,
)


@pytest.fixture
def empty_portfolio():
    return Portfolio(
        equity=100.0,
        available_balance=100.0,
        positions=[],
        peak_equity=100.0,
        locked_capital=0.0,
        daily_pnl=0.0,
        total_fees_today=0.0,
        drawdown_pct=0.0,
    )


@pytest.fixture
def full_portfolio():
    """Portfolio with max positions already open."""
    positions = [
        Position(symbol=f"COIN{i}USDT", direction=Direction.LONG, entry_price=100.0,
                 quantity=0.1, leverage=5, unrealized_pnl=0.0, strategy="test",
                 entry_time=None, current_stop=95.0)
        for i in range(3)
    ]
    return Portfolio(
        equity=100.0, available_balance=50.0, positions=positions,
        peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
        total_fees_today=0.0, drawdown_pct=0.0,
    )


@pytest.fixture
def long_signal():
    return TradeSignal(
        symbol="BTCUSDT", direction=Direction.LONG, confidence=0.85,
        entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
        strategy="trend_follower", regime=MarketRegime.TRENDING_UP,
        timeframe_score=8,
    )


class TestRiskManager:
    def test_validate_returns_order_for_valid_signal(self, empty_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, empty_portfolio)
        assert order is not None
        assert isinstance(order, ValidatedOrder)

    def test_position_size_respects_max_risk(self, empty_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, empty_portfolio)
        # Max risk per trade = 2% of $100 = $2
        assert order.risk_amount <= 2.0 + 0.01  # small float tolerance

    def test_rejects_when_max_positions_reached(self, full_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, full_portfolio)
        assert order is None

    def test_leverage_based_on_confidence(self, empty_portfolio):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())

        high_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.9,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        order = rm.validate(high_conf, empty_portfolio)
        assert order.leverage == 10

        mid_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.6,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        order = rm.validate(mid_conf, empty_portfolio)
        assert order.leverage == 5

    def test_rejects_low_confidence(self, empty_portfolio):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        low_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.3,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        # Below min_confidence (default 0.3) → rejected
        order = rm.validate(low_conf, empty_portfolio, min_confidence=0.5)
        assert order is None
        # At min_confidence → accepted with reduced leverage
        order2 = rm.validate(low_conf, empty_portfolio, min_confidence=0.3)
        assert order2 is not None
        assert order2.leverage == 2
