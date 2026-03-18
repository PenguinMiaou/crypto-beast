"""Tests for LiveExecutor with mock exchange."""
import asyncio
import pytest
from datetime import datetime
from typing import Optional

from core.database import Database
from core.models import (
    Direction,
    ExecutionPlan,
    MarketRegime,
    OrderType,
    Position,
    TradeSignal,
    ValidatedOrder,
)
from core.rate_limiter import BinanceRateLimiter
from execution.executor import LiveExecutor


class MockExchange:
    """Mock ccxt exchange for testing (supports direct fapi calls for hedge mode)."""

    def __init__(self, fail_count: int = 0):
        self._fail_count = fail_count
        self._attempt = 0
        self.leverage_calls = []
        self.order_calls = []
        self.cancel_called = False

    async def set_leverage(self, leverage: int, symbol: str) -> None:
        self.leverage_calls.append((leverage, symbol))

    async def fapiPrivatePostOrder(self, params: dict) -> dict:
        """Direct Binance fapi order (hedge mode compatible)."""
        self._attempt += 1
        if self._attempt <= self._fail_count:
            raise Exception(f"Mock failure {self._attempt}")
        qty = float(params.get("quantity", 0))
        self.order_calls.append((params.get("type", "MARKET"), params.get("symbol"),
                                  params.get("side"), qty))
        return {
            "orderId": f"mock-{self._attempt}",
            "avgPrice": "65000",
            "executedQty": str(qty),
            "status": "FILLED",
        }

    async def fapiPrivateV2GetAccount(self) -> dict:
        return {
            "totalWalletBalance": "1000",
            "totalUnrealizedProfit": "1.5",
            "availableBalance": "900",
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.01",
                    "entryPrice": "65000",
                    "leverage": "5",
                    "unrealizedProfit": "1.5",
                    "notional": "650",
                    "markPrice": "65150",
                },
                {
                    "symbol": "ETHUSDT",
                    "positionAmt": "0",
                    "entryPrice": "0",
                    "leverage": "1",
                    "unrealizedProfit": "0",
                    "notional": "0",
                },
            ],
        }

    async def fetch_positions(self) -> list:
        return [
            {
                "symbol": "BTCUSDT",
                "side": "long",
                "contracts": 0.01,
                "entryPrice": 65000,
                "leverage": 5,
                "unrealizedPnl": 1.5,
            }
        ]

    async def cancel_all_orders(self, symbol: str = None) -> None:
        self.cancel_called = True


@pytest.fixture
def db(tmp_path) -> Database:
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db


@pytest.fixture
def rate_limiter() -> BinanceRateLimiter:
    return BinanceRateLimiter()


@pytest.fixture
def signal() -> TradeSignal:
    return TradeSignal(
        symbol="BTCUSDT",
        direction=Direction.LONG,
        confidence=0.85,
        entry_price=65000.0,
        stop_loss=63700.0,
        take_profit=68000.0,
        strategy="trend_follow",
        regime=MarketRegime.TRENDING_UP,
        timeframe_score=7,
        timestamp=datetime.utcnow(),
    )


@pytest.fixture
def order(signal: TradeSignal) -> ValidatedOrder:
    return ValidatedOrder(
        signal=signal,
        quantity=0.01,
        leverage=5,
        order_type=OrderType.MARKET,
        risk_amount=13.0,
        max_slippage=0.001,
    )


@pytest.fixture
def plan(order: ValidatedOrder) -> ExecutionPlan:
    return ExecutionPlan(
        order=order,
        entry_tranches=[
            {"price": 65000.0, "quantity": 0.01, "type": "MARKET"},
        ],
        exit_tranches=[
            {"price": 66500.0, "quantity": 0.004, "trigger": "TP_50"},
            {"price": 67250.0, "quantity": 0.003, "trigger": "TP_75"},
            {"price": 68000.0, "quantity": 0.003, "trigger": "TP_100"},
        ],
        trailing_stop=None,
        time_limit_hours=4.0,
    )


