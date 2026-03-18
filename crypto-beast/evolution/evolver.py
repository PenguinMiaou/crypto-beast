import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

from core.models import EvolutionReport, BacktestResult
from core.database import Database

logger = logging.getLogger(__name__)


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

    async def run_daily_evolution(self, data: dict = None, recommendations: List[str] = None) -> Optional[EvolutionReport]:
        """Run daily parameter optimization using Optuna.

        Args:
            data: {symbol: DataFrame} market data for backtesting
            recommendations: from TradeReviewer (e.g., "widen stops")
        """
        from strategy.trend_follower import TrendFollower
        from strategy.mean_reversion import MeanReversion
        from strategy.momentum import Momentum
        from strategy.breakout import Breakout
        from strategy.scalper import Scalper
        from evolution.backtest_lab import BacktestLab

        if not data:
            logger.info("No data provided for evolution, skipping")
            return None

        backtest_lab = BacktestLab()

        # Get sample data (use first available symbol)
        sample_data = None
        sample_symbol = None
        for sym, df in data.items():
            if len(df) >= 200:
                sample_data = df
                sample_symbol = sym
                break

        if sample_data is None:
            logger.warning("Not enough data for evolution")
            return None

        # Current strategy performances
        strategies = {
            "trend_follower": TrendFollower(),
            "mean_reversion": MeanReversion(),
            "momentum": Momentum(),
            "breakout": Breakout(),
            "scalper": Scalper(),
        }

        # Backtest each strategy to get current performance
        performances: Dict[str, float] = {}
        for name, strategy in strategies.items():
            try:
                result = backtest_lab.run_backtest(strategy, sample_data, sample_symbol)
                performances[name] = result.sharpe_ratio
            except Exception as e:
                logger.warning(f"Backtest failed for {name}: {e}")
                performances[name] = 0.0

        sharpe_before = sum(performances.values()) / len(performances) if performances else 0

        # Optuna optimization for TrendFollower params
        def objective(trial: optuna.Trial) -> float:
            fast_ema = trial.suggest_int("fast_ema", 5, 15)
            slow_ema = trial.suggest_int("slow_ema", 15, 30)
            atr_sl = trial.suggest_float("atr_sl_mult", 1.0, 3.0)
            atr_tp = trial.suggest_float("atr_tp_mult", 2.0, 5.0)

            if fast_ema >= slow_ema:
                return -999

            strategy = TrendFollower(fast_ema=fast_ema, slow_ema=slow_ema,
                                      atr_sl_mult=atr_sl, atr_tp_mult=atr_tp)
            result = backtest_lab.run_backtest(strategy, sample_data, sample_symbol)

            # Fitness: sharpe * sqrt(trades) to reward both quality and frequency
            if result.total_trades == 0:
                return -999
            return result.sharpe_ratio * (result.total_trades ** 0.5)

        study = optuna.create_study(direction="maximize")
        study.optimize(objective, n_trials=30, show_progress_bar=False)

        best = study.best_params
        logger.info(f"Optuna best params: {best} (value={study.best_value:.4f})")

        # Backtest with best params to get new sharpe
        best_strategy = TrendFollower(
            fast_ema=best.get("fast_ema", 9),
            slow_ema=best.get("slow_ema", 21),
            atr_sl_mult=best.get("atr_sl_mult", 1.5),
            atr_tp_mult=best.get("atr_tp_mult", 3.0),
        )
        best_result = backtest_lab.run_backtest(best_strategy, sample_data, sample_symbol)
        sharpe_after = best_result.sharpe_ratio

        # Reweight strategies based on performance
        new_weights = self.calculate_strategy_weights(performances)
        self.update_strategy_weights(new_weights)

        # Build report
        report = EvolutionReport(
            timestamp=datetime.now(timezone.utc),
            parameters_changed=best,
            backtest_sharpe_before=round(sharpe_before, 4),
            backtest_sharpe_after=round(sharpe_after, 4),
            strategy_weights=new_weights,
            recommendations_applied=recommendations or [],
        )

        # Log to DB
        self.log_evolution(report)

        logger.info(f"Evolution complete: Sharpe {sharpe_before:.4f} -> {sharpe_after:.4f}")

        return report

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
