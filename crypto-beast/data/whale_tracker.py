"""Whale Tracker - Monitors large trades (>$100k) for directional bias."""

from datetime import datetime, timedelta, timezone
from typing import List

from core.models import DirectionalBias, SignalType


class WhaleTracker:
    UPDATE_INTERVAL = 60  # seconds
    LARGE_TRADE_THRESHOLD = 100000  # $100k notional

    def __init__(self, large_trade_threshold: float = 100000):
        self.LARGE_TRADE_THRESHOLD = large_trade_threshold
        self._large_trades: List[dict] = []  # [{side, notional, timestamp}]
        self._last_update = 0.0

    def process_trade(self, trade: dict) -> None:
        """Process an aggTrade event. Keep if notional > threshold."""
        notional = trade.get("price", 0) * trade.get("quantity", 0)
        if notional >= self.LARGE_TRADE_THRESHOLD:
            self._large_trades.append({
                "side": "BUY" if not trade.get("is_buyer_maker", True) else "SELL",
                "notional": notional,
                "timestamp": trade.get("timestamp", datetime.now(timezone.utc)),
            })
            # Keep only last 15 min
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
            self._large_trades = [
                t for t in self._large_trades
                if (t["timestamp"].replace(tzinfo=timezone.utc) if t["timestamp"].tzinfo is None else t["timestamp"]) > cutoff
            ]

    def get_signal(self, symbol: str = "BTCUSDT") -> DirectionalBias:
        """Analyze recent whale activity."""
        if not self._large_trades:
            return DirectionalBias(
                source="whale_tracker", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.0,
                reason="No whale activity",
            )

        buys = sum(t["notional"] for t in self._large_trades if t["side"] == "BUY")
        sells = sum(t["notional"] for t in self._large_trades if t["side"] == "SELL")
        total = buys + sells

        if total == 0:
            return DirectionalBias(
                source="whale_tracker", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.0,
                reason="No volume",
            )

        ratio = buys / total
        if ratio > 0.6:
            confidence = min(0.7, 0.3 + (ratio - 0.6) * 2)
            return DirectionalBias(
                source="whale_tracker", symbol=symbol,
                direction=SignalType.BULLISH, confidence=round(confidence, 2),
                reason=f"Whale net buys: {ratio:.0%}",
            )
        elif ratio < 0.4:
            confidence = min(0.7, 0.3 + (0.4 - ratio) * 2)
            return DirectionalBias(
                source="whale_tracker", symbol=symbol,
                direction=SignalType.BEARISH, confidence=round(confidence, 2),
                reason=f"Whale net sells: {1 - ratio:.0%}",
            )

        return DirectionalBias(
            source="whale_tracker", symbol=symbol,
            direction=SignalType.NEUTRAL, confidence=0.1,
            reason="Balanced whale activity",
        )
