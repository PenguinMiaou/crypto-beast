"""Tests for RecoveryMode — now validates via DefenseManager.

The old RecoveryMode class still exists for backward compat, but these tests
verify the same behavior via DefenseManager.
"""
import os
import pytest

from core.models import Portfolio, RecoveryState


def make_portfolio(drawdown: float):
    equity = 100.0 * (1 - drawdown)
    return Portfolio(
        equity=equity, available_balance=equity * 0.8, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=drawdown,
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


class TestRecoveryMode:
    def test_normal_state(self):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(make_portfolio(0.02))
        assert result.recovery_state == RecoveryState.NORMAL

    def test_cautious_state(self):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(make_portfolio(0.07))
        assert result.recovery_state == RecoveryState.CAUTIOUS

    def test_recovery_state(self):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(make_portfolio(0.15))
        assert result.recovery_state == RecoveryState.RECOVERY

    def test_critical_state(self):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(make_portfolio(0.25))
        assert result.recovery_state == RecoveryState.CRITICAL

    def test_adjust_reduces_leverage_in_cautious(self):
        from defense.defense_manager import DefenseManager
        from config import Config

        dm = DefenseManager(Config())
        result = dm.check(make_portfolio(0.07))
        params = result.params
        assert params["max_leverage"] <= 5
        assert params["min_confidence"] >= 0.5
