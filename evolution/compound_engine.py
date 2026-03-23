"""Compound growth engine with Kelly sizing, profit locking, and strategy rehabilitation."""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from loguru import logger

from config import Config
from core.database import Database
from core.models import Portfolio, PositionSizing


# Regime → strategies that are naturally suited
REGIME_STRATEGY_FIT: Dict[str, List[str]] = {
    "TRENDING_UP": ["trend_follower", "momentum", "ichimoku_cloud", "breakout"],
    "TRENDING_DOWN": ["trend_follower", "momentum", "ichimoku_cloud", "breakout"],
    "RANGING": ["mean_reversion", "enhanced_bb_rsi", "scalper"],
    "HIGH_VOLATILITY": ["breakout", "ichimoku_cloud", "trend_follower"],
    "LOW_VOLATILITY": ["mean_reversion", "enhanced_bb_rsi"],
    "TRANSITIONING": [],  # No strategy is naturally suited during transition
}


class CompoundEngine:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._locked_capital = 0.0

    def get_kelly_fraction(self, strategy: str, current_regime: Optional[str] = None) -> float:
        """Calculate half-Kelly for a strategy, with 3-layer rehabilitation.

        Rehabilitation layers (any one can unblock a strategy):
        A) Time decay: only use trades from last 7 days (old failures expire)
        B) Regime fit: if current regime suits this strategy, use relaxed threshold
        C) Staleness: if no trades in 7 days, reset to default (allow trading)
        """
        # Query trades from last 7 days only (Layer A: time decay)
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        rows = self.db.execute(
            "SELECT pnl FROM trades WHERE strategy = ? AND status = 'CLOSED' "
            "AND exit_time >= ? ORDER BY exit_time DESC LIMIT 100",
            (strategy, seven_days_ago),
        ).fetchall()

        # Layer C: if too few recent trades (stale/insufficient), reset to default → allow trading
        if len(rows) < 5:
            return 0.02  # Default conservative fraction (need at least 5 trades in 7 days)

        pnls = [r[0] for r in rows if r[0] is not None]
        if not pnls:
            return 0.02

        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        if not wins:
            # All recent trades are losses
            # Layer B: regime fit — if current regime suits this strategy, give a chance
            if current_regime and strategy in REGIME_STRATEGY_FIT.get(current_regime, []):
                logger.debug(
                    f"Kelly rehab: {strategy} all losses but regime {current_regime} fits → 0.01"
                )
                return 0.01  # Minimal fraction, allows very small trades
            return 0.0  # Truly blocked

        if not losses:
            return 0.1

        p = len(wins) / len(pnls)
        b = (sum(wins) / len(wins)) / (sum(losses) / len(losses))
        kelly = (b * p - (1 - p)) / b
        half_kelly = kelly * self.config.kelly_fraction

        if half_kelly <= 0:
            # Negative Kelly from recent data
            # Layer B: regime fit
            if current_regime and strategy in REGIME_STRATEGY_FIT.get(current_regime, []):
                logger.debug(
                    f"Kelly rehab: {strategy} negative Kelly but regime {current_regime} fits → 0.01"
                )
                return 0.01
            return 0.0

        return min(0.2, half_kelly)

    def update_position_sizing(self, portfolio: Portfolio) -> PositionSizing:
        """Update position sizing based on current portfolio."""
        self._update_locks(portfolio.equity)
        available = portfolio.equity - self._locked_capital
        fractions: Dict[str, float] = {}
        strategies = [r[0] for r in self.db.execute(
            "SELECT DISTINCT strategy FROM trades WHERE status='CLOSED' AND strategy IS NOT NULL"
        ).fetchall()]
        if not strategies:
            strategies = ["trend_follower", "mean_reversion", "momentum", "breakout",
                          "ichimoku_cloud", "enhanced_bb_rsi", "funding_rate_arb"]
        for strategy in strategies:
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
