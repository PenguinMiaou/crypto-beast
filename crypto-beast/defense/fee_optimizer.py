"""FeeOptimizer - Maker/taker optimization and fee budget tracking."""

from datetime import datetime
from typing import Optional, List

from core.models import TradeSignal, OrderType


class FeeOptimizer:
    """Optimizes order type (maker vs taker) and tracks fee budget."""

    MAKER_FEE = 0.0002  # 0.02% for Binance Futures
    TAKER_FEE = 0.0004  # 0.04%

    def __init__(self, daily_fee_budget: float = 5.0):
        self.daily_fee_budget = daily_fee_budget
        self._fees_today = 0.0
        self._last_reset = datetime.utcnow().date()

    def recommend_order_type(
        self, signal: TradeSignal, urgency: float = 0.5
    ) -> OrderType:
        """Recommend LIMIT (maker) or MARKET (taker) based on urgency and budget.

        High urgency (>0.7) or high confidence (>0.8) -> MARKET (faster fill).
        Otherwise -> LIMIT (lower fees).
        """
        if urgency > 0.7 or signal.confidence > 0.8:
            return OrderType.MARKET
        return OrderType.LIMIT

    def estimate_fee(self, notional: float, order_type: OrderType) -> float:
        """Estimate fee for a given notional value."""
        if order_type == OrderType.LIMIT:
            return notional * self.MAKER_FEE
        return notional * self.TAKER_FEE

    def record_fee(self, fee: float) -> None:
        """Record a fee payment, reset daily if needed."""
        self._maybe_reset()
        self._fees_today += fee

    def budget_remaining(self) -> float:
        """Return remaining fee budget for today."""
        self._maybe_reset()
        return max(0.0, self.daily_fee_budget - self._fees_today)

    def is_within_budget(self, estimated_fee: float) -> bool:
        """Check if estimated fee fits within daily budget."""
        self._maybe_reset()
        return (self._fees_today + estimated_fee) <= self.daily_fee_budget

    def _maybe_reset(self) -> None:
        """Reset daily fee counter if the date has changed."""
        today = datetime.utcnow().date()
        if today > self._last_reset:
            self._fees_today = 0.0
            self._last_reset = today
