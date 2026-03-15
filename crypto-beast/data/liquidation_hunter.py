"""Liquidation Hunter - Detects liquidation cascades for reversal entries."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.models import DirectionalBias, SignalType


class LiquidationHunter:
    def __init__(self, cascade_multiplier: float = 2.0, window_minutes: int = 5):
        self.cascade_multiplier = cascade_multiplier
        self.window_minutes = window_minutes
        self._events: List[dict] = []  # [{side, quantity, price, timestamp}]
        self._avg_volume = 0.0  # Rolling average liquidation volume per window
        self._volume_history: List[float] = []  # Historical window volumes

    def process_liquidation(self, event: dict) -> None:
        """Process a forceOrder event."""
        self._events.append(event)
        # Prune old events (keep last 30 min)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        self._events = [
            e for e in self._events
            if self._ensure_aware(e.get("timestamp", datetime.now(timezone.utc))) > cutoff
        ]

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt

    def _get_window_volume(self, side: Optional[str] = None) -> float:
        """Get total liquidation volume in current window."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.window_minutes)
        events = [
            e for e in self._events
            if self._ensure_aware(e.get("timestamp", datetime.now(timezone.utc))) > cutoff
        ]
        if side:
            events = [e for e in events if e.get("side") == side]
        return sum(e.get("quantity", 0) * e.get("price", 0) for e in events)

    def is_cascade_active(self) -> bool:
        """Check if liquidation cascade is happening."""
        current_vol = self._get_window_volume()
        return self._avg_volume > 0 and current_vol > self._avg_volume * self.cascade_multiplier

    def update_average(self, volume: float) -> None:
        """Update rolling average volume (called periodically)."""
        self._volume_history.append(volume)
        if len(self._volume_history) > 100:
            self._volume_history = self._volume_history[-100:]
        self._avg_volume = (
            sum(self._volume_history) / len(self._volume_history)
            if self._volume_history else 0
        )

    def get_signal(self, symbol: str = "BTCUSDT") -> DirectionalBias:
        """Generate signal from liquidation data."""
        if not self._events:
            return DirectionalBias(
                source="liquidation_hunter", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.0,
                reason="No liquidation data",
            )

        long_liqs = self._get_window_volume("LONG")
        short_liqs = self._get_window_volume("SHORT")

        if not self.is_cascade_active():
            return DirectionalBias(
                source="liquidation_hunter", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.1,
                reason="Normal liquidation activity",
            )

        # After cascade: entry in opposite direction (exhaustion)
        total = long_liqs + short_liqs
        if total == 0:
            return DirectionalBias(
                source="liquidation_hunter", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.0,
                reason="No volume",
            )

        if long_liqs > short_liqs:
            # Long cascade = price dropped hard = potential bounce
            confidence = min(0.8, 0.4 + (long_liqs / total - 0.5) * 0.8)
            return DirectionalBias(
                source="liquidation_hunter", symbol=symbol,
                direction=SignalType.BULLISH, confidence=round(confidence, 2),
                reason=f"Long liquidation cascade: ${long_liqs:.0f}",
            )
        else:
            confidence = min(0.8, 0.4 + (short_liqs / total - 0.5) * 0.8)
            return DirectionalBias(
                source="liquidation_hunter", symbol=symbol,
                direction=SignalType.BEARISH, confidence=round(confidence, 2),
                reason=f"Short liquidation cascade: ${short_liqs:.0f}",
            )
