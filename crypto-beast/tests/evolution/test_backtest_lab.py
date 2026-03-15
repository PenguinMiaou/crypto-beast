# tests/evolution/test_backtest_lab.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from typing import List

from core.models import (
    BacktestResult, MonteCarloResult, MarketRegime,
    Direction, TradeSignal,
)
from evolution.backtest_lab import BacktestLab
from strategy.trend_follower import TrendFollower


@pytest.fixture
def lab():
    return BacktestLab(slippage=0.0005, taker_fee=0.0004)


@pytest.fixture
def uptrend_data():
    n = 300
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 30.0
    high = close + 50
    low = close - 50
    open_ = close - 15
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({
        "open_time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def empty_data():
    return pd.DataFrame({
        "open_time": [],
        "open": [],
        "high": [],
        "low": [],
        "close": [],
        "volume": [],
    })


@pytest.fixture
def short_data():
    """Data shorter than lookback period."""
    n = 20
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 30.0
    return pd.DataFrame({
        "open_time": dates,
        "open": close - 15,
        "high": close + 50,
        "low": close - 50,
        "close": close,
        "volume": np.random.uniform(500, 1500, n),
    })


class TestRunBacktest:
    """Tests for BacktestLab.run_backtest."""

    def test_uptrend_produces_trades_with_fees(self, lab, uptrend_data):
        """run_backtest on TrendFollower with uptrend data produces trades with fees deducted."""
        strategy = TrendFollower()
        result = lab.run_backtest(
            strategy, uptrend_data, symbol="BTCUSDT",
            starting_capital=100.0, regime=MarketRegime.RANGING,
        )
        assert isinstance(result, BacktestResult)
        assert result.total_trades > 0, "Should produce at least one trade on uptrend data"

        # Every trade must have fees > 0
        for trade in result.trades:
            assert trade["fees"] > 0, "Each trade should have fees deducted"
            assert "pnl" in trade
            assert "entry" in trade
            assert "exit" in trade

    def test_metrics_calculated_correctly(self, lab, uptrend_data):
        """BacktestResult metrics: win_rate, profit_factor calculated correctly."""
        strategy = TrendFollower()
        result = lab.run_backtest(
            strategy, uptrend_data, symbol="BTCUSDT",
            starting_capital=100.0, regime=MarketRegime.RANGING,
        )
        if result.total_trades == 0:
            pytest.skip("No trades generated")

        # win_rate must be between 0 and 1
        assert 0 <= result.win_rate <= 1.0

        # Manually verify win_rate
        pnls = [t["pnl"] for t in result.trades]
        wins = [p for p in pnls if p > 0]
        expected_win_rate = round(len(wins) / len(pnls), 4)
        assert result.win_rate == expected_win_rate

        # Manually verify profit_factor
        losses = [p for p in pnls if p < 0]
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        if gross_loss > 0:
            expected_pf = round(gross_profit / gross_loss, 4)
            assert result.profit_factor == expected_pf
        else:
            assert result.profit_factor == float("inf")

        # max_drawdown should be non-negative
        assert result.max_drawdown >= 0

        # sharpe and sortino are floats
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.sortino_ratio, float)

    def test_empty_data_returns_zero_result(self, lab, empty_data):
        """Empty data returns a zero result."""
        strategy = TrendFollower()
        result = lab.run_backtest(strategy, empty_data)
        assert result.total_trades == 0
        assert result.total_return == 0
        assert result.trades == []

    def test_short_data_returns_zero_result(self, lab, short_data):
        """Data shorter than lookback returns zero result."""
        strategy = TrendFollower()
        result = lab.run_backtest(strategy, short_data)
        assert result.total_trades == 0
        assert result.total_return == 0
        assert result.trades == []


class TestRunWalkForward:
    """Tests for BacktestLab.run_walk_forward."""

    def test_walk_forward(self, lab, uptrend_data):
        """Walk-forward returns valid result with expected attributes."""
        strategy = TrendFollower()
        # Use small windows (1 day each = 288 candles, need 576 total but data is 300)
        # So this should return is_valid=False due to insufficient data
        result = lab.run_walk_forward(strategy, uptrend_data, train_days=1, test_days=1)
        assert hasattr(result, 'in_sample_sharpe')
        assert hasattr(result, 'out_of_sample_sharpe')
        assert isinstance(result.is_valid, bool)

    def test_walk_forward_insufficient_data(self, lab, short_data):
        """Insufficient data returns invalid result."""
        from core.models import WalkForwardResult
        strategy = TrendFollower()
        result = lab.run_walk_forward(strategy, short_data, train_days=30, test_days=7)
        assert isinstance(result, WalkForwardResult)
        assert result.is_valid is False
        assert result.in_sample_sharpe == 0.0


class TestRunMonteCarlo:
    """Tests for BacktestLab.run_monte_carlo."""

    def test_monte_carlo_basic(self, lab):
        """worst_case_drawdown >= 0, probability_of_ruin between 0-1."""
        sample_trades = [
            {"pnl": 5.0, "fees": 0.1},
            {"pnl": -3.0, "fees": 0.1},
            {"pnl": 8.0, "fees": 0.1},
            {"pnl": -2.0, "fees": 0.1},
            {"pnl": 4.0, "fees": 0.1},
            {"pnl": -1.0, "fees": 0.1},
            {"pnl": 6.0, "fees": 0.1},
            {"pnl": -4.0, "fees": 0.1},
            {"pnl": 3.0, "fees": 0.1},
            {"pnl": -2.5, "fees": 0.1},
        ]
        mc = lab.run_monte_carlo(sample_trades, starting_capital=100.0, iterations=500)

        assert isinstance(mc, MonteCarloResult)
        assert mc.worst_case_drawdown >= 0
        assert 0 <= mc.probability_of_ruin <= 1.0
        # median_return should be deterministic given net-positive trades
        assert isinstance(mc.median_return, float)
        assert isinstance(mc.confidence_95_return, float)

    def test_monte_carlo_empty_trades(self, lab):
        """Empty trades list returns safe defaults."""
        mc = lab.run_monte_carlo([], starting_capital=100.0)
        assert mc.median_return == 0
        assert mc.worst_case_drawdown == 0
        assert mc.probability_of_ruin == 1.0
        assert mc.confidence_95_return == 0

    def test_monte_carlo_all_wins(self, lab):
        """All winning trades should have probability_of_ruin == 0."""
        winning_trades = [{"pnl": 10.0, "fees": 0.1} for _ in range(20)]
        mc = lab.run_monte_carlo(winning_trades, starting_capital=100.0, iterations=500)
        assert mc.probability_of_ruin == 0
        assert mc.worst_case_drawdown == 0
        assert mc.median_return > 0

    def test_monte_carlo_with_backtest_trades(self, lab, uptrend_data):
        """Monte Carlo works with trades from a real backtest."""
        strategy = TrendFollower()
        bt = lab.run_backtest(
            strategy, uptrend_data, symbol="BTCUSDT",
            starting_capital=100.0, regime=MarketRegime.RANGING,
        )
        if bt.total_trades < 2:
            pytest.skip("Need at least 2 trades for meaningful MC")

        mc = lab.run_monte_carlo(bt.trades, starting_capital=100.0, iterations=200)
        assert isinstance(mc, MonteCarloResult)
        assert mc.worst_case_drawdown >= 0
        assert 0 <= mc.probability_of_ruin <= 1.0
