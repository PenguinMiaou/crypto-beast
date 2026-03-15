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


class TestEmergencyShield:
    def test_continue_on_healthy(self, healthy_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(healthy_portfolio)
        assert action == ShieldAction.CONTINUE

    def test_halt_on_daily_loss(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(daily_loss_portfolio)
        assert action == ShieldAction.HALT

    def test_emergency_close_on_critical_drawdown(self, critical_drawdown_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(critical_drawdown_portfolio)
        assert action == ShieldAction.EMERGENCY_CLOSE

    def test_cooldown_after_halt(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        shield.check(daily_loss_portfolio)
        assert shield.is_in_cooldown() is True

    def test_reset_clears_cooldown(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        shield.check(daily_loss_portfolio)
        shield.reset()
        assert shield.is_in_cooldown() is False
