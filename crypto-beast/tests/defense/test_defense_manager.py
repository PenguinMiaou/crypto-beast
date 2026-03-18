import os
import pytest

from config import Config
from core.models import Portfolio, RecoveryState, ShieldAction


def _make_portfolio(equity=100, peak=100, daily_pnl=0):
    dd = (peak - equity) / peak if peak > 0 else 0
    return Portfolio(
        equity=equity, available_balance=equity, positions=[],
        peak_equity=peak, locked_capital=0, daily_pnl=daily_pnl,
        total_fees_today=0, drawdown_pct=dd,
    )


@pytest.fixture(autouse=True)
def cleanup_state_file():
    """Remove shield.state before and after each test."""
    from defense.defense_manager import DefenseManager
    state_file = DefenseManager._STATE_FILE
    if os.path.exists(state_file):
        os.remove(state_file)
    yield
    if os.path.exists(state_file):
        os.remove(state_file)


class TestDefenseManager:
    def test_normal_state(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        result = dm.check(_make_portfolio(100, 100))
        assert result.action == ShieldAction.CONTINUE
        assert result.recovery_state == RecoveryState.NORMAL
        assert result.params["max_leverage"] == 10

    def test_cautious_at_5pct(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        # 6% drawdown (above 5% cautious threshold)
        result = dm.check(_make_portfolio(94, 100))
        assert result.recovery_state == RecoveryState.CAUTIOUS
        assert result.params["max_leverage"] == 5

    def test_recovery_at_10pct(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        result = dm.check(_make_portfolio(88, 100))
        assert result.recovery_state == RecoveryState.RECOVERY
        assert result.params["max_leverage"] == 3

    def test_critical_at_20pct(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        result = dm.check(_make_portfolio(79, 100))
        assert result.recovery_state == RecoveryState.CRITICAL
        assert result.params["max_leverage"] == 2
        assert result.params["min_confidence"] == 0.7

    def test_halt_at_10pct_daily(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        result = dm.check(_make_portfolio(90, 100, daily_pnl=-10))
        assert result.action == ShieldAction.HALT

    def test_emergency_at_30pct_dd(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        result = dm.check(_make_portfolio(70, 100))
        assert result.action == ShieldAction.EMERGENCY_CLOSE

    def test_halt_persists_to_disk(self):
        from defense.defense_manager import DefenseManager
        dm1 = DefenseManager(Config())
        dm1.check(_make_portfolio(90, 100, daily_pnl=-10))
        assert dm1.is_halted()
        # New instance should load state from disk
        dm2 = DefenseManager(Config())
        assert dm2.is_halted()

    def test_already_notified_on_repeat(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        r1 = dm.check(_make_portfolio(70, 100))
        assert r1.action == ShieldAction.EMERGENCY_CLOSE
        r2 = dm.check(_make_portfolio(70, 100))
        assert r2.action == ShieldAction.ALREADY_NOTIFIED

    def test_cooldown_active(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        dm.check(_make_portfolio(90, 100, daily_pnl=-10))
        assert dm.is_in_cooldown() is True

    def test_reset_clears_all(self):
        from defense.defense_manager import DefenseManager
        dm = DefenseManager(Config())
        dm.check(_make_portfolio(90, 100, daily_pnl=-10))
        dm.reset()
        assert dm.is_halted() is False
        assert dm.is_in_cooldown() is False
        assert dm.current_state == RecoveryState.NORMAL
        assert dm.pop_just_resumed() is True

    def test_relaxed_params_vs_old(self):
        """Verify params are relaxed compared to old RecoveryMode."""
        from defense.defense_manager import RECOVERY_PARAMS
        # Old NORMAL had min_confidence 0.5, new has 0.3
        assert RECOVERY_PARAMS[RecoveryState.NORMAL]["min_confidence"] == 0.3
        # Old CRITICAL had max_leverage 1, new has 2
        assert RECOVERY_PARAMS[RecoveryState.CRITICAL]["max_leverage"] == 2
