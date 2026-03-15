# evolution/backtest_lab.py
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from core.models import (BacktestResult, WalkForwardResult, MonteCarloResult,
                          MarketRegime, Direction)


class BacktestLab:
    def __init__(self, slippage: float = 0.0005, taker_fee: float = 0.0004):
        self.slippage = slippage
        self.taker_fee = taker_fee

    def run_backtest(
        self, strategy, data: pd.DataFrame, symbol: str = "BTCUSDT",
        starting_capital: float = 100.0, regime: MarketRegime = MarketRegime.RANGING
    ) -> BacktestResult:
        """Run a backtest of a strategy on historical data."""
        equity = starting_capital
        peak = equity
        max_dd = 0.0
        trades: List[dict] = []
        position: Optional[dict] = None  # {direction, entry_price, quantity, stop_loss, take_profit}

        lookback = 50  # Minimum candles needed
        if len(data) < lookback:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, [])

        for i in range(lookback, len(data)):
            bar = data.iloc[i]

            # Check open position exits
            if position is not None:
                # Check stop loss / take profit hit
                if position["direction"] == Direction.LONG:
                    if bar["low"] <= position["stop_loss"]:
                        # Stop hit
                        exit_price = position["stop_loss"] * (1 - self.slippage)
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]
                        fees = exit_price * position["quantity"] * self.taker_fee
                        trades.append({"entry": position["entry_price"], "exit": exit_price,
                            "pnl": pnl - fees, "fees": fees, "direction": "LONG"})
                        equity += pnl - fees
                        position = None
                    elif bar["high"] >= position["take_profit"]:
                        exit_price = position["take_profit"] * (1 + self.slippage)
                        pnl = (exit_price - position["entry_price"]) * position["quantity"]
                        fees = exit_price * position["quantity"] * self.taker_fee
                        trades.append({"entry": position["entry_price"], "exit": exit_price,
                            "pnl": pnl - fees, "fees": fees, "direction": "LONG"})
                        equity += pnl - fees
                        position = None
                else:  # SHORT
                    if bar["high"] >= position["stop_loss"]:
                        exit_price = position["stop_loss"] * (1 + self.slippage)
                        pnl = (position["entry_price"] - exit_price) * position["quantity"]
                        fees = exit_price * position["quantity"] * self.taker_fee
                        trades.append({"entry": position["entry_price"], "exit": exit_price,
                            "pnl": pnl - fees, "fees": fees, "direction": "SHORT"})
                        equity += pnl - fees
                        position = None
                    elif bar["low"] <= position["take_profit"]:
                        exit_price = position["take_profit"] * (1 - self.slippage)
                        pnl = (position["entry_price"] - exit_price) * position["quantity"]
                        fees = exit_price * position["quantity"] * self.taker_fee
                        trades.append({"entry": position["entry_price"], "exit": exit_price,
                            "pnl": pnl - fees, "fees": fees, "direction": "SHORT"})
                        equity += pnl - fees
                        position = None

            # Generate new signals if no position
            if position is None:
                window = data.iloc[:i + 1]
                signals = strategy.generate(window, symbol, regime)
                if signals:
                    sig = signals[0]  # Take best signal
                    # Calculate position size (2% risk)
                    risk_per_trade = equity * 0.02
                    risk_distance = abs(sig.entry_price - sig.stop_loss)
                    if risk_distance > 0:
                        quantity = risk_per_trade / risk_distance
                        if sig.direction == Direction.LONG:
                            entry_price = sig.entry_price * (1 + self.slippage)
                        else:
                            entry_price = sig.entry_price * (1 - self.slippage)
                        entry_fee = entry_price * quantity * self.taker_fee
                        equity -= entry_fee
                        position = {
                            "direction": sig.direction,
                            "entry_price": entry_price,
                            "quantity": quantity,
                            "stop_loss": sig.stop_loss,
                            "take_profit": sig.take_profit,
                        }

            # Track drawdown
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Close any remaining position at last price
        if position is not None:
            last_price = data.iloc[-1]["close"]
            if position["direction"] == Direction.LONG:
                pnl = (last_price - position["entry_price"]) * position["quantity"]
            else:
                pnl = (position["entry_price"] - last_price) * position["quantity"]
            fees = last_price * position["quantity"] * self.taker_fee
            trades.append({"entry": position["entry_price"], "exit": last_price,
                "pnl": pnl - fees, "fees": fees, "direction": str(position["direction"])})
            equity += pnl - fees

        # Calculate metrics
        if not trades:
            return BacktestResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, [])

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_return = (equity - starting_capital) / starting_capital
        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Sharpe (annualized from trade returns)
        if len(pnls) > 1:
            ret_arr = np.array(pnls) / starting_capital
            sharpe = float(np.mean(ret_arr) / np.std(ret_arr) * np.sqrt(252)) if np.std(ret_arr) > 0 else 0.0
            neg_rets = ret_arr[ret_arr < 0]
            sortino = float(np.mean(ret_arr) / np.std(neg_rets) * np.sqrt(252)) if len(neg_rets) > 0 and np.std(neg_rets) > 0 else 0.0
        else:
            sharpe = 0.0
            sortino = 0.0

        return BacktestResult(
            total_return=round(total_return, 4),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown=round(max_dd, 4),
            win_rate=round(win_rate, 4),
            avg_win=round(avg_win, 4),
            avg_loss=round(avg_loss, 4),
            profit_factor=round(profit_factor, 4),
            total_trades=len(trades),
            trades=trades,
        )

    def run_walk_forward(self, strategy, data: pd.DataFrame, symbol: str = "BTCUSDT",
                         train_days: int = 30, test_days: int = 7,
                         starting_capital: float = 100.0) -> WalkForwardResult:
        """Run walk-forward analysis: train on window, test on next window."""
        # Each day ~ 288 five-minute candles
        candles_per_day = 288
        train_size = train_days * candles_per_day
        test_size = test_days * candles_per_day

        if len(data) < train_size + test_size:
            return WalkForwardResult(
                in_sample_sharpe=0.0, out_of_sample_sharpe=0.0,
                best_params={}, is_valid=False)

        # Split data
        train_data = data.iloc[:train_size]
        test_data = data.iloc[train_size:train_size + test_size]

        # Run in-sample backtest
        is_result = self.run_backtest(strategy, train_data, symbol, starting_capital)

        # Run out-of-sample backtest
        oos_result = self.run_backtest(strategy, test_data, symbol, starting_capital)

        return WalkForwardResult(
            in_sample_sharpe=is_result.sharpe_ratio,
            out_of_sample_sharpe=oos_result.sharpe_ratio,
            best_params={},  # Params from the strategy used
            is_valid=oos_result.sharpe_ratio > 0,
        )

    def run_monte_carlo(self, trades: List[dict], starting_capital: float = 100.0,
                         iterations: int = 1000, max_drawdown_limit: float = 0.3) -> MonteCarloResult:
        """Shuffle trade order and recalculate equity curves."""
        if not trades:
            return MonteCarloResult(0, 0, 1.0, 0)

        pnls = [t["pnl"] for t in trades]
        final_returns: List[float] = []
        max_drawdowns: List[float] = []
        ruin_count = 0

        for _ in range(iterations):
            shuffled = np.random.permutation(pnls)
            equity = starting_capital
            peak = equity
            max_dd = 0.0

            for pnl in shuffled:
                equity += pnl
                peak = max(peak, equity)
                dd = (peak - equity) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

            final_returns.append((equity - starting_capital) / starting_capital)
            max_drawdowns.append(max_dd)
            if max_dd >= max_drawdown_limit:
                ruin_count += 1

        return MonteCarloResult(
            median_return=round(float(np.median(final_returns)), 4),
            worst_case_drawdown=round(float(np.percentile(max_drawdowns, 95)), 4),
            probability_of_ruin=round(ruin_count / iterations, 4),
            confidence_95_return=round(float(np.percentile(final_returns, 5)), 4),
        )
