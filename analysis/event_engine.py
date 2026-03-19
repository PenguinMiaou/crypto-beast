"""EventEngine: Track funding settlements and known scheduled events."""

from datetime import datetime, timezone
from typing import List, Dict, Optional


class EventEngine:
    """Track funding settlements and known events."""

    # Binance funding every 8h: 00:00, 08:00, 16:00 UTC
    FUNDING_HOURS = [0, 8, 16]

    def __init__(self) -> None:
        self._custom_events: List[dict] = []  # [{name, timestamp, impact}]

    def is_near_funding(self, minutes_before: int = 30) -> bool:
        """Check if we're within N minutes before a funding settlement."""
        now = datetime.now(timezone.utc)
        current_minutes = now.hour * 60 + now.minute
        for hour in self.FUNDING_HOURS:
            funding_minutes = hour * 60
            diff = funding_minutes - current_minutes
            if diff < 0:
                diff += 24 * 60  # wrap around
            if 0 < diff <= minutes_before:
                return True
        return False

    def is_near_funding_for_time(
        self, utc_hour: int, utc_minute: int, minutes_before: int = 30
    ) -> bool:
        """Testable version: check if a specific time is near funding."""
        current_minutes = utc_hour * 60 + utc_minute
        for hour in self.FUNDING_HOURS:
            funding_minutes = hour * 60
            diff = funding_minutes - current_minutes
            if diff < 0:
                diff += 24 * 60
            if 0 < diff <= minutes_before:
                return True
        return False

    def add_event(
        self, name: str, timestamp: datetime, impact: str = "medium"
    ) -> None:
        """Add a custom event."""
        self._custom_events.append(
            {"name": name, "timestamp": timestamp, "impact": impact}
        )

    def get_upcoming_events(self, hours_ahead: int = 4) -> List[dict]:
        """Get events in next N hours."""
        now = datetime.now(timezone.utc)
        cutoff = now.replace(hour=(now.hour + hours_ahead) % 24)
        return [
            e for e in self._custom_events if now <= e["timestamp"] <= cutoff
        ]

    def should_reduce_exposure(self) -> bool:
        """Check if exposure should be reduced due to imminent events."""
        return self.is_near_funding(minutes_before=15)
