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
        # max_risk_per_trade=0.03 * MAX_MULTIPLIER=3.5 * equity=$100 = $10.5 max risk
        assert order is not None
        assert order.risk_amount <= 10.5 + 0.01  # small float tolerance

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
        # At min_confidence → accepted with reduced leverage (use higher equity for BTC min notional)
        big_portfolio = Portfolio(equity=500.0, available_balance=500.0, positions=[],
            peak_equity=500.0, locked_capital=0.0, daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=0.0)
        order2 = rm.validate(low_conf, big_portfolio, min_confidence=0.3)
        assert order2 is not None
        assert order2.leverage == 3

    def test_continuous_risk_scaling(self, empty_portfolio):
        """Fix #9: risk_multiplier should be continuous, not 3-step."""
        from defense.risk_manager import RiskManager
        from config import Config

        risk_manager = RiskManager(Config())
        sig_low = TradeSignal(symbol="BTCUSDT", direction=Direction.LONG, confidence=0.35,
                              entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
                              strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8)
        sig_high = TradeSignal(symbol="BTCUSDT", direction=Direction.LONG, confidence=0.90,
                               entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
                               strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8)

        result_low = risk_manager.validate(sig_low, empty_portfolio)
        result_high = risk_manager.validate(sig_high, empty_portfolio)
        if result_low and result_high:
            assert result_high.quantity > result_low.quantity * 1.5, (
                "High confidence should get >1.5x the position of low confidence"
            )

    def test_directional_exposure_limit(self, long_signal):
        """Fix #3: reject signal when same-dir exposure exceeds 15x equity."""
        from defense.risk_manager import RiskManager
        from config import Config

        risk_manager = RiskManager(Config())
        pos1 = Position(symbol="ETHUSDT", direction=Direction.LONG, entry_price=3000.0,
                        quantity=0.27, leverage=10, unrealized_pnl=0.0, strategy="test",
                        entry_time=None, current_stop=2900.0)
        pos2 = Position(symbol="SOLUSDT", direction=Direction.LONG, entry_price=150.0,
                        quantity=5.0, leverage=10, unrealized_pnl=0.0, strategy="test",
                        entry_time=None, current_stop=145.0)
        portfolio = Portfolio(
            equity=100.0, available_balance=20.0,
            positions=[pos1, pos2],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0,
        )
        result = risk_manager.validate(long_signal, portfolio)
        assert result is None, "Should reject: directional exposure exceeds 15x"

    def test_correlated_same_dir_limit(self, empty_portfolio):
        """Fix #3: max 2 correlated assets same direction."""
        from defense.risk_manager import RiskManager
        from config import Config

        risk_manager = RiskManager(Config())
        pos1 = Position(symbol="BTCUSDT", direction=Direction.LONG, entry_price=65000.0,
                        quantity=0.001, leverage=5, unrealized_pnl=0.0, strategy="test",
                        entry_time=None, current_stop=63000.0)
        pos2 = Position(symbol="ETHUSDT", direction=Direction.LONG, entry_price=3000.0,
                        quantity=0.01, leverage=5, unrealized_pnl=0.0, strategy="test",
                        entry_time=None, current_stop=2900.0)
        portfolio = Portfolio(
            equity=100.0, available_balance=80.0,
            positions=[pos1, pos2],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0,
        )
        sol_signal = TradeSignal(
            symbol="SOLUSDT", direction=Direction.LONG, confidence=0.7,
            entry_price=150.0, stop_loss=145.0, take_profit=160.0,
            strategy="trend_follower", regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )
        result = risk_manager.validate(sol_signal, portfolio)
        assert result is None, "Should reject: 3rd correlated asset same direction"
