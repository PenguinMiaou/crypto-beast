# execution/position_manager.py
"""Monitors open positions and auto-closes on SL/TP hit.

Includes trailing stop and profit drawback protection.
"""
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone

from loguru import logger
from core.database import Database
from core.models import Direction, OrderType, Position

class PositionManager:
    """Monitor open positions and trigger SL/TP/trailing/profit-protection exits."""

    def __init__(self, db: Database, get_price_fn: Callable[[str], float],
                 config, executor=None):
        self.db = db
        self._get_price = get_price_fn
        self._executor = executor  # LiveExecutor or None for paper mode

        # Profit protection: activate at X% profit, close if Y% given back
        self._profit_protect_activation_pct = config.profit_protect_activation_pct
        self._profit_protect_drawback_pct = config.profit_protect_drawback_pct

        # Position timeout
        self._timeout_hours = getattr(config, 'position_timeout_hours', 48)
        self._timeout_pnl_min = getattr(config, 'timeout_pnl_min', -0.01)
        self._timeout_pnl_max = getattr(config, 'timeout_pnl_max', 0.02)

        # Track peak prices and profits per trade for trailing/protection
        # Peaks are persisted to DB (peak_profit column) so restarts don't lose them
        self._peak_prices: Dict[int, float] = {}   # trade_id -> peak favorable price
        self._peak_profits: Dict[int, float] = {}   # trade_id -> peak profit %
        self._load_peaks_from_db()

    def _load_peaks_from_db(self) -> None:
        """Load persisted peak profits from DB on startup."""
        try:
            rows = self.db.execute(
                "SELECT id, peak_profit FROM trades WHERE status = 'OPEN' AND peak_profit > 0"
            ).fetchall()
            for trade_id, peak_profit in rows:
                self._peak_profits[trade_id] = peak_profit
            if rows:
                logger.info(f"Restored peak tracking for {len(rows)} positions from DB")
        except Exception as e:
            logger.debug(f"Failed to load peaks from DB: {e}")

    def check_positions(self) -> List[dict]:
        """Check all open positions against SL/TP, trailing stop, and profit protection.

        Returns list of positions that should be closed with reason.
        """
        rows = self.db.execute(
            "SELECT id, symbol, side, entry_price, quantity, leverage, stop_loss, take_profit, strategy, entry_time FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        to_close: List[dict] = []

        for row in rows:
            trade_id, symbol, side, entry_price, quantity, leverage, stop_loss, take_profit, strategy, entry_time = row

            current_price = self._get_price(symbol)
            if current_price <= 0:
                continue

            # Calculate current profit % (leveraged — what you actually earn/lose)
            if side == "LONG":
                profit_pct = (current_price - entry_price) / entry_price * leverage
            else:
                profit_pct = (entry_price - current_price) / entry_price * leverage

            # Update peak tracking (persisted to DB so restarts don't lose it)
            peak_profit = self._peak_profits.get(trade_id, 0)
            if profit_pct > peak_profit:
                self._peak_profits[trade_id] = profit_pct
                self._peak_prices[trade_id] = current_price
                # Persist to DB
                try:
                    self.db.execute(
                        "UPDATE trades SET peak_profit = ? WHERE id = ?",
                        (round(profit_pct, 6), trade_id)
                    )
                except Exception:
                    pass
            peak_profit = self._peak_profits.get(trade_id, 0)

            reason = None
            exit_price = current_price

            # 1. Static SL/TP check
            if stop_loss and side == "LONG" and current_price <= stop_loss:
                reason = "STOP_LOSS"
                exit_price = stop_loss
            elif stop_loss and side == "SHORT" and current_price >= stop_loss:
                reason = "STOP_LOSS"
                exit_price = stop_loss
            elif take_profit and side == "LONG" and current_price >= take_profit:
                reason = "TAKE_PROFIT"
                exit_price = take_profit
            elif take_profit and side == "SHORT" and current_price <= take_profit:
                reason = "TAKE_PROFIT"
                exit_price = take_profit

            # 2. Profit protection (tiered — tighter protection at higher profits)
            # Activates at threshold, max allowed drawback decreases as profit grows
            if reason is None and peak_profit >= self._profit_protect_activation_pct:
                # Tiered drawback: higher profit = tighter protection
                if peak_profit >= 0.40:
                    max_drawback = 0.20  # 40%+ profit: only allow 20% giveback
                elif peak_profit >= 0.20:
                    max_drawback = 0.25  # 20-40% profit: allow 25% giveback
                elif peak_profit >= 0.10:
                    max_drawback = 0.30  # 10-20% profit: allow 30% giveback
                else:
                    max_drawback = self._profit_protect_drawback_pct  # <10%: default (50%)

                drawback = (peak_profit - profit_pct) / peak_profit if peak_profit > 0 else 0
                if drawback >= max_drawback:
                    reason = "PROFIT_PROTECT"
                    exit_price = current_price

            # 3. Timeout: close stale positions with small PnL
            if reason is None:
                try:
                    if entry_time:
                        entry_dt = datetime.fromisoformat(entry_time) if isinstance(entry_time, str) else entry_time
                        if entry_dt.tzinfo is None:
                            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
                        hours_held = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
                        if hours_held >= self._timeout_hours and self._timeout_pnl_min <= profit_pct <= self._timeout_pnl_max:
                            reason = "TIMEOUT"
                            exit_price = current_price
                except (ValueError, TypeError):
                    pass

            if reason:
                # Calculate PnL
                if side == "LONG":
                    pnl = (exit_price - entry_price) * quantity * leverage
                else:
                    pnl = (entry_price - exit_price) * quantity * leverage

                fees = exit_price * quantity * 0.0004  # taker fee
                net_pnl = pnl - fees

                # Clean up tracking
                self._peak_prices.pop(trade_id, None)
                self._peak_profits.pop(trade_id, None)

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
            (trade["exit_price"], datetime.now(timezone.utc).isoformat(), trade["pnl"], trade["fees"], trade["trade_id"])
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
                entry_time=datetime.now(timezone.utc),
                current_stop=0.0,
            )
            result = await self._executor.close_position(position, OrderType.MARKET)
            if result.success:
                # Update DB with actual fill price
                actual_pnl = trade["pnl"]
                self.db.execute(
                    "UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, fees = fees + ?, status = 'CLOSED' WHERE id = ?",
                    (result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
                     actual_pnl, result.fees_paid, trade["trade_id"])
                )
                logger.info(
                    f"LIVE CLOSED {trade['side']} {trade['symbol']} @ ${result.avg_fill_price:,.2f} | "
                    f"PnL={actual_pnl:+.4f} | Reason={trade['reason']}"
                )
                return True
            elif result.error == "already_closed":
                # Position was already closed by exchange SL — mark CLOSED in DB with estimated PnL
                self.db.execute(
                    "UPDATE trades SET exit_time = ?, exit_price = ?, pnl = ?, status = 'CLOSED' WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), trade["exit_price"], trade["pnl"], trade["trade_id"])
                )
                logger.info(f"Marked {trade['symbol']} as CLOSED in DB (exchange SL) PnL={trade['pnl']:+.4f}")
                return True
            else:
                logger.error(f"Live close failed: {result.error}")
                return False
        except Exception as e:
            logger.error(f"Live close exception: {e}")
            return False
