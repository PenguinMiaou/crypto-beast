# execution/paper_executor.py
import random
from datetime import datetime
from typing import Callable
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


class PaperExecutor:
    TAKER_FEE = 0.0004

    def __init__(self, db: Database, current_price_fn: Callable[[str], float]):
        self.db = db
        self._current_price_fn = current_price_fn

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        signal = plan.order.signal
        price = self._current_price_fn(signal.symbol)

        # Simulate slippage
        slippage = random.uniform(0, 0.001)
        if signal.direction == Direction.LONG:
            fill_price = price * (1 + slippage)
        else:
            fill_price = price * (1 - slippage)

        quantity = plan.order.quantity
        fees = quantity * fill_price * self.TAKER_FEE
        order_id = f"PAPER-{uuid4().hex[:12]}"

        # Record in database
        self.db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, fees, status, stop_loss, take_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.symbol,
                signal.direction.value,
                round(fill_price, 2),
                quantity,
                plan.order.leverage,
                signal.strategy,
                datetime.utcnow().isoformat(),
                round(fees, 6),
                "OPEN",
                signal.stop_loss,
                signal.take_profit,
            ),
        )

        logger.info(
            f"PAPER {signal.direction.value} {signal.symbol} @ {fill_price:.2f} | "
            f"qty={quantity} | lev={plan.order.leverage}x | fee={fees:.4f}"
        )

        return ExecutionResult(
            success=True,
            order_ids=[order_id],
            avg_fill_price=round(fill_price, 2),
            total_filled=quantity,
            fees_paid=round(fees, 6),
            slippage=round(slippage, 6),
        )

    async def get_positions(self) -> list[Position]:
        rows = self.db.execute(
            "SELECT id, symbol, side, entry_price, quantity, leverage, strategy, entry_time FROM trades WHERE status = 'OPEN'"
        ).fetchall()
        positions = []
        for row in rows:
            symbol = row[1]
            direction = Direction.LONG if row[2] == "LONG" else Direction.SHORT
            entry_price = row[3]
            current_price = self._current_price_fn(symbol)

            if direction == Direction.LONG:
                unrealized = (current_price - entry_price) * row[4] * row[5]
            else:
                unrealized = (entry_price - current_price) * row[4] * row[5]

            positions.append(Position(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=row[4],
                leverage=row[5],
                unrealized_pnl=round(unrealized, 4),
                strategy=row[6],
                entry_time=row[7],
                current_stop=0.0,
                order_ids=[f"PAPER-{row[0]}"],
            ))
        return positions

    async def close_position(self, position: Position, order_type: OrderType = OrderType.MARKET) -> ExecutionResult:
        current_price = self._current_price_fn(position.symbol)
        fees = position.quantity * current_price * self.TAKER_FEE
        pnl = position.unrealized_pnl - fees

        # Update database
        trade_id = int(position.order_ids[0].replace("PAPER-", "")) if position.order_ids else None
        if trade_id:
            self.db.execute(
                "UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, status = ? WHERE id = ?",
                (round(current_price, 2), datetime.utcnow().isoformat(), round(pnl, 4), "CLOSED", trade_id),
            )

        logger.info(f"PAPER CLOSE {position.symbol} @ {current_price:.2f} | PnL={pnl:.4f}")

        return ExecutionResult(
            success=True,
            order_ids=position.order_ids,
            avg_fill_price=current_price,
            total_filled=position.quantity,
            fees_paid=round(fees, 6),
            slippage=0.0,
        )

    async def cancel_all_pending(self) -> None:
        logger.info("PAPER: No pending orders to cancel")
