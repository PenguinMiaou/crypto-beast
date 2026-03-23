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
            "trend_follower": 0.15,
            "mean_reversion": 0.15,
            "momentum": 0.15,
            "breakout": 0.15,
            "ichimoku_cloud": 0.15,
            "enhanced_bb_rsi": 0.15,
            "funding_rate_arb": 0.10,
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

    # Minimum closed trades before enabling Optuna parameter optimization
    MIN_TRADES_FOR_OPTUNA = 30

    async def run_daily_evolution(self, data: dict = None, recommendations: List[str] = None) -> Optional[EvolutionReport]:
        """Run daily evolution: always reweight strategies, only optimize params with enough data.

        Phase 1 (always): Backtest each strategy, reweight by performance
        Phase 2 (gated): Optuna parameter optimization — only if enough real trades exist
                         Uses walk-forward validation to prevent overfitting.
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

        # === Phase 1: Strategy weight rebalancing (always runs) ===
        # Import all active strategies (must match strategy_engine._strategies)
        from strategy.ichimoku_cloud import IchimokuCloud
        from strategy.enhanced_bb_rsi import EnhancedBbRsi
        from strategy.funding_rate_arb import FundingRateArb

        strategies = {
            "trend_follower": TrendFollower(),
            "mean_reversion": MeanReversion(),
            "momentum": Momentum(),
            "breakout": Breakout(),
            "ichimoku_cloud": IchimokuCloud(),
            "enhanced_bb_rsi": EnhancedBbRsi(),
            "funding_rate_arb": FundingRateArb(),
        }

        performances: Dict[str, float] = {}
        for name, strategy in strategies.items():
            try:
                # Average Sharpe across all available symbols
                sharpe_sum = 0.0
                sym_count = 0
                for sym, df in data.items():
                    if len(df) >= 200:
                        result = backtest_lab.run_backtest(strategy, df, sym)
                        sharpe_sum += result.sharpe_ratio
                        sym_count += 1
                performances[name] = sharpe_sum / sym_count if sym_count > 0 else 0.0
            except Exception as e:
                logger.warning(f"Backtest failed for {name}: {e}")
                performances[name] = 0.0

        new_weights = self.calculate_strategy_weights(performances)
        self.update_strategy_weights(new_weights)

        # === Phase 2: Optuna parameter optimization (gated by trade count) ===
        # Check if enough real trades exist to justify optimization
        trade_count = 0
        try:
            row = self.db.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'").fetchone()
            trade_count = row[0] if row else 0
        except Exception:
            pass

        best = {}
        # Average Sharpe across all strategies as summary metric
        sharpe_values = [v for v in performances.values() if v != 0]
        sharpe_before = sum(sharpe_values) / len(sharpe_values) if sharpe_values else 0
        sharpe_after = sharpe_before  # Default: no change until Optuna runs

        if trade_count < self.MIN_TRADES_FOR_OPTUNA:
            logger.info(f"Optuna skipped: {trade_count}/{self.MIN_TRADES_FOR_OPTUNA} trades (weights-only mode)")
        else:
            # Walk-forward: 70% train / 30% test
            split_idx = int(len(sample_data) * 0.7)
            train_data = sample_data.iloc[:split_idx].copy()
            test_data = sample_data.iloc[split_idx:].copy()

            if len(train_data) < 100 or len(test_data) < 50:
                logger.info("Not enough data for walk-forward split, skipping Optuna")
            else:
                def objective(trial: optuna.Trial) -> float:
                    fast_ema = trial.suggest_int("fast_ema", 5, 15)
                    slow_ema = trial.suggest_int("slow_ema", 15, 30)
                    atr_sl = trial.suggest_float("atr_sl_mult", 1.0, 3.0)
                    atr_tp = trial.suggest_float("atr_tp_mult", 2.0, 5.0)

                    if fast_ema >= slow_ema:
                        return -999

                    strategy = TrendFollower(fast_ema=fast_ema, slow_ema=slow_ema,
                                              atr_sl_mult=atr_sl, atr_tp_mult=atr_tp)
                    # Train on 70% only
                    result = backtest_lab.run_backtest(strategy, train_data, sample_symbol)

                    if result.total_trades == 0:
                        return -999
                    return result.sharpe_ratio * (result.total_trades ** 0.5)

                study = optuna.create_study(direction="maximize")
                study.optimize(objective, n_trials=30, show_progress_bar=False)

                best = study.best_params
                logger.info(f"Optuna best params: {best} (train_value={study.best_value:.4f})")

                # Validate on 30% test set (out-of-sample)
                best_strategy = TrendFollower(
                    fast_ema=best.get("fast_ema", 9),
                    slow_ema=best.get("slow_ema", 21),
                    atr_sl_mult=best.get("atr_sl_mult", 1.5),
                    atr_tp_mult=best.get("atr_tp_mult", 3.0),
                )
                test_result = backtest_lab.run_backtest(best_strategy, test_data, sample_symbol)
                sharpe_after = test_result.sharpe_ratio

                # Reject overfitting: test Sharpe must be > 0 and <= 5.0
                if sharpe_after <= 0:
                    logger.warning(f"Optuna rejected: test Sharpe {sharpe_after:.2f} <= 0 (overfitting)")
                    best = {}
                    sharpe_after = sharpe_before
                elif sharpe_after > 5.0:
                    logger.warning(f"Optuna rejected: test Sharpe {sharpe_after:.2f} > 5.0 (likely overfitting)")
                    best = {}
                    sharpe_after = sharpe_before
                else:
                    logger.info(f"Optuna validated: test Sharpe {sharpe_after:.2f} (accepted)")

        # Build report
        report = EvolutionReport(
            timestamp=datetime.now(timezone.utc),
            parameters_changed=best,
            backtest_sharpe_before=round(sharpe_before, 4),
            backtest_sharpe_after=round(sharpe_after, 4),
            strategy_weights=new_weights,
            recommendations_applied=recommendations or [],
        )

        self.log_evolution(report)
        logger.info(f"Evolution complete: Sharpe {sharpe_before:.4f} -> {sharpe_after:.4f} | weights={new_weights}")

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