class TestExecute:
    """Test LiveExecutor.execute() places orders and records to DB."""

    @pytest.mark.asyncio
    async def test_execute_success(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        result = await executor.execute(plan)

        assert result.success is True
        assert len(result.order_ids) >= 1  # Entry + TP/SL exit orders
        assert "mock-" in result.order_ids[0]
        assert result.total_filled == 0.01
        assert result.avg_fill_price == 65000
        assert result.fees_paid > 0

    @pytest.mark.asyncio
    async def test_execute_records_to_db(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        await executor.execute(plan)

        rows = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "BTCUSDT"  # symbol
        assert rows[0][2] == "LONG"  # side

    @pytest.mark.asyncio
    async def test_execute_sets_leverage(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        await executor.execute(plan)

        assert exchange.leverage_calls == [(5, "BTC/USDT")]

    @pytest.mark.asyncio
    async def test_execute_leverage_failure(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange()

        async def fail_leverage(leverage, symbol):
            raise Exception("leverage error")

        exchange.set_leverage = fail_leverage
        executor = LiveExecutor(exchange, db, rate_limiter)
        result = await executor.execute(plan)

        assert result.success is False
        assert "leverage error" in result.error


class TestGetPositions:
    """Test LiveExecutor.get_positions() returns parsed positions."""

    @pytest.mark.asyncio
    async def test_get_positions(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        positions = await executor.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "BTCUSDT"
        assert pos.direction == Direction.LONG
        assert pos.entry_price == 65000.0
        assert pos.quantity == 0.01
        assert pos.leverage == 5
        assert pos.unrealized_pnl == 1.5

    @pytest.mark.asyncio
    async def test_get_positions_error(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()

        async def fail_fetch():
            raise Exception("connection error")

        exchange.fapiPrivateV2GetAccount = fail_fetch
        executor = LiveExecutor(exchange, db, rate_limiter)
        positions = await executor.get_positions()
        assert positions == []


class TestClosePosition:
    """Test LiveExecutor.close_position() creates opposite order."""

    @pytest.mark.asyncio
    async def test_close_long_position(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        position = Position(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            entry_price=65000.0,
            quantity=0.01,
            leverage=5,
            unrealized_pnl=1.5,
            strategy="trend_follow",
            entry_time=datetime.utcnow(),
            current_stop=63700.0,
        )

        result = await executor.close_position(position)
        assert result.success is True
        assert result.total_filled == 0.01
        # Should sell to close long
        assert exchange.order_calls[0][2].upper() == "SELL"

    @pytest.mark.asyncio
    async def test_close_short_position(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        position = Position(
            symbol="ETHUSDT",
            direction=Direction.SHORT,
            entry_price=3500.0,
            quantity=1.0,
            leverage=3,
            unrealized_pnl=-5.0,
            strategy="mean_revert",
            entry_time=datetime.utcnow(),
            current_stop=3600.0,
        )

        result = await executor.close_position(position)
        assert result.success is True
        # Should buy to close short
        assert exchange.order_calls[0][2].upper() == "BUY"

    @pytest.mark.asyncio
    async def test_close_position_error(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()

        async def fail_order(*args, **kwargs):
            raise Exception("order failed")

        exchange.fapiPrivatePostOrder = fail_order
        executor = LiveExecutor(exchange, db, rate_limiter)
        position = Position(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            entry_price=65000.0,
            quantity=0.01,
            leverage=5,
            unrealized_pnl=0,
            strategy="test",
            entry_time=datetime.utcnow(),
            current_stop=0.0,
        )

        result = await executor.close_position(position)
        assert result.success is False
        assert result.error is not None


class TestCancelAllPending:
    """Test LiveExecutor.cancel_all_pending() calls exchange."""

    @pytest.mark.asyncio
    async def test_cancel_all(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()
        executor = LiveExecutor(exchange, db, rate_limiter)
        await executor.cancel_all_pending()
        assert exchange.cancel_called is True

    @pytest.mark.asyncio
    async def test_cancel_error_handled(
        self, db: Database, rate_limiter: BinanceRateLimiter
    ):
        exchange = MockExchange()

        async def fail_cancel():
            raise Exception("cancel error")

        exchange.cancel_all_orders = fail_cancel
        executor = LiveExecutor(exchange, db, rate_limiter)
        # Should not raise
        await executor.cancel_all_pending()


class TestRetryLogic:
    """Test retry logic on order failure."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange(fail_count=2)
        executor = LiveExecutor(exchange, db, rate_limiter)
        result = await executor.execute(plan)

        assert result.success is True
        assert len(result.order_ids) >= 1  # Entry + TP/SL exit orders

    @pytest.mark.asyncio
    async def test_retry_exhausted(
        self, db: Database, rate_limiter: BinanceRateLimiter, plan: ExecutionPlan
    ):
        exchange = MockExchange(fail_count=5)
        executor = LiveExecutor(exchange, db, rate_limiter)
        result = await executor.execute(plan)

        assert result.success is False
        assert result.error is not None
