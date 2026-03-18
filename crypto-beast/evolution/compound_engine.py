"""Compound growth engine with Kelly sizing and profit locking."""

from typing import Dict, Optional

from config import Config
from core.database import Database
from core.models import Portfolio, PositionSizing


class CompoundEngine:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._locked_capital = 0.0

    def get_kelly_fraction(self, strategy: str) -> float:
        """Calculate half-Kelly for a strategy from its trade history."""
        rows = self.db.execute(
            "SELECT pnl FROM trades WHERE strategy = ? AND status = 'CLOSED' ORDER BY exit_time DESC LIMIT 100",
            (strategy,)
        ).fetchall()
        if len(rows) < 10:
            return 0.02  # Default conservative fraction
        pnls = [r[0] for r in rows if r[0] is not None]
        if not pnls:
            return 0.02
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        if not losses:
            return 0.1
        p = len(wins) / len(pnls)
        b = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        kelly = (b * p - (1 - p)) / b
        return max(0.01, min(0.2, kelly * self.config.kelly_fraction))

    def update_position_sizing(self, portfolio: Portfolio) -> PositionSizing:
        """Update position sizing based on current portfolio."""
        self._update_locks(portfolio.equity)
        available = portfolio.equity - self._locked_capital
        fractions: Dict[str, float] = {}
        for strategy in ["trend_follower", "mean_reversion", "momentum", "breakout", "scalper"]:
            fractions[strategy] = self.get_kelly_fraction(strategy)
        return PositionSizing(
            available_capital=available,
            kelly_fractions=fractions,
            max_position_pct=0.3,
        )

    def _update_locks(self, equity: float) -> None:
        """Lock profits at milestones."""
        for milestone, lock_amount in sorted(self.config.profit_lock_milestones.items()):
            if equity >= milestone:
                self._locked_capital = max(self._locked_capital, lock_amount)

    def get_locked_capital(self) -> float:
        return self._locked_capital
