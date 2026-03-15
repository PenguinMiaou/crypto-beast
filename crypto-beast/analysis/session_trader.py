"""Session-based strategy weighting for different trading sessions."""

from datetime import datetime, timezone
from typing import Optional, Dict


# Trading session definitions by UTC hour ranges
SESSIONS = {
    "ASIA": (0, 8),
    "EUROPE": (8, 13),
    "US_OVERLAP": (13, 17),
    "US": (17, 21),
    "OFF_HOURS": (21, 24),
}

# Strategy weight multipliers per session
SESSION_WEIGHTS: Dict[str, Dict[str, float]] = {
    "ASIA": {
        "trend_follower": 0.8,
        "momentum": 0.7,
        "breakout": 0.6,
        "mean_reversion": 1.3,
        "scalper": 1.2,
    },
    "EUROPE": {
        "trend_follower": 1.0,
        "momentum": 1.0,
        "breakout": 1.0,
        "mean_reversion": 1.0,
        "scalper": 1.0,
    },
    "US_OVERLAP": {
        "trend_follower": 1.2,
        "momentum": 1.3,
        "breakout": 1.2,
        "mean_reversion": 0.7,
        "scalper": 1.0,
    },
    "US": {
        "trend_follower": 1.1,
        "momentum": 1.1,
        "breakout": 1.0,
        "mean_reversion": 0.9,
        "scalper": 0.9,
    },
    "OFF_HOURS": {
        "trend_follower": 0.7,
        "momentum": 0.6,
        "breakout": 0.5,
        "mean_reversion": 1.2,
        "scalper": 1.3,
    },
}


class SessionTrader:
    """Adjusts strategy weights based on the current trading session."""

    def get_session_for_hour(self, utc_hour: int) -> str:
        """Return session name for a specific UTC hour.

        Args:
            utc_hour: Hour in UTC (0-23).

        Returns:
            Session name string.
        """
        for session_name, (start, end) in SESSIONS.items():
            if start <= utc_hour < end:
                return session_name
        return "OFF_HOURS"

    def get_current_session(self) -> str:
        """Return current trading session name based on UTC hour."""
        utc_hour = datetime.now(timezone.utc).hour
        return self.get_session_for_hour(utc_hour)

    def get_strategy_weights(self) -> Dict[str, float]:
        """Return strategy weight multipliers for current session."""
        session = self.get_current_session()
        return SESSION_WEIGHTS[session].copy()
