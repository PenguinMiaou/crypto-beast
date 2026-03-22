# tests/integration/test_paper_trading.py
"""End-to-end paper trading test."""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from config import Config
from core.database import Database
from analysis.market_regime import MarketRegimeDetector
from analysis.multi_timeframe import MultiTimeframe
from analysis.session_trader import SessionTrader
from strategy.strategy_engine import StrategyEngine
from defense.risk_manager import RiskManager
from defense.anti_trap import AntiTrap
from execution.paper_executor import PaperExecutor
from core.models import Portfolio, ExecutionPlan


@pytest.fixture
def long_uptrend_data():
    """300-candle uptrend for integration testing.

    Volume increases steadily to avoid triggering AntiTrap volume
    divergence detection.  The body/wick ratio is kept moderate to
    avoid pin-bar detection.
    """
    np.random.seed(77)
    n = 300
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000.0 + np.arange(n) * 30.0
    # Keep wicks small relative to body to avoid pin-bar trap detection
    high = close + 20
    low = close - 20
    open_ = close - 15
    # Steadily increasing volume avoids volume-divergence trap
    volume = 500.0 + np.arange(n) * 2.0
    return pd.DataFrame({
        "open_time": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


class TestPaperTrading:
    def test_strategy_engine_generates_signals(self, long_uptrend_data):
        """StrategyEngine with all dependencies produces signals."""
        regime_detector = MarketRegimeDetector()
        session_trader = SessionTrader()
        multi_timeframe = MultiTimeframe()

        engine = StrategyEngine(regime_detector, session_trader, multi_timeframe)
        signals = engine.generate_signals("BTCUSDT", long_uptrend_data)

        assert isinstance(signals, list)
        # Strong uptrend should produce at least one signal
        assert len(signals) > 0

    @pytest.mark.asyncio
    async def test_multi_module_integration(self, long_uptrend_data, db):
        """Test multiple modules working together.

        StrategyEngine applies strategy weights (0.2) and session weights,
        which reduce raw confidence. We boost weights to simulate a scenario
        where the evolver has learned to trust the trend_follower strategy.
        """
        config = Config()
        # Lower fee so the TP-distance check doesn't filter this integration test's synthetic
        # signal (min_profit_pct = taker_fee * 2 * 3). The fee formula fix (Bug 3) is tested
        # in unit tests; here we just need a valid end-to-end signal to reach execution.
        config.taker_fee = 0.0001
        regime_detector = MarketRegimeDetector()
        session_trader = SessionTrader()
        multi_timeframe = MultiTimeframe()

        engine = StrategyEngine(regime_detector, session_trader, multi_timeframe)
        # Boost trend_follower weight so its signals survive risk validation
        engine.update_weights({
            "trend_follower": 1.0,
            "mean_reversion": 0.2,
            "momentum": 1.0,
            "breakout": 1.0,
            "scalper": 0.2,
        })
        rm = RiskManager(config)
        anti_trap = AntiTrap()

        price = float(long_uptrend_data.iloc[-1]["close"])
        executor = PaperExecutor(db=db, current_price_fn=lambda s: price)

        portfolio = Portfolio(
            equity=100.0, available_balance=100.0, positions=[],
            peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
            total_fees_today=0.0, drawdown_pct=0.0)

        signals = engine.generate_signals("BTCUSDT", long_uptrend_data)
        assert len(signals) > 0, "Engine should produce signals on strong uptrend"

        executed = 0

        for signal in signals:
            # AntiTrap filter
            if anti_trap.is_trap(signal, long_uptrend_data):
                continue

            # Risk validation
            order = rm.validate(signal, portfolio)
            if order is None:
                continue

            # Execute
            plan = ExecutionPlan(
                order=order,
                entry_tranches=[{"price": price, "quantity": order.quantity, "type": "MARKET"}],
                exit_tranches=[])
            result = await executor.execute(plan)
            if result.success:
                executed += 1

        # Should have executed at least one trade
        assert executed >= 1

        # Verify in DB
        trades = db.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()
        assert trades[0] >= 1
