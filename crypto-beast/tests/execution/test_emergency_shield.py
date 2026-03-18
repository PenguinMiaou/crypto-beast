"""Tests for EmergencyShield — now delegates to DefenseManager.

The old EmergencyShield class still exists for backward compat, but these tests
verify the same behavior via DefenseManager.
"""
import os
import pytest
from datetime import datetime

from core.models import Direction, Portfolio, Position, ShieldAction


@pytest.fixture
def healthy_portfolio():
    return Portfolio(
        equity=100.0, available_balance=80.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=0.0,
    )


@pytest.fixture
def daily_loss_portfolio():
    return Portfolio(
        equity=88.0, available_balance=60.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=-12.0, total_fees_today=0.5, drawdown_pct=0.12,
    )


@pytest.fixture
def critical_drawdown_portfolio():
    return Portfolio(
        equity=65.0, available_balance=40.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=-5.0, total_fees_today=0.3, drawdown_pct=0.35,
    )


@pytest.fixture(autouse=True)
def cleanup_state_file():
    from defense.defense_manager import DefenseManager
    state_file = DefenseManager._STATE_FILE
    if os.path.exists(state_file):
        os.remove(state_file)
    yield
    if os.path.exists(state_file):
        os.remove(state_file)


class TestEmergencyShield:
    def test_continue_on_healthy(self, healthy_portfolio):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(healthy_portfolio)
        assert result.action == ShieldAction.CONTINUE

    def test_halt_on_daily_loss(self, daily_loss_portfolio):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(daily_loss_portfolio)
        assert result.action == ShieldAction.HALT

    def test_emergency_close_on_critical_drawdown(self, critical_drawdown_portfolio):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(critical_drawdown_portfolio)
        assert result.action == ShieldAction.EMERGENCY_CLOSE

    def test_cooldown_after_halt(self, daily_loss_portfolio):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        dm.check(daily_loss_portfolio)
        assert dm.is_in_cooldown() is True

    def test_reset_clears_cooldown(self, daily_loss_portfolio):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        dm.check(daily_loss_portfolio)
        dm.reset()
        assert dm.is_in_cooldown() is False
