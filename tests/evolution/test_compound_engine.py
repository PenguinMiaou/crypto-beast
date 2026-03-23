"""Tests for compound growth engine."""

import pytest
from datetime import datetime, timezone

from config import Config
from core.models import Portfolio, PositionSizing
from evolution.compound_engine import CompoundEngine


@pytest.fixture
def config():
    cfg = Config.__new__(Config)
    cfg.kelly_fraction = 0.5
    cfg.profit_lock_milestones = {150: 20, 200: 50, 500: 150}
    return cfg


@pytest.fixture
def engine(config, db):
    return CompoundEngine(config, db)


@pytest.fixture
def db_with_trades(db):
    """Insert 20 trades: 12 wins (pnl=1.5), 8 losses (pnl=-1.0)."""
    for i in range(12):
        db.execute(
            "INSERT INTO trades (symbol, side, strategy, entry_price, exit_price, quantity, leverage, pnl, fees, status, entry_time, exit_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("BTCUSDT", "LONG", "trend_follower", 65000, 65150, 0.01, 1, 1.5, 0.05, "CLOSED", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
    for i in range(8):
        db.execute(
            "INSERT INTO trades (symbol, side, strategy, entry_price, exit_price, quantity, leverage, pnl, fees, status, entry_time, exit_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("BTCUSDT", "LONG", "trend_follower", 65000, 64900, 0.01, 1, -1.0, 0.05, "CLOSED", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
    return db


class TestKellyFraction:
    def test_kelly_with_known_win_rate(self, config, db_with_trades):
        """60% win rate, 1.5 avg_win / 1.0 avg_loss -> verify formula with half-Kelly."""
        engine = CompoundEngine(config, db_with_trades)
        fraction = engine.get_kelly_fraction("trend_follower")

        # Manual calculation: p=0.6, b=1.5/1.0=1.5
        # kelly = (1.5*0.6 - 0.4) / 1.5 = (0.9 - 0.4) / 1.5 = 0.5/1.5 = 1/3
        # half-kelly = 1/3 * 0.5 = 1/6 ≈ 0.1667
        expected = (1 / 3) * 0.5
        assert abs(fraction - expected) < 0.001

    def test_fewer_than_5_trades_returns_default(self, engine):
        """Less than 5 trades should return conservative default 0.02."""
        # Insert only 3 trades
        for i in range(3):
            engine.db.execute(
                "INSERT INTO trades (symbol, side, strategy, entry_price, exit_price, quantity, leverage, pnl, fees, status, entry_time, exit_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("BTCUSDT", "LONG", "trend_follower", 65000, 65100, 0.01, 1, 1.0, 0.05, "CLOSED", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            )
        assert engine.get_kelly_fraction("trend_follower") == 0.02

    def test_all_wins_returns_cap(self, engine):
        """All winning trades should return 0.1."""
        for i in range(15):
            engine.db.execute(
                "INSERT INTO trades (symbol, side, strategy, entry_price, exit_price, quantity, leverage, pnl, fees, status, entry_time, exit_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("BTCUSDT", "LONG", "momentum", 65000, 65200, 0.01, 1, 2.0, 0.05, "CLOSED", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
            )
        assert engine.get_kelly_fraction("momentum") == 0.1


class TestProfitLocking:
    def test_lock_at_150(self, engine):
        """Equity at $150 should lock $20."""
        engine._update_locks(150.0)
        assert engine.get_locked_capital() == 20.0

    def test_lock_at_200(self, engine):
        """Equity at $200 should lock $50."""
        engine._update_locks(200.0)
        assert engine.get_locked_capital() == 50.0

    def test_lock_never_decreases(self, engine):
        """Locked capital should never decrease even if equity drops."""
        engine._update_locks(200.0)
        assert engine.get_locked_capital() == 50.0
        engine._update_locks(140.0)
        assert engine.get_locked_capital() == 50.0

    def test_available_capital_equals_equity_minus_locked(self, config, db_with_trades):
        """Available capital = equity - locked_capital."""
        engine = CompoundEngine(config, db_with_trades)
        portfolio = Portfolio(
            equity=200.0,
            available_balance=200.0,
            positions=[],
            peak_equity=200.0,
            locked_capital=0.0,
            daily_pnl=0.0,
            total_fees_today=0.0,
            drawdown_pct=0.0,
        )
        sizing = engine.update_position_sizing(portfolio)
        assert sizing.available_capital == 200.0 - 50.0  # $200 equity -> $50 locked


class TestUpdatePositionSizing:
    def test_returns_position_sizing(self, config, db_with_trades):
        """update_position_sizing should return a valid PositionSizing."""
        engine = CompoundEngine(config, db_with_trades)
        portfolio = Portfolio(
            equity=150.0,
            available_balance=150.0,
            positions=[],
            peak_equity=150.0,
            locked_capital=0.0,
            daily_pnl=0.0,
            total_fees_today=0.0,
            drawdown_pct=0.0,
        )
        sizing = engine.update_position_sizing(portfolio)

        assert isinstance(sizing, PositionSizing)
        assert sizing.available_capital == 150.0 - 20.0  # $150 equity -> $20 locked
        assert sizing.max_position_pct == 0.3
        # Dynamic query: only strategies present in DB are returned
        assert "trend_follower" in sizing.kelly_fractions
        assert len(sizing.kelly_fractions) >= 1
