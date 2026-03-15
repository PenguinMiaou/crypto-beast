"""Smart order planning with DCA entries and scaled exits."""
from typing import Optional, List, Dict

from core.models import ExecutionPlan, ValidatedOrder, OrderType


class SmartOrder:
    """Plans multi-tranche execution for entries and exits."""

    def __init__(self, num_entry_tranches: int = 3, time_limit_hours: float = 4.0):
        self.num_entry_tranches = num_entry_tranches
        self.time_limit_hours = time_limit_hours

    def plan_execution(
        self, order: ValidatedOrder, urgency: float = 0.5
    ) -> ExecutionPlan:
        """Create execution plan with DCA entry and scaled exit.

        Args:
            order: Validated order from RiskManager.
            urgency: 0.0 (patient) to 1.0 (immediate).
                     High urgency = fewer tranches, MARKET orders.
        """
        signal = order.signal

        # High urgency: single market order
        if urgency >= 0.8:
            entry_tranches = [
                {
                    "price": signal.entry_price,
                    "quantity": order.quantity,
                    "type": "MARKET",
                }
            ]
        else:
            # DCA: split into tranches
            entry_tranches = self._split_entry(order, urgency)

        # Exit plan: 3 scaled TPs
        exit_tranches = self._plan_exits(order)

        # Trailing stop for remaining position
        trailing = None
        if urgency < 0.7:
            trailing = {
                "activation_pct": 0.01,  # Activate after 1% profit
                "trail_pct": 0.005,  # Trail by 0.5%
                "quantity_pct": 0.3,  # 30% of position
            }

        return ExecutionPlan(
            order=order,
            entry_tranches=entry_tranches,
            exit_tranches=exit_tranches,
            trailing_stop=trailing,
            time_limit_hours=self.time_limit_hours,
        )

    def _split_entry(
        self, order: ValidatedOrder, urgency: float
    ) -> List[Dict]:
        """Split entry into DCA tranches."""
        n = max(1, int(self.num_entry_tranches * (1 - urgency * 0.5)))
        qty_per = order.quantity / n
        signal = order.signal
        price = signal.entry_price

        tranches = []
        for i in range(n):
            # Each tranche slightly lower (for longs) or higher (for shorts)
            offset = i * 0.001 * price  # 0.1% spacing
            if signal.direction.value == "LONG":
                tranche_price = price - offset
            else:
                tranche_price = price + offset

            tranches.append(
                {
                    "price": round(tranche_price, 2),
                    "quantity": round(qty_per, 8),
                    "type": "LIMIT" if i > 0 else "MARKET",
                }
            )

        return tranches

    def _plan_exits(self, order: ValidatedOrder) -> List[Dict]:
        """Create scaled exit plan with 3 take-profit levels."""
        signal = order.signal
        entry = signal.entry_price
        tp = signal.take_profit

        # 3 TP levels: 40%, 30%, 30% of position
        tp_distance = abs(tp - entry)
        exits = []

        tp_levels = [
            (0.5, 0.4),  # TP1: 50% of distance, close 40%
            (0.75, 0.3),  # TP2: 75% of distance, close 30%
            (1.0, 0.3),  # TP3: full TP, close 30%
        ]

        for pct_distance, qty_pct in tp_levels:
            if signal.direction.value == "LONG":
                tp_price = entry + tp_distance * pct_distance
            else:
                tp_price = entry - tp_distance * pct_distance

            exits.append(
                {
                    "price": round(tp_price, 2),
                    "quantity": round(order.quantity * qty_pct, 8),
                    "trigger": f"TP_{int(pct_distance * 100)}",
                }
            )

        return exits
