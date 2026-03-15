# tests/execution/test_paper_executor.py
import pytest
import pytest_asyncio

from core.models import (
    Direction,
    ExecutionPlan,
    MarketRegime,
    OrderType,
    TradeSignal,
    ValidatedOrder,
)


@pytest.fixture
def sample_plan():
    signal = TradeSignal(
        symbol="BTCUSDT", direction=Direction.LONG, confidence=0.85,
        entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
        strategy="trend_follower", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
    )
    order = ValidatedOrder(
        signal=signal, quantity=0.001, leverage=10,
        order_type=OrderType.MARKET, risk_amount=1.0, max_slippage=0.001,
    )
    return ExecutionPlan(
        order=order,
        entry_tranches=[{"price": 65000.0, "quantity": 0.001, "type": "MARKET"}],
        exit_tranches=[{"price": 67000.0, "quantity": 0.001, "trigger": "TP"}],
    )


class TestPaperExecutor:
    @pytest.mark.asyncio
    async def test_execute_returns_success(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_generates_paper_order_id(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.order_ids[0].startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_execute_records_trade_in_db(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        await executor.execute(sample_plan)
        trades = db.execute("SELECT * FROM trades").fetchall()
        assert len(trades) == 1

    @pytest.mark.asyncio
    async def test_execute_calculates_fees(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.fees_paid > 0

    @pytest.mark.asyncio
    async def test_get_positions(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65100.0)
        await executor.execute(sample_plan)
        positions = await executor.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTCUSDT"
