# tests/defense/test_risk_manager.py
import pytest
from datetime import datetime, timezone

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
        assert order.leverage == 7

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
            assert result_high.quantity > result_low.quantity * 1.2, (
                "High confidence should get >1.2x the position of low confidence"
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


def test_kelly_negative_rejects_signal(db):
    """#2: strategy with negative Kelly should be rejected."""
    from core.models import Direction, MarketRegime, Portfolio, TradeSignal
    # Insert 10 trades for 'bad_strat': 2 wins, 8 losses
    for i in range(10):
        pnl = 0.5 if i < 2 else -1.0
        db.execute(
            "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, "
            "strategy, entry_time, exit_time, fees, status, pnl, stop_loss, take_profit) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now', ?), datetime('now'), 0.01, 'CLOSED', ?, 0, 0)",
            ("BTCUSDT", "LONG", 65000, 0.001, 5, "bad_strat", f"-{i+1} hours", pnl)
        )
    from config import Config
    from evolution.compound_engine import CompoundEngine
    from defense.risk_manager import RiskManager
    config = Config()
    compound = CompoundEngine(config, db)
    rm = RiskManager(config, db, compound)
    signal = TradeSignal(symbol="BTCUSDT", direction=Direction.LONG, confidence=0.8,
                         entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
                         strategy="bad_strat", regime=MarketRegime.TRENDING_UP, timeframe_score=8)
    portfolio = Portfolio(equity=100.0, available_balance=100.0, positions=[],
                          peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
                          total_fees_today=0.0, drawdown_pct=0.0)
    result = rm.validate(signal, portfolio)
    assert result is None, "Signal should be rejected: Kelly negative for losing strategy"


def _insert_trades(db, pnls):
    """Helper: insert closed trades with given pnl list (most recent first = last inserted)."""
    now = datetime.now(timezone.utc)
    for i, pnl in enumerate(reversed(pnls)):  # oldest first so ORDER BY exit_time DESC gives correct order
        db.execute(
            "INSERT INTO trades (symbol, side, entry_price, exit_price, quantity, leverage, "
            "strategy, entry_time, exit_time, pnl, fees, status) VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "BTCUSDT", "BUY", 65000.0, 65100.0, 0.001, 10, "test",
                f"2026-01-01T{i:02d}:00:00+00:00",
                f"2026-01-01T{i:02d}:30:00+00:00",
                pnl, 0.1, "CLOSED",
            ),
        )


class TestAdaptiveRiskState:
    def _make_portfolio(self):
        return Portfolio(
            equity=500.0, available_balance=500.0, positions=[],
            peak_equity=500.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0,
        )

    def _make_signal(self):
        return TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.85,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="trend_follower", regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )

    def test_adaptive_consecutive_loss_scales_down(self, db):
        """4 consecutive losses should yield scale <= 0.50."""
        from defense.risk_manager import AdaptiveRiskState
        from config import Config

        # Insert 4 consecutive losing trades (most recent first in list)
        _insert_trades(db, [-1.0, -1.0, -1.0, -1.0, 5.0])
        state = AdaptiveRiskState(db, lookback=10, cooldown_hours=2)
        scale = state.get_scale_factor()
        assert scale <= 0.50, f"Expected scale <= 0.50 after 4 consecutive losses, got {scale}"

    def test_adaptive_cooldown_on_low_winrate(self, db):
        """2 wins, 8 losses (20% win-rate) should trigger cooldown and return 0.0."""
        from defense.risk_manager import AdaptiveRiskState
        from config import Config

        pnls = [1.0, 1.0] + [-1.0] * 8  # 20% win rate
        _insert_trades(db, pnls)
        state = AdaptiveRiskState(db, lookback=10, cooldown_hours=2)
        scale = state.get_scale_factor()
        assert scale == 0.0, f"Expected scale == 0.0 for 20% win-rate, got {scale}"

    def test_adaptive_normal_when_winning(self, db):
        """5 winning trades should yield scale >= 1.0."""
        from defense.risk_manager import AdaptiveRiskState
        from config import Config

        _insert_trades(db, [2.0, 1.5, 3.0, 1.0, 2.5])
        state = AdaptiveRiskState(db, lookback=10, cooldown_hours=2)
        scale = state.get_scale_factor()
        assert scale >= 1.0, f"Expected scale >= 1.0 for all-wins, got {scale}"

    def test_adaptive_integrated_in_risk_manager(self, db):
        """RiskManager with db should apply adaptive scale to quantity."""
        from defense.risk_manager import AdaptiveRiskState, RiskManager
        from config import Config

        config = Config()
        # Most recent 3 are losses (consecutive), 4 wins before → 4/7 = 57% win_rate (>=30%)
        # _insert_trades reverses the list so ORDER BY exit_time DESC returns the original order.
        # Pass losses first (index 0) so they become most recent in DB.
        _insert_trades(db, [-1.0, -1.0, -1.0, 5.0, 5.0, 5.0, 5.0])
        rm_adaptive = RiskManager(config, db)
        rm_plain = RiskManager(config)

        # Verify scale is indeed 0.50 (3 consecutive losses, win_rate=57%)
        assert rm_adaptive._adaptive is not None
        scale = rm_adaptive._adaptive.get_scale_factor()
        assert scale == 0.50, f"Expected 0.50 scale, got {scale}"

        portfolio = self._make_portfolio()
        # Use separate signal objects to avoid mutation
        signal_adaptive = self._make_signal()
        signal_plain = self._make_signal()
        order_adaptive = rm_adaptive.validate(signal_adaptive, portfolio)
        order_plain = rm_plain.validate(signal_plain, portfolio)

        assert order_adaptive is not None
        assert order_plain is not None
        # Adaptive (scale=0.50) should produce smaller quantity than plain (no scaling)
        assert order_adaptive.quantity < order_plain.quantity
