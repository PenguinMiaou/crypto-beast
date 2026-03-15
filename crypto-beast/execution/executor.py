"""Live Binance Futures executor using ccxt."""
import asyncio
from datetime import datetime
from typing import List, Optional, Dict
from uuid import uuid4

from loguru import logger

from core.database import Database
from core.models import (
    Direction,
    ExecutionPlan,
    ExecutionResult,
    OrderType,
    Position,
)
from core.rate_limiter import BinanceRateLimiter


class LiveExecutor:
    """Execute trades on Binance Futures via ccxt."""

    TAKER_FEE = 0.0004
    MAKER_FEE = 0.0002
    MAX_RETRIES = 3

    def __init__(
        self, exchange: object, db: Database, rate_limiter: BinanceRateLimiter
    ):
        self.exchange = exchange
        self.db = db
        self.rate_limiter = rate_limiter

    @staticmethod
    def _to_ccxt_symbol(symbol: str) -> str:
        """Convert 'BTCUSDT' to 'BTC/USDT' for ccxt."""
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            return symbol[:-4] + "/USDT"
        return symbol

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute a trade plan on Binance."""
        signal = plan.order.signal
        ccxt_symbol = self._to_ccxt_symbol(signal.symbol)
        order_ids: List[str] = []
        total_filled = 0.0
        total_cost = 0.0
        total_fees = 0.0

        # Set leverage
        try:
            await self.rate_limiter.acquire_order_slot()
            await self.exchange.set_leverage(plan.order.leverage, ccxt_symbol)
        except Exception as e:
            logger.error(f"Failed to set leverage: {e}")
            return ExecutionResult(
                success=False,
                order_ids=[],
                avg_fill_price=0,
                total_filled=0,
                fees_paid=0,
                slippage=0,
                error=str(e),
            )

        # Execute entry tranches
        for tranche in plan.entry_tranches:
            for attempt in range(self.MAX_RETRIES):
                try:
                    await self.rate_limiter.acquire_order_slot()

                    side = "buy" if signal.direction == Direction.LONG else "sell"
                    order_type = tranche.get("type", "MARKET").lower()

                    params: Dict = {}
                    if order_type == "limit":
                        order = await self.exchange.create_limit_order(
                            ccxt_symbol,
                            side,
                            tranche["quantity"],
                            tranche["price"],
                            params,
                        )
                    else:
                        order = await self.exchange.create_market_order(
                            ccxt_symbol, side, tranche["quantity"], params
                        )

                    fill_price = order.get(
                        "average", order.get("price", tranche["price"])
                    )
                    filled = order.get("filled", tranche["quantity"])
                    fee_cost = order.get("fee", {}).get(
                        "cost", filled * fill_price * self.TAKER_FEE
                    )

                    order_ids.append(order.get("id", f"LIVE-{uuid4().hex[:12]}"))
                    total_filled += filled
                    total_cost += filled * fill_price
                    total_fees += fee_cost
                    break

                except Exception as e:
                    logger.warning(f"Order attempt {attempt + 1} failed: {e}")
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(2**attempt)  # Exponential backoff
                    else:
                        return ExecutionResult(
                            success=False,
                            order_ids=order_ids,
                            avg_fill_price=0,
                            total_filled=total_filled,
                            fees_paid=total_fees,
                            slippage=0,
                            error=str(e),
                        )

        avg_price = total_cost / total_filled if total_filled > 0 else 0
        slippage = (
            abs(avg_price - signal.entry_price) / signal.entry_price
            if signal.entry_price > 0
            else 0
        )

        # Record to DB
        self.db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage,
               strategy, entry_time, fees, status, stop_loss, take_profit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.symbol,
                signal.direction.value,
                round(avg_price, 2),
                round(total_filled, 8),
                plan.order.leverage,
                signal.strategy,
                datetime.utcnow().isoformat(),
                round(total_fees, 6),
                "OPEN",
                signal.stop_loss,
                signal.take_profit,
            ),
        )

        return ExecutionResult(
            success=True,
            order_ids=order_ids,
            avg_fill_price=round(avg_price, 2),
            total_filled=round(total_filled, 8),
            fees_paid=round(total_fees, 6),
            slippage=round(slippage, 6),
        )

    async def get_positions(self) -> List[Position]:
        """Fetch open positions from exchange."""
        try:
            await self.rate_limiter.acquire_data_slot()
            positions = await self.exchange.fetch_positions()  # Returns all futures positions
            result: List[Position] = []
            for pos in positions:
                if float(pos.get("contracts", 0)) > 0:
                    result.append(
                        Position(
                            symbol=pos["symbol"],
                            direction=(
                                Direction.LONG
                                if pos["side"] == "long"
                                else Direction.SHORT
                            ),
                            entry_price=float(pos.get("entryPrice", 0)),
                            quantity=float(pos.get("contracts", 0)),
                            leverage=int(pos.get("leverage", 1)),
                            unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                            strategy="unknown",
                            entry_time=datetime.utcnow(),
                            current_stop=0.0,
                        )
                    )
            return result
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def close_position(
        self,
        position: Position,
        order_type: OrderType = OrderType.MARKET,
    ) -> ExecutionResult:
        """Close a position."""
        try:
            await self.rate_limiter.acquire_order_slot()
            ccxt_sym = self._to_ccxt_symbol(position.symbol)
            side = "sell" if position.direction == Direction.LONG else "buy"
            order = await self.exchange.create_market_order(
                ccxt_sym, side, position.quantity
            )

            fill_price = order.get("average", order.get("price", 0))
            fees = position.quantity * fill_price * self.TAKER_FEE

            return ExecutionResult(
                success=True,
                order_ids=[order.get("id", "")],
                avg_fill_price=fill_price,
                total_filled=position.quantity,
                fees_paid=round(fees, 6),
                slippage=0,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                order_ids=[],
                avg_fill_price=0,
                total_filled=0,
                fees_paid=0,
                slippage=0,
                error=str(e),
            )

    async def cancel_all_pending(self) -> None:
        """Cancel all open orders."""
        try:
            await self.rate_limiter.acquire_order_slot()
            await self.exchange.cancel_all_orders()
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
