from datetime import datetime
from typing import Dict, List, Optional

from core.models import EvolutionReport, BacktestResult
from core.database import Database


class Evolver:
    """Parameter optimizer with atomic config swap."""

    def __init__(self, config, db: Database):
        self._active_config = config
        self._pending_config = None
        self.db = db
        self._strategy_weights: Dict[str, float] = {
            "trend_follower": 0.2,
            "mean_reversion": 0.2,
            "momentum": 0.2,
            "breakout": 0.2,
            "scalper": 0.2,
        }

    def build_search_space(
        self, current_params: Dict[str, float], max_change: float = 0.2
    ) -> Dict[str, tuple]:
        """Build bounded search space: each param +/-max_change of current."""
        space = {}
        for key, value in current_params.items():
            delta = abs(value) * max_change
            if delta == 0:
                delta = 0.1
            space[key] = (value - delta, value + delta)
        return space

    def calculate_strategy_weights(
        self, performance: Dict[str, float]
    ) -> Dict[str, float]:
        """Reweight strategies by Sharpe ratio (softmax-like)."""
        if not performance:
            return self._strategy_weights.copy()

        # Shift all values positive and normalize
        min_perf = min(performance.values())
        shifted = {k: v - min_perf + 0.1 for k, v in performance.items()}
        total = sum(shifted.values())

        if total == 0:
            return {k: 1.0 / len(shifted) for k in shifted}

        return {k: round(v / total, 4) for k, v in shifted.items()}

    def set_pending_config(self, new_config) -> None:
        """Stage a new config for atomic swap."""
        self._pending_config = new_config

    def apply_if_pending(self) -> bool:
        """Apply pending config if one exists. Returns True if applied."""
        if self._pending_config is not None:
            self._active_config = self._pending_config
            self._pending_config = None
            return True
        return False

    def get_active_config(self):
        return self._active_config

    def get_strategy_weights(self) -> Dict[str, float]:
        return self._strategy_weights.copy()

    def update_strategy_weights(self, new_weights: Dict[str, float]) -> None:
        self._strategy_weights.update(new_weights)

    def log_evolution(self, report: EvolutionReport) -> None:
        """Save evolution report to database."""
        import json

        self.db.execute(
            "INSERT INTO evolution_log (timestamp, parameters_before, parameters_after, backtest_sharpe, changes_summary) VALUES (?, ?, ?, ?, ?)",
            (
                report.timestamp.isoformat(),
                json.dumps(report.parameters_changed),
                json.dumps(report.strategy_weights),
                report.backtest_sharpe_after,
                json.dumps(report.recommendations_applied),
            ),
        )
