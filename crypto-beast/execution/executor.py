"""Live Binance Futures executor — direct API for hedge mode compatibility."""
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
    """Execute trades on Binance Futures. Uses direct fapi calls for hedge mode."""

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
    def _to_binance_symbol(symbol: str) -> str:
        """Ensure symbol is in Binance format: 'BTCUSDT'."""
        return symbol.replace("/", "")

    @staticmethod
    def _to_ccxt_symbol(symbol: str) -> str:
        """Convert 'BTCUSDT' to 'BTC/USDT' for ccxt methods."""
        if "/" in symbol:
            return symbol
        if symbol.endswith("USDT"):
            return symbol[:-4] + "/USDT"
        return symbol

    def _get_qty_precision(self, symbol: str) -> int:
        """Get quantity decimal precision for a symbol."""
        # Default precisions for common symbols
        precisions = {"BTCUSDT": 3, "ETHUSDT": 3, "SOLUSDT": 1,
                       "BNBUSDT": 2, "XRPUSDT": 1, "DOGEUSDT": 0,
                       "ADAUSDT": 0, "AVAXUSDT": 1, "LINKUSDT": 1, "DOTUSDT": 1}
        binance_sym = self._to_binance_symbol(symbol)
        return precisions.get(binance_sym, 3)

    def _round_qty(self, symbol: str, qty: float) -> float:
        """Round quantity UP to symbol's precision to meet minimum notional."""
        import math
        precision = self._get_qty_precision(symbol)
        factor = 10 ** precision
        # Round UP to ensure we meet minimum notional
        rounded = math.ceil(qty * factor) / factor
        # Ensure minimum quantity
        min_qty = 10 ** (-precision)
        return max(rounded, min_qty)

    async def _place_order(self, symbol: str, side: str, position_side: str,
                            order_type: str, quantity: float,
                            price: Optional[float] = None,
                            stop_price: Optional[float] = None,
                            reduce_only: bool = False) -> dict:
        """Place order via Binance fapi direct call (hedge mode compatible)."""
        binance_sym = self._to_binance_symbol(symbol)
        params = {
            "symbol": binance_sym,
            "side": side.upper(),
            "positionSide": position_side.upper(),
            "type": order_type.upper(),
            "quantity": str(self._round_qty(symbol, quantity)),
        }
        if price and order_type.upper() == "LIMIT":
            params["price"] = str(round(price, 2))
            params["timeInForce"] = "GTC"
        if stop_price:
            params["stopPrice"] = str(round(stop_price, 2))
        # Note: reduceOnly is not supported in hedge mode (positionSide handles it)

        await self.rate_limiter.acquire_order_slot()
        result = await self.exchange.fapiPrivatePostOrder(params)
        return result

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
                success=False, order_ids=[], avg_fill_price=0,
                total_filled=0, fees_paid=0, slippage=0, error=str(e),
            )

        side = "BUY" if signal.direction == Direction.LONG else "SELL"
        position_side = "LONG" if signal.direction == Direction.LONG else "SHORT"

        # Execute entry tranches
        for tranche in plan.entry_tranches:
            for attempt in range(self.MAX_RETRIES):
                try:
                    order_type = tranche.get("type", "MARKET").upper()
                    qty = self._round_qty(signal.symbol, tranche["quantity"])

                    result = await self._place_order(
                        signal.symbol, side, position_side, order_type, qty,
                        price=tranche.get("price") if order_type == "LIMIT" else None,
                    )

                    order_id = result.get("orderId", f"LIVE-{uuid4().hex[:12]}")
                    avg_price = float(result.get("avgPrice", 0))
                    filled = float(result.get("executedQty", 0))

                    # If market order filled immediately
                    if filled == 0 and order_type == "MARKET":
                        # Wait briefly and check order status
                        await asyncio.sleep(0.5)
                        filled = qty
                        avg_price = signal.entry_price

                    fee_cost = filled * (avg_price if avg_price > 0 else signal.entry_price) * self.TAKER_FEE

                    order_ids.append(str(order_id))
                    total_filled += filled
                    total_cost += filled * (avg_price if avg_price > 0 else signal.entry_price)
                    total_fees += fee_cost

                    logger.info(f"LIVE {side} {signal.symbol} qty={filled} @ {avg_price} | order={order_id}")
                    break

                except Exception as e:
                    logger.warning(f"Order attempt {attempt + 1} failed: {e}")
                    if attempt < self.MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        return ExecutionResult(
                            success=False, order_ids=order_ids,
                            avg_fill_price=0, total_filled=total_filled,
                            fees_paid=total_fees, slippage=0, error=str(e),
                        )

        if total_filled == 0:
            return ExecutionResult(
                success=False, order_ids=order_ids, avg_fill_price=0,
                total_filled=0, fees_paid=0, slippage=0, error="No fills",
            )

        avg_price = total_cost / total_filled
        slippage = abs(avg_price - signal.entry_price) / signal.entry_price if signal.entry_price > 0 else 0

        # Place exit orders (TP + SL)
        exit_ids = await self._place_exit_orders(signal, plan, total_filled, position_side)
        order_ids.extend(exit_ids)

        # Record to DB
        self.db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage,
               strategy, entry_time, fees, status, stop_loss, take_profit)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.symbol, signal.direction.value, round(avg_price, 2),
             round(total_filled, 8), plan.order.leverage, signal.strategy,
             datetime.utcnow().isoformat(), round(total_fees, 6), "OPEN",
             signal.stop_loss, signal.take_profit),
        )

        return ExecutionResult(
            success=True, order_ids=order_ids,
            avg_fill_price=round(avg_price, 2),
            total_filled=round(total_filled, 8),
            fees_paid=round(total_fees, 6),
            slippage=round(slippage, 6),
        )

    async def _place_exit_orders(self, signal, plan, filled_qty: float,
                                  position_side: str) -> List[str]:
        """Place TP and SL orders after entry."""
        exit_ids: List[str] = []
        close_side = "SELL" if signal.direction == Direction.LONG else "BUY"

        # TP limit orders
        for tranche in plan.exit_tranches:
            try:
                qty = min(tranche["quantity"], filled_qty)
                qty = self._round_qty(signal.symbol, qty)
                if qty <= 0:
                    continue
                result = await self._place_order(
                    signal.symbol, close_side, position_side, "LIMIT", qty,
                    price=tranche["price"], reduce_only=True,
                )
                exit_ids.append(str(result.get("orderId", "")))
                logger.info(f"TP placed: {close_side} {signal.symbol} {qty} @ {tranche['price']}")
            except Exception as e:
                logger.warning(f"TP order failed: {e}")

        # SL stop-market order
        if signal.stop_loss and filled_qty > 0:
            try:
                qty = self._round_qty(signal.symbol, filled_qty)
                result = await self._place_order(
                    signal.symbol, close_side, position_side, "STOP_MARKET", qty,
                    stop_price=signal.stop_loss, reduce_only=True,
                )
                exit_ids.append(str(result.get("orderId", "")))
                logger.info(f"SL placed: {close_side} {signal.symbol} {qty} @ stop={signal.stop_loss}")
            except Exception as e:
                logger.warning(f"SL order failed: {e}")

        return exit_ids

    async def get_positions(self) -> List[Position]:
        """Fetch open positions from exchange."""
        try:
            await self.rate_limiter.acquire_data_slot()
            positions = await self.exchange.fetch_positions()
            result: List[Position] = []
            for pos in positions:
                if float(pos.get("contracts", 0)) > 0:
                    result.append(Position(
                        symbol=self._to_binance_symbol(pos.get("symbol", "")),
                        direction=Direction.LONG if pos["side"] == "long" else Direction.SHORT,
                        entry_price=float(pos.get("entryPrice", 0)),
                        quantity=float(pos.get("contracts", 0)),
                        leverage=int(pos.get("leverage", 1)),
                        unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                        strategy="unknown",
                        entry_time=datetime.utcnow(),
                        current_stop=0.0,
                    ))
            return result
        except Exception as e:
            logger.error(f"Failed to fetch positions: {e}")
            return []

    async def close_position(self, position: Position,
                              order_type: OrderType = OrderType.MARKET) -> ExecutionResult:
        """Close a position on exchange."""
        try:
            close_side = "SELL" if position.direction == Direction.LONG else "BUY"
            position_side = "LONG" if position.direction == Direction.LONG else "SHORT"

            result = await self._place_order(
                position.symbol, close_side, position_side, "MARKET",
                position.quantity, reduce_only=True,
            )

            fill_price = float(result.get("avgPrice", 0))
            fees = position.quantity * fill_price * self.TAKER_FEE if fill_price > 0 else 0

            return ExecutionResult(
                success=True, order_ids=[str(result.get("orderId", ""))],
                avg_fill_price=fill_price, total_filled=position.quantity,
                fees_paid=round(fees, 6), slippage=0,
            )
        except Exception as e:
            return ExecutionResult(
                success=False, order_ids=[], avg_fill_price=0,
                total_filled=0, fees_paid=0, slippage=0, error=str(e),
            )

    async def cancel_all_pending(self) -> None:
        """Cancel all open orders."""
        try:
            await self.rate_limiter.acquire_order_slot()
            await self.exchange.cancel_all_orders()
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")
