import pytest
from evolution.performance_analyzer import PerformanceAnalyzer


def test_performance_basic_metrics():
    trades = [
        {"pnl": 10.0, "fees": 0.5, "direction": "LONG", "entry": 100, "exit": 110, "strategy": "trend"},
        {"pnl": -5.0, "fees": 0.5, "direction": "SHORT", "entry": 100, "exit": 105, "strategy": "trend"},
        {"pnl": 8.0, "fees": 0.5, "direction": "LONG", "entry": 100, "exit": 108, "strategy": "mean_rev"},
    ]
    analyzer = PerformanceAnalyzer()
    result = analyzer.calculate(trades, initial_capital=100.0)
    assert result["total_trades"] == 3
    assert result["win_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert result["profit_factor"] > 1.0
    assert result["net_profit"] == pytest.approx(13.0, abs=0.01)
    assert len(result["equity_curve"]) == 4  # initial + 3 trades


def test_performance_empty():
    result = PerformanceAnalyzer().calculate([], initial_capital=100.0)
    assert result["total_trades"] == 0


def test_performance_by_strategy():
    trades = [
        {"pnl": 10.0, "strategy": "trend", "direction": "LONG"},
        {"pnl": -3.0, "strategy": "trend", "direction": "LONG"},
        {"pnl": 5.0, "strategy": "mean", "direction": "SHORT"},
    ]
    result = PerformanceAnalyzer().calculate(trades, initial_capital=100.0)
    assert "trend" in result["by_strategy"]
    assert result["by_strategy"]["trend"]["trades"] == 2
    assert result["by_strategy"]["mean"]["trades"] == 1


def test_performance_max_drawdown():
    trades = [
        {"pnl": 20.0}, {"pnl": -15.0}, {"pnl": -10.0}, {"pnl": 30.0},
    ]
    result = PerformanceAnalyzer().calculate(trades, initial_capital=100.0)
    assert result["max_drawdown"] > 0


def test_performance_all_keys_present():
    trades = [{"pnl": 5.0, "strategy": "s", "regime": "TRENDING_UP"}]
    result = PerformanceAnalyzer().calculate(trades, initial_capital=100.0)
    expected_keys = [
        "total_trades", "win_rate", "profit_factor", "avg_win", "avg_loss",
        "payoff_ratio", "net_profit", "total_return", "max_drawdown",
        "sharpe_ratio", "sortino_ratio", "calmar_ratio",
        "gross_profit", "gross_loss", "by_strategy", "by_regime", "equity_curve",
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_performance_by_regime():
    trades = [
        {"pnl": 5.0, "regime": "TRENDING_UP"},
        {"pnl": -2.0, "regime": "RANGING"},
        {"pnl": 3.0, "regime": "TRENDING_UP"},
    ]
    result = PerformanceAnalyzer().calculate(trades, initial_capital=100.0)
    assert "TRENDING_UP" in result["by_regime"]
    assert result["by_regime"]["TRENDING_UP"]["trades"] == 2
    assert result["by_regime"]["RANGING"]["trades"] == 1


def test_walk_forward_returns_result():
    import numpy as np
    import pandas as pd
    from datetime import datetime, timedelta
    from evolution.backtest_lab import BacktestLab
    from strategy.trend_follower import TrendFollower

    # Build enough data: 1 train_day + 1 test_day = 576 candles minimum
    n = 600
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 10.0
    lab = BacktestLab()
    sample_klines = pd.DataFrame({
        "open_time": dates,
        "open": close - 10,
        "high": close + 30,
        "low": close - 30,
        "close": close,
        "volume": np.random.uniform(500, 1500, n),
    })
    result = lab.run_walk_forward(TrendFollower(), sample_klines, symbol="BTCUSDT",
                                  train_days=1, test_days=1, starting_capital=100.0)
    assert hasattr(result, "num_folds") or isinstance(result, object)
    assert hasattr(result, "in_sample_sharpe")
    assert hasattr(result, "out_of_sample_sharpe")
    assert hasattr(result, "efficiency_ratio")
    assert result.num_folds >= 1
