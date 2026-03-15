"""OrderBook Sniper - Analyzes order book imbalance and wall detection."""

from typing import List

from core.models import DirectionalBias, SignalType


class OrderBookSniper:
    def __init__(
        self,
        imbalance_bullish: float = 1.5,
        imbalance_bearish: float = 0.67,
        wall_multiplier: float = 5.0,
    ):
        self.imbalance_bullish = imbalance_bullish
        self.imbalance_bearish = imbalance_bearish
        self.wall_multiplier = wall_multiplier

    def get_imbalance(self, orderbook: dict) -> float:
        """Calculate bid/ask volume ratio at top 20 levels."""
        bids = orderbook.get("bids", [])[:20]
        asks = orderbook.get("asks", [])[:20]
        bid_vol = sum(level[1] for level in bids)
        ask_vol = sum(level[1] for level in asks)
        if ask_vol == 0:
            return float("inf")
        return bid_vol / ask_vol

    def detect_walls(self, orderbook: dict) -> List[dict]:
        """Find price levels with quantity > wall_multiplier * average."""
        all_levels = orderbook.get("bids", []) + orderbook.get("asks", [])
        if not all_levels:
            return []
        avg_qty = sum(level[1] for level in all_levels) / len(all_levels)
        walls: List[dict] = []
        for level in all_levels:
            if level[1] > avg_qty * self.wall_multiplier:
                wall_type = (
                    "support"
                    if level in orderbook.get("bids", [])
                    else "resistance"
                )
                walls.append({
                    "price": level[0],
                    "quantity": level[1],
                    "type": wall_type,
                })
        return walls

    def get_signal(self, symbol: str, orderbook: dict) -> DirectionalBias:
        """Generate signal from order book analysis."""
        imbalance = self.get_imbalance(orderbook)

        if imbalance > self.imbalance_bullish:
            confidence = min(0.6, 0.3 + (imbalance - 1.5) * 0.15)
            return DirectionalBias(
                source="orderbook_sniper", symbol=symbol,
                direction=SignalType.BULLISH, confidence=round(confidence, 2),
                reason=f"Bid/ask imbalance: {imbalance:.2f}",
            )
        elif imbalance < self.imbalance_bearish:
            confidence = min(0.6, 0.3 + (0.67 - imbalance) * 0.3)
            return DirectionalBias(
                source="orderbook_sniper", symbol=symbol,
                direction=SignalType.BEARISH, confidence=round(confidence, 2),
                reason=f"Bid/ask imbalance: {imbalance:.2f}",
            )

        return DirectionalBias(
            source="orderbook_sniper", symbol=symbol,
            direction=SignalType.NEUTRAL, confidence=0.1,
            reason=f"Balanced orderbook: {imbalance:.2f}",
        )
