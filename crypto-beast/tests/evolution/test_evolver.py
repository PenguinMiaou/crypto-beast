import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from evolution.evolver import Evolver
from core.models import EvolutionReport
from core.database import Database
from config import Config


@pytest.fixture
def mock_db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db


@pytest.fixture
def evolver(mock_db):
    config = {"param_a": 1.0, "param_b": 2.0}
    return Evolver(config=config, db=mock_db)


class TestBuildSearchSpace:
    def test_bounds_20_percent(self, evolver):
        """param=9, 20% change -> bounds (7.2, 10.8)"""
        space = evolver.build_search_space({"x": 9.0}, max_change=0.2)
        low, high = space["x"]
        assert abs(low - 7.2) < 1e-9
        assert abs(high - 10.8) < 1e-9

    def test_zero_param_gets_default_delta(self, evolver):
        space = evolver.build_search_space({"x": 0.0}, max_change=0.2)
        low, high = space["x"]
        assert low == pytest.approx(-0.1)
        assert high == pytest.approx(0.1)


class TestCalculateStrategyWeights:
    def test_higher_sharpe_gets_higher_weight(self, evolver):
        """Strategy with Sharpe 0.6 gets higher weight than Sharpe 0.2."""
        perf = {"strat_a": 0.6, "strat_b": 0.2}
        weights = evolver.calculate_strategy_weights(perf)
        assert weights["strat_a"] > weights["strat_b"]

    def test_empty_performance_returns_defaults(self, evolver):
        weights = evolver.calculate_strategy_weights({})
        assert weights == evolver.get_strategy_weights()


class TestAtomicSwap:
    def test_set_and_apply_pending(self, evolver):
        """set_pending_config + apply_if_pending -> config swapped."""
        new_config = {"param_a": 99.0}
        evolver.set_pending_config(new_config)
        result = evolver.apply_if_pending()
        assert result is True
        assert evolver.get_active_config() == new_config

    def test_no_pending_returns_false(self, evolver):
        """No pending -> apply_if_pending returns False."""
        result = evolver.apply_if_pending()
        assert result is False


class TestLogEvolution:
    def test_writes_to_db(self, evolver, mock_db):
        """log_evolution writes to DB."""
        report = EvolutionReport(
            timestamp=datetime(2026, 1, 1),
            parameters_changed={"lr": {"old": 0.01, "new": 0.02}},
            backtest_sharpe_before=1.0,
            backtest_sharpe_after=1.5,
            strategy_weights={"momentum": 0.5},
            recommendations_applied=["widen stops"],
        )
        evolver.log_evolution(report)

        rows = mock_db.execute("SELECT * FROM evolution_log").fetchall()
        assert len(rows) == 1
        assert rows[0][4] == 1.5  # backtest_sharpe column


class TestRunDailyEvolution:
    @pytest.mark.asyncio
    async def test_run_daily_evolution(self, mock_db):
        """run_daily_evolution optimizes params and returns a report."""
        config = Config()
        evolver = Evolver(config, mock_db)

        # Create sample data
        n = 300
        dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
        close = 65000 + np.arange(n) * 30.0
        data = {"BTCUSDT": pd.DataFrame({
            "open_time": dates,
            "open": close - 10,
            "high": close + 50,
            "low": close - 50,
            "close": close,
            "volume": np.random.uniform(500, 1500, n),
        })}

        report = await evolver.run_daily_evolution(data=data)
        assert report is not None
        assert report.strategy_weights is not None
        assert len(report.parameters_changed) > 0

    @pytest.mark.asyncio
    async def test_run_daily_evolution_no_data(self, mock_db):
        """run_daily_evolution with no data returns None."""
        config = Config()
        evolver = Evolver(config, mock_db)
        report = await evolver.run_daily_evolution(data=None)
        assert report is None
