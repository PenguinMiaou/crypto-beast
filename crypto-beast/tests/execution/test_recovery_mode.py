import pytest

from core.models import Portfolio, RecoveryState


def make_portfolio(drawdown: float):
    equity = 100.0 * (1 - drawdown)
    return Portfolio(
        equity=equity, available_balance=equity * 0.8, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=drawdown,
    )


class TestRecoveryMode:
    def test_normal_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.02))
        assert state == RecoveryState.NORMAL

    def test_cautious_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.07))
        assert state == RecoveryState.CAUTIOUS

    def test_recovery_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.15))
        assert state == RecoveryState.RECOVERY

    def test_critical_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.25))
        assert state == RecoveryState.CRITICAL

    def test_adjust_reduces_leverage_in_cautious(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        rm.assess_state(make_portfolio(0.07))
        params = rm.get_adjusted_params()
        assert params["max_leverage"] <= 3
        assert params["min_confidence"] > 0.5
