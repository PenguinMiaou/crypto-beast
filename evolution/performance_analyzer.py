"""Comprehensive backtest performance metrics calculator."""
import math
from typing import Dict, List, Optional

import numpy as np


class PerformanceAnalyzer:
    """Calculate comprehensive backtest performance metrics."""

    def calculate(self, trades: List[dict], initial_capital: float = 100.0) -> dict:
        """Calculate all metrics from a list of trade dicts.

        Each trade dict should have: pnl, fees, direction, entry, exit
        Optional: strategy, regime, hold_time

        Returns dict with all metrics.
        """
        if not trades:
            return self._empty_result()

        pnls = [(t.get("pnl") or 0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_trades = len(trades)
        win_count = len(wins)
        win_rate = win_count / total_trades if total_trades > 0 else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean([abs(l) for l in losses]) if losses else 0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else float("inf")

        # Equity curve
        equity_curve = [initial_capital]
        for pnl in pnls:
            equity_curve.append(equity_curve[-1] + pnl)

        # Max drawdown
        peak = initial_capital
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Sharpe ratio (annualized, assuming trade-level returns)
        if len(pnls) > 1:
            returns = np.array(pnls) / initial_capital
            sharpe = (
                float(np.mean(returns) / np.std(returns) * math.sqrt(252))
                if np.std(returns) > 0
                else 0.0
            )
        else:
            sharpe = 0.0

        # Sortino ratio (only downside deviation)
        if len(pnls) > 1:
            returns = np.array(pnls) / initial_capital
            downside = returns[returns < 0]
            downside_std = float(np.std(downside)) if len(downside) > 0 else 0.0
            sortino = (
                float(np.mean(returns) / downside_std * math.sqrt(252))
                if downside_std > 0
                else 0.0
            )
        else:
            sortino = 0.0

        # Net profit
        net_profit = sum(pnls)
        total_return = net_profit / initial_capital

        # Calmar ratio
        calmar = (total_return / max_dd) if max_dd > 0 else 0.0

        # By strategy and regime breakdown
        by_strategy = self._breakdown_by(trades, "strategy")
        by_regime = self._breakdown_by(trades, "regime")

        return {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "avg_win": round(float(avg_win), 4),
            "avg_loss": round(float(avg_loss), 4),
            "payoff_ratio": round(float(payoff_ratio), 4),
            "net_profit": round(net_profit, 4),
            "total_return": round(total_return, 4),
            "max_drawdown": round(max_dd, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(float(calmar), 4),
            "gross_profit": round(gross_profit, 4),
            "gross_loss": round(gross_loss, 4),
            "by_strategy": by_strategy,
            "by_regime": by_regime,
            "equity_curve": equity_curve,
        }

    def _breakdown_by(self, trades: List[dict], key: str) -> Dict[str, dict]:
        """Break down metrics by a grouping key (strategy, regime)."""
        groups: Dict[str, List[dict]] = {}
        for t in trades:
            k = str(t.get(key, "unknown"))
            groups.setdefault(k, []).append(t)

        result: Dict[str, dict] = {}
        for k, group_trades in groups.items():
            pnls = [(t.get("pnl") or 0) for t in group_trades]
            wins = [p for p in pnls if p > 0]
            result[k] = {
                "trades": len(group_trades),
                "win_rate": round(len(wins) / len(group_trades), 4) if group_trades else 0,
                "net_pnl": round(sum(pnls), 4),
            }
        return result

    def _empty_result(self) -> dict:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "profit_factor": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "payoff_ratio": 0,
            "net_profit": 0,
            "total_return": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "calmar_ratio": 0,
            "gross_profit": 0,
            "gross_loss": 0,
            "by_strategy": {},
            "by_regime": {},
            "equity_curve": [],
        }
