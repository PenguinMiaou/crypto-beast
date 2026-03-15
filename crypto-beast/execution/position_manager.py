# execution/position_manager.py
"""Monitors open positions and auto-closes on SL/TP hit."""
from typing import List, Optional, Callable
from datetime import datetime

from loguru import logger
from core.database import Database
from core.models import Direction, OrderType, Position


class PositionManager:
    """Monitor open positions and trigger SL/TP exits."""

    def __init__(self, db: Database, get_price_fn: Callable[[str], float],
                 executor=None):
        self.db = db
        self._get_price = get_price_fn
        self._executor = executor  # LiveExecutor or None for paper mode

    def check_positions(self) -> List[dict]:
        """Check all open positions against their SL/TP.

        Returns list of positions that should be closed with reason.
        """
        rows = self.db.execute(
            "SELECT id, symbol, side, entry_price, quantity, leverage, stop_loss, take_profit, strategy FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        to_close: List[dict] = []

        for row in rows:
            trade_id, symbol, side, entry_price, quantity, leverage, stop_loss, take_profit, strategy = row

            if stop_loss is None and take_profit is None:
                continue

            current_price = self._get_price(symbol)
            if current_price <= 0:
                continue

            reason = None
            exit_price = current_price

            if side == "LONG":
                if stop_loss and current_price <= stop_loss:
                    reason = "STOP_LOSS"
                    exit_price = stop_loss  # Assume filled at stop
                elif take_profit and current_price >= take_profit:
                    reason = "TAKE_PROFIT"
                    exit_price = take_profit
            elif side == "SHORT":
                if stop_loss and current_price >= stop_loss:
                    reason = "STOP_LOSS"
                    exit_price = stop_loss
                elif take_profit and current_price <= take_profit:
                    reason = "TAKE_PROFIT"
                    exit_price = take_profit

            if reason:
                # Calculate PnL
                if side == "LONG":
                    pnl = (exit_price - entry_price) * quantity * leverage
                else:
                    pnl = (entry_price - exit_price) * quantity * leverage

                fees = exit_price * quantity * 0.0004  # taker fee
                net_pnl = pnl - fees

                to_close.append({
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": round(exit_price, 2),
                    "quantity": quantity,
                    "leverage": leverage,
                    "pnl": round(net_pnl, 4),
                    "fees": round(fees, 6),
                    "reason": reason,
                    "strategy": strategy,
                })

        return to_close

    def close_trade(self, trade: dict) -> None:
        """Close a trade in the database."""
        self.db.execute(
            "UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, fees = fees + ?, status = 'CLOSED' WHERE id = ?",
            (trade["exit_price"], datetime.utcnow().isoformat(), trade["pnl"], trade["fees"], trade["trade_id"])
        )
        logger.info(
            f"CLOSED {trade['side']} {trade['symbol']} @ ${trade['exit_price']:,.2f} | "
            f"PnL={trade['pnl']:+.4f} | Reason={trade['reason']} | Strategy={trade['strategy']}"
        )

    async def close_trade_live(self, trade: dict) -> bool:
        """Close a trade on the exchange (live mode) and update DB.

        In live mode, the SL/TP orders are already placed on the exchange
        via LiveExecutor._place_exit_orders(). This method is a fallback
        for cases where exchange orders didn't trigger (e.g., API lag).
        """
        if self._executor is None:
            self.close_trade(trade)
            return True

        try:
            position = Position(
                symbol=trade["symbol"],
                direction=Direction.LONG if trade["side"] == "LONG" else Direction.SHORT,
                entry_price=trade["entry_price"],
                quantity=trade["quantity"],
                leverage=trade["leverage"],
                unrealized_pnl=trade["pnl"],
                strategy=trade["strategy"],
                entry_time=datetime.utcnow(),
                current_stop=0.0,
            )
            result = await self._executor.close_position(position, OrderType.MARKET)
            if result.success:
                # Update DB with actual fill price
                actual_pnl = trade["pnl"]  # Could recalculate from result.avg_fill_price
                self.db.execute(
                    "UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, fees = fees + ?, status = 'CLOSED' WHERE id = ?",
                    (result.avg_fill_price, datetime.utcnow().isoformat(),
                     actual_pnl, result.fees_paid, trade["trade_id"])
                )
                logger.info(
                    f"LIVE CLOSED {trade['side']} {trade['symbol']} @ ${result.avg_fill_price:,.2f} | "
                    f"PnL={actual_pnl:+.4f} | Reason={trade['reason']}"
                )
                return True
            else:
                logger.error(f"Live close failed: {result.error}")
                return False
        except Exception as e:
            logger.error(f"Live close exception: {e}")
            return False
