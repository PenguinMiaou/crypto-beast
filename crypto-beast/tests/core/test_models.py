from datetime import datetime

from core.models import (
    ConfluenceScore,
    Direction,
    DirectionalBias,
    ExecutionPlan,
    ExecutionResult,
    LossCategory,
    LossClassification,
    MarketRegime,
    OrderBook,
    OrderType,
    Portfolio,
    Position,
    PositionSizing,
    RecoveryState,
    ReviewReport,
    ShieldAction,
    SignalType,
    SystemStatus,
    TradeSignal,
    ValidatedOrder,
    WinProfile,
)


class TestEnums:
    def test_direction_values(self):
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"

    def test_signal_type_values(self):
        assert SignalType.BULLISH.value == "BULLISH"
        assert SignalType.BEARISH.value == "BEARISH"
        assert SignalType.NEUTRAL.value == "NEUTRAL"

    def test_market_regime_has_all_states(self):
        regimes = [r.value for r in MarketRegime]
        assert "TRENDING_UP" in regimes
        assert "TRENDING_DOWN" in regimes
        assert "RANGING" in regimes
        assert "HIGH_VOLATILITY" in regimes
        assert "LOW_VOLATILITY" in regimes

    def test_recovery_state_order(self):
        states = list(RecoveryState)
        assert states == [
            RecoveryState.NORMAL,
            RecoveryState.CAUTIOUS,
            RecoveryState.RECOVERY,
            RecoveryState.CRITICAL,
        ]

    def test_loss_category_has_all_types(self):
        cats = [c.value for c in LossCategory]
        assert len(cats) == 8
        assert "STOP_TOO_TIGHT" in cats
        assert "FEE_EROSION" in cats


class TestDirectionalBias:
    def test_create_bias(self):
        bias = DirectionalBias(
            source="whale_tracker",
            symbol="BTCUSDT",
            direction=SignalType.BULLISH,
            confidence=0.8,
            reason="Large withdrawal detected",
        )
        assert bias.source == "whale_tracker"
        assert bias.confidence == 0.8
        assert isinstance(bias.timestamp, datetime)


class TestTradeSignal:
    def test_create_signal(self):
        signal = TradeSignal(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            confidence=0.85,
            entry_price=65000.0,
            stop_loss=64000.0,
            take_profit=67000.0,
            strategy="trend_follower",
            regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.direction == Direction.LONG
        assert signal.confidence == 0.85


class TestValidatedOrder:
    def test_create_order(self):
        signal = TradeSignal(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            confidence=0.85,
            entry_price=65000.0,
            stop_loss=64000.0,
            take_profit=67000.0,
            strategy="trend_follower",
            regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )
        order = ValidatedOrder(
            signal=signal,
            quantity=0.001,
            leverage=10,
            order_type=OrderType.LIMIT,
            risk_amount=2.0,
            max_slippage=0.001,
        )
        assert order.leverage == 10
        assert order.risk_amount == 2.0


class TestPortfolio:
    def test_create_portfolio(self):
        portfolio = Portfolio(
            equity=100.0,
            available_balance=80.0,
            positions=[],
            peak_equity=100.0,
            locked_capital=0.0,
            daily_pnl=0.0,
            total_fees_today=0.0,
            drawdown_pct=0.0,
        )
        assert portfolio.equity == 100.0
        assert portfolio.drawdown_pct == 0.0


class TestReviewReport:
    def test_create_review(self):
        report = ReviewReport(
            period="daily",
            timestamp=datetime.utcnow(),
            total_trades=10,
            wins=6,
            losses=4,
            loss_classifications=[],
            win_profiles=[],
            recommendations=["widen stops"],
            hypothetical_results={"confluence_8": 150.0},
        )
        assert report.wins == 6
        assert report.recommendations == ["widen stops"]
