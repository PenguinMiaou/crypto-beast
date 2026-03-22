"""Live Binance Futures executor — direct API for hedge mode compatibility."""
import aiohttp
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict
from uuid import uuid4

from dotenv import dotenv_values
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
        env = dotenv_values(str(Path(__file__).parent.parent / ".env"))
        self._api_key = env.get("BINANCE_API_KEY", "")
        self._api_secret = env.get("BINANCE_API_SECRET", "")
        self._http_session: Optional[aiohttp.ClientSession] = None

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

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self):
        """Close persistent HTTP session."""
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    async def _place_order(self, symbol: str, side: str, position_side: str,
                            order_type: str, quantity: float,
                            price: Optional[float] = None,
                            stop_price: Optional[float] = None,
                            reduce_only: bool = False,
                            time_in_force: str = "GTC") -> dict:
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
            params["timeInForce"] = time_in_force
        if stop_price:
            params["stopPrice"] = str(round(stop_price, 2))
        # Note: reduceOnly is not supported in hedge mode (positionSide handles it)

        await self.rate_limiter.acquire_order_slot()
        result = await self.exchange.fapiPrivatePostOrder(params)
        return result

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute a trade plan on Binance."""
        signal = plan.order.signal

        # Guard: reject zero/tiny quantity orders (ghost orders from stale signals)
        total_planned_qty = sum(t.get("quantity", 0) for t in plan.entry_tranches)
        if total_planned_qty <= 0:
            logger.warning(f"Rejected ghost order: {signal.symbol} qty={total_planned_qty}")
            return ExecutionResult(
                success=False, order_ids=[], avg_fill_price=0,
                total_filled=0, fees_paid=0, slippage=0, error="zero_quantity",
            )

        ccxt_symbol = self._to_ccxt_symbol(signal.symbol)
        order_ids: List[str] = []
        total_filled = 0.0
        total_cost = 0.0
        total_fees = 0.0

        # Set leverage — -2028 means margin不足以支撑新杠杆，用当前杠杆继续即可
        try:
            await self.rate_limiter.acquire_order_slot()
            await self.exchange.set_leverage(plan.order.leverage, ccxt_symbol)
        except Exception as e:
            if "-2028" in str(e):
                logger.warning(f"杠杆设置跳过(保证金不足以调整)，使用当前杠杆继续: {ccxt_symbol}")
            else:
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
                        time_in_force=tranche.get("timeInForce", "GTC"),
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

        # Record to DB — prevent duplicate OPEN records per symbol
        existing = self.db.execute(
            "SELECT id FROM trades WHERE symbol=? AND side=? AND status='OPEN'",
            (signal.symbol, signal.direction.value)
        ).fetchone()
        if existing:
            # Update existing record (position was added to on exchange)
            self.db.execute(
                "UPDATE trades SET entry_price=?, quantity=?, leverage=?, fees=fees+?, "
                "stop_loss=?, take_profit=? WHERE id=?",
                (round(avg_price, 2), round(total_filled, 8), plan.order.leverage,
                 round(total_fees, 6), signal.stop_loss, signal.take_profit, existing[0]),
            )
        else:
            self.db.execute(
                """INSERT INTO trades (symbol, side, entry_price, quantity, leverage,
                   strategy, entry_time, fees, status, stop_loss, take_profit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (signal.symbol, signal.direction.value, round(avg_price, 2),
                 round(total_filled, 8), plan.order.leverage, signal.strategy,
                 datetime.now(timezone.utc).isoformat(), round(total_fees, 6), "OPEN",
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
        """Place TP and SL via Binance Algo Order API (hedge mode compatible).

        Uses /fapi/v1/algoOrder with algoType=CONDITIONAL.
        These orders persist on the exchange — survive bot crashes.
        """
        exit_ids: List[str] = []
        close_side = "SELL" if signal.direction == Direction.LONG else "BUY"
        binance_sym = self._to_binance_symbol(signal.symbol)

        # SL stop-market order (most important — placed first)
        if signal.stop_loss and filled_qty > 0:
            qty = self._round_qty(signal.symbol, filled_qty)
            try:
                result = await self._place_algo_order(
                    binance_sym, close_side, position_side,
                    "STOP_MARKET", qty, signal.stop_loss)
                algo_id = result.get("algoId", "")
                exit_ids.append(str(algo_id))
                logger.info(f"SL placed: {close_side} {signal.symbol} {qty} @ stop={signal.stop_loss} | algoId={algo_id}")
            except Exception as e:
                logger.warning(f"SL order failed: {e}")

        # TP: NOT placed on exchange — managed by bot's profit protection mechanism.
        # Reason: exchange TP triggers instant close, then bot re-opens same direction = double fees.
        # Profit protection tracks peak profit and closes when 50% is given back — more flexible.
        # Only SL is on exchange (survives bot crash = safety net).

        return exit_ids

    async def _place_algo_order(self, binance_sym: str, side: str,
                                 position_side: str, order_type: str,
                                 qty: float, trigger_price: float) -> dict:
        """Place order via Binance Algo Order API (/fapi/v1/algoOrder).

        Required for STOP_MARKET/TAKE_PROFIT_MARKET in hedge mode since 2025-12-09.
        """
        import hmac, hashlib, time as _time
        from urllib.parse import urlencode

        params = {
            "symbol": binance_sym,
            "side": side.upper(),
            "positionSide": position_side.upper(),
            "algoType": "CONDITIONAL",
            "type": order_type,
            "quantity": str(qty),
            "triggerPrice": str(round(trigger_price, 2)),
            "workingType": "MARK_PRICE",
            "timestamp": int(_time.time() * 1000),
        }
        query = urlencode(params)
        signature = hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com/fapi/v1/algoOrder?{query}&signature={signature}"

        await self.rate_limiter.acquire_order_slot()
        session = await self._get_http_session()
        async with session.post(url, headers={"X-MBX-APIKEY": self._api_key}) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Algo order failed ({resp.status}): {text}")
            return await resp.json()

    async def _place_sl_limit(self, symbol: str, side: str, position_side: str,
                               qty: float, stop_price: float,
                               is_long: bool) -> dict:
        """Place a STOP limit order as fallback for STOP_MARKET."""
        binance_sym = self._to_binance_symbol(symbol)
        # For LONG close (SELL), limit price slightly below stop to ensure fill
        # For SHORT close (BUY), limit price slightly above stop
        slippage = 0.005  # 0.5% slippage tolerance
        if is_long:
            limit_price = round(stop_price * (1 - slippage), 2)
        else:
            limit_price = round(stop_price * (1 + slippage), 2)

        params = {
            "symbol": binance_sym,
            "side": side.upper(),
            "positionSide": position_side.upper(),
            "type": "STOP",
            "quantity": str(self._round_qty(symbol, qty)),
            "price": str(limit_price),
            "stopPrice": str(round(stop_price, 2)),
            "timeInForce": "GTC",
        }
        await self.rate_limiter.acquire_order_slot()
        return await self.exchange.fapiPrivatePostOrder(params)

    async def _place_tp_limit(self, symbol: str, side: str, position_side: str,
                               qty: float, tp_price: float) -> dict:
        """Place a TAKE_PROFIT limit order as fallback for TAKE_PROFIT_MARKET."""
        binance_sym = self._to_binance_symbol(symbol)
        params = {
            "symbol": binance_sym,
            "side": side.upper(),
            "positionSide": position_side.upper(),
            "type": "TAKE_PROFIT",
            "quantity": str(self._round_qty(symbol, qty)),
            "price": str(round(tp_price, 2)),
            "stopPrice": str(round(tp_price, 2)),
            "timeInForce": "GTC",
        }
        await self.rate_limiter.acquire_order_slot()
        return await self.exchange.fapiPrivatePostOrder(params)

    async def get_positions(self) -> List[Position]:
        """Fetch open positions from exchange via direct fapi call.
        Falls back to DB if API fails (prevents opening positions when status unknown).
        """
        try:
            await self.rate_limiter.acquire_data_slot()
            account = await self.exchange.fapiPrivateV2GetAccount()
            result: List[Position] = []
            for pos in account.get("positions", []):
                amt = float(pos.get("positionAmt", 0))
                if amt == 0:
                    continue
                result.append(Position(
                    symbol=pos["symbol"],
                    direction=Direction.LONG if amt > 0 else Direction.SHORT,
                    entry_price=float(pos.get("entryPrice", 0)),
                    quantity=abs(amt),
                    leverage=int(pos.get("leverage", 1)),
                    unrealized_pnl=float(pos.get("unrealizedProfit", 0)),
                    strategy="live",
                    entry_time=datetime.now(timezone.utc),
                    current_stop=0.0,
                ))
            return result
        except Exception as e:
            logger.error(f"Failed to fetch positions from exchange: {e}")
            # Fallback to DB to prevent opening new positions when status unknown
            try:
                rows = self.db.execute(
                    "SELECT symbol, side, entry_price, quantity, leverage, strategy "
                    "FROM trades WHERE status = 'OPEN'"
                ).fetchall()
                result: List[Position] = []
                for r in rows:
                    result.append(Position(
                        symbol=r[0],
                        direction=Direction.LONG if r[1] == "LONG" else Direction.SHORT,
                        entry_price=float(r[2]),
                        quantity=float(r[3]),
                        leverage=int(r[4]),
                        unrealized_pnl=0.0,
                        strategy=r[5] or "unknown",
                        entry_time=datetime.now(timezone.utc),
                        current_stop=0.0,
                    ))
                if result:
                    logger.info(f"Using DB fallback: {len(result)} positions")
                return result
            except Exception as e2:
                logger.error(f"DB fallback also failed: {e2}")
                return []

    async def get_positions_and_account(self):
        """Fetch positions + account data in single API call.

        Returns (positions, equity, available_balance, wallet_balance).
        equity = totalMarginBalance (wallet + unrealized PnL).
        wallet_balance = totalWalletBalance (realized only, used for peak tracking).
        """
        try:
            await self.rate_limiter.acquire_data_slot()
            account = await self.exchange.fapiPrivateV2GetAccount()
            positions = []
            for pos in account.get("positions", []):
                amt = float(pos.get("positionAmt", 0))
                if amt == 0:
                    continue
                positions.append(Position(
                    symbol=pos["symbol"],
                    direction=Direction.LONG if amt > 0 else Direction.SHORT,
                    entry_price=float(pos.get("entryPrice", 0)),
                    quantity=abs(amt),
                    leverage=int(pos.get("leverage", 1)),
                    unrealized_pnl=float(pos.get("unrealizedProfit", 0)),
                    strategy="exchange",  # placeholder, reconciliation overrides
                    entry_time=datetime.now(timezone.utc),  # placeholder
                    current_stop=0.0,
                ))
            equity = float(account.get("totalMarginBalance", 0))
            available = float(account.get("availableBalance", 0))
            wallet_balance = float(account.get("totalWalletBalance", 0))
            return positions, equity, available, wallet_balance
        except Exception as e:
            logger.error(f"Failed to fetch account: {e}")
            return [], 0.0, 0.0, 0.0

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
            filled_qty = float(result.get("executedQty", 0))

            # If fill_price=0 or filled_qty=0, position was likely already closed on exchange
            if fill_price <= 0 or filled_qty <= 0:
                logger.info(f"Position {position.symbol} close returned fill=0 (likely already closed by exchange SL)")
                return ExecutionResult(
                    success=False, order_ids=[], avg_fill_price=0,
                    total_filled=0, fees_paid=0, slippage=0,
                    error="already_closed",
                )

            fees = filled_qty * fill_price * self.TAKER_FEE

            # Cancel any remaining algo orders (SL) for this symbol+side
            binance_sym = self._to_binance_symbol(position.symbol)
            pos_side = "LONG" if position.direction == Direction.LONG else "SHORT"
            try:
                await self.cancel_algo_orders(binance_sym, pos_side)
            except Exception as e:
                logger.warning(f"Failed to cancel algo orders for {position.symbol}: {e}")

            return ExecutionResult(
                success=True, order_ids=[str(result.get("orderId", ""))],
                avg_fill_price=fill_price, total_filled=filled_qty,
                fees_paid=round(fees, 6), slippage=0,
            )
        except Exception as e:
            error_str = str(e)
            # -2022 "ReduceOnly Order is rejected" means position already closed
            # (e.g., exchange SL/TP already triggered). Return success=False so caller
            # doesn't try to open a new position in the same cycle.
            if "-2022" in error_str:
                logger.info(f"Position {position.symbol} already closed on exchange (SL/TP triggered)")
                # Position closed by exchange SL — cancel remaining algo orders too
                binance_sym = self._to_binance_symbol(position.symbol)
                pos_side = "LONG" if position.direction == Direction.LONG else "SHORT"
                try:
                    await self.cancel_algo_orders(binance_sym, pos_side)
                except Exception:
                    pass
                return ExecutionResult(
                    success=False, order_ids=[], avg_fill_price=0,
                    total_filled=0, fees_paid=0, slippage=0,
                    error="already_closed",
                )
            return ExecutionResult(
                success=False, order_ids=[], avg_fill_price=0,
                total_filled=0, fees_paid=0, slippage=0, error=error_str,
            )

    async def cancel_algo_orders(self, symbol: Optional[str] = None,
                                 position_side: Optional[str] = None) -> int:
        """Cancel open algo orders (SL/TP conditional orders).

        Args:
            symbol: Binance symbol (e.g. 'BTCUSDT'). If None, cancels ALL open algo orders.
            position_side: 'LONG' or 'SHORT'. If set, only cancel orders matching this side.
                           Important in hedge mode to avoid cancelling the other side's SL.

        Returns:
            Number of algo orders cancelled.
        """
        import hmac, hashlib, time as _time
        from urllib.parse import urlencode

        # Step 1: Query open algo orders
        query_params: Dict[str, object] = {
            "timestamp": int(_time.time() * 1000),
        }
        if symbol:
            query_params["symbol"] = symbol
        query = urlencode(query_params)
        signature = hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com/fapi/v1/openAlgoOrders?{query}&signature={signature}"

        cancelled = 0
        try:
            await self.rate_limiter.acquire_order_slot()
            session = await self._get_http_session()
            async with session.get(url, headers={"X-MBX-APIKEY": self._api_key}) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to query algo orders: {await resp.text()}")
                    return 0
                data = await resp.json()

            orders = data if isinstance(data, list) else data.get("orders", [])

            # Filter by positionSide if specified (hedge mode: don't cancel other side)
            if position_side:
                orders = [o for o in orders if o.get("positionSide") == position_side]

            if not orders:
                return 0

            logger.info(f"Found {len(orders)} algo orders to cancel"
                        f"{f' for {symbol}' if symbol else ''}"
                        f"{f' {position_side}' if position_side else ''}")

            # Step 2: Cancel each algo order
            for order in orders:
                algo_id = order.get("algoId")
                if not algo_id:
                    continue
                try:
                    cancel_params = {
                        "algoId": algo_id,
                        "timestamp": int(_time.time() * 1000),
                    }
                    cquery = urlencode(cancel_params)
                    csig = hmac.new(self._api_secret.encode(), cquery.encode(), hashlib.sha256).hexdigest()
                    curl = f"https://fapi.binance.com/fapi/v1/algoOrder?{cquery}&signature={csig}"

                    await self.rate_limiter.acquire_order_slot()
                    session = await self._get_http_session()
                    async with session.delete(curl, headers={"X-MBX-APIKEY": self._api_key}) as cresp:
                        if cresp.status == 200:
                            cancelled += 1
                        else:
                            logger.warning(f"Failed to cancel algoId={algo_id}: {await cresp.text()}")
                except Exception as e:
                    logger.warning(f"Error cancelling algoId={algo_id}: {e}")

            logger.info(f"Cancelled {cancelled}/{len(orders)} algo orders")
        except Exception as e:
            logger.error(f"cancel_algo_orders error: {e}")

        return cancelled

    async def cancel_all_pending(self) -> None:
        """Cancel all open orders (regular + algo) for all traded symbols."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
        for sym in symbols:
            try:
                ccxt_sym = self._to_ccxt_symbol(sym)
                await self.rate_limiter.acquire_order_slot()
                await self.exchange.cancel_all_orders(ccxt_sym)
            except Exception:
                pass  # No open orders for this symbol is fine
        # Also cancel all algo orders (SL/TP conditional orders)
        await self.cancel_algo_orders()

    async def ensure_sl_orders(self, db: Database) -> int:
        """Check open positions and place missing SL algo orders.

        Called on startup after reconciliation to ensure all positions have
        exchange-level SL protection. Returns number of SL orders placed.
        """
        import hmac, hashlib, time as _time
        from urllib.parse import urlencode

        # Step 1: Get open algo orders to know which positions already have SL
        query_params = {"timestamp": int(_time.time() * 1000)}
        query = urlencode(query_params)
        signature = hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"https://fapi.binance.com/fapi/v1/openAlgoOrders?{query}&signature={signature}"

        existing_sl = set()  # (symbol, positionSide) that already have SL
        all_algo_orders = []
        try:
            await self.rate_limiter.acquire_order_slot()
            session = await self._get_http_session()
            async with session.get(url, headers={"X-MBX-APIKEY": self._api_key}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    all_algo_orders = data if isinstance(data, list) else data.get("orders", [])
                    for o in all_algo_orders:
                        existing_sl.add((o.get("symbol"), o.get("positionSide")))
        except Exception as e:
            logger.warning(f"Failed to query existing algo orders: {e}")

        # Step 2: Get open trades from DB
        DEFAULT_SL_PCT = 0.03  # 3% default SL for positions without one
        rows = db.execute(
            "SELECT symbol, side, quantity, stop_loss, entry_price FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        placed = 0
        for row in rows:
            symbol, side, qty, stop_loss, entry_price = row[0], row[1], row[2], row[3], row[4]
            position_side = side  # LONG or SHORT
            binance_sym = self._to_binance_symbol(symbol)

            # Skip if already has SL on exchange
            if (binance_sym, position_side) in existing_sl:
                logger.info(f"SL already exists for {symbol} {side}, skipping")
                continue

            # Calculate default SL if missing
            if not stop_loss or stop_loss <= 0:
                if not entry_price or entry_price <= 0:
                    logger.warning(f"No SL or entry price for {symbol} {side}, cannot place SL")
                    continue
                if side == "LONG":
                    stop_loss = round(entry_price * (1 - DEFAULT_SL_PCT), 2)
                else:
                    stop_loss = round(entry_price * (1 + DEFAULT_SL_PCT), 2)
                logger.info(f"Using default {DEFAULT_SL_PCT*100}% SL for {symbol} {side}: {stop_loss}")
                # Update DB so it's not 0 anymore
                db.execute(
                    "UPDATE trades SET stop_loss = ? WHERE symbol = ? AND side = ? AND status = 'OPEN'",
                    (stop_loss, symbol, side)
                )

            close_side = "SELL" if side == "LONG" else "BUY"
            rounded_qty = self._round_qty(symbol, qty)

            try:
                result = await self._place_algo_order(
                    binance_sym, close_side, position_side,
                    "STOP_MARKET", rounded_qty, stop_loss)
                algo_id = result.get("algoId", "")
                logger.info(f"SL补下: {close_side} {symbol} {rounded_qty} @ stop={stop_loss} | algoId={algo_id}")
                placed += 1
            except Exception as e:
                logger.warning(f"Failed to place SL for {symbol} {side}: {e}")

        if placed:
            logger.info(f"ensure_sl_orders: placed {placed} missing SL orders")
        else:
            logger.info("ensure_sl_orders: all positions have SL protection")

        # Step 3: Clean up orphaned algo orders (no matching open position)
        open_keys = set()
        for row in rows:
            binance_sym = self._to_binance_symbol(row[0])
            open_keys.add((binance_sym, row[1]))  # (symbol, side)

        for o in all_algo_orders:
            key = (o.get("symbol"), o.get("positionSide"))
            if key not in open_keys:
                algo_id = o.get("algoId")
                try:
                    cancel_params = {
                        "algoId": algo_id,
                        "timestamp": int(_time.time() * 1000),
                    }
                    cquery = urlencode(cancel_params)
                    csig = hmac.new(self._api_secret.encode(), cquery.encode(), hashlib.sha256).hexdigest()
                    curl = f"https://fapi.binance.com/fapi/v1/algoOrder?{cquery}&signature={csig}"
                    await self.rate_limiter.acquire_order_slot()
                    session = await self._get_http_session()
                    async with session.delete(curl, headers={"X-MBX-APIKEY": self._api_key}) as cresp:
                        if cresp.status == 200:
                            logger.info(f"Cleaned orphan algo: {key[0]} {key[1]} algoId={algo_id}")
                except Exception as e:
                    logger.warning(f"Failed to clean orphan algo {algo_id}: {e}")

        return placed
