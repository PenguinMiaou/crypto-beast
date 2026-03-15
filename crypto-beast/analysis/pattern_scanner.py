"""PatternScanner: Detect basic chart patterns from OHLCV data."""

from datetime import datetime
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

from core.models import Pattern, Direction


class PatternScanner:
    """Detect chart patterns from OHLCV data."""

    def __init__(self, lookback: int = 50) -> None:
        self.lookback = lookback

    def scan(
        self, klines: pd.DataFrame, symbol: str, timeframe: str = "5m"
    ) -> List[Pattern]:
        """Scan for patterns in OHLCV data."""
        patterns: List[Pattern] = []
        if len(klines) < self.lookback:
            return patterns

        window = klines.tail(self.lookback)

        # Check support/resistance
        sr = self._find_support_resistance(window)

        # Check double bottom
        db = self._detect_double_bottom(window, symbol, timeframe)
        if db:
            patterns.append(db)

        # Check double top
        dt = self._detect_double_top(window, symbol, timeframe)
        if dt:
            patterns.append(dt)

        return patterns

    def _find_support_resistance(
        self, data: pd.DataFrame
    ) -> Dict[str, List[float]]:
        """Find support and resistance levels using pivot points."""
        highs = data["high"].values
        lows = data["low"].values

        resistance: List[float] = []
        support: List[float] = []

        for i in range(2, len(highs) - 2):
            if (
                highs[i] > highs[i - 1]
                and highs[i] > highs[i - 2]
                and highs[i] > highs[i + 1]
                and highs[i] > highs[i + 2]
            ):
                resistance.append(float(highs[i]))
            if (
                lows[i] < lows[i - 1]
                and lows[i] < lows[i - 2]
                and lows[i] < lows[i + 1]
                and lows[i] < lows[i + 2]
            ):
                support.append(float(lows[i]))

        return {"resistance": resistance, "support": support}

    def _detect_double_bottom(
        self, data: pd.DataFrame, symbol: str, timeframe: str
    ) -> Optional[Pattern]:
        """Detect double bottom pattern (W shape)."""
        lows = data["low"].values
        close = data["close"].values

        # Find two lowest points in first and second half
        mid = len(lows) // 2
        first_low_idx = np.argmin(lows[:mid])
        second_low_idx = mid + np.argmin(lows[mid:])

        first_low = lows[first_low_idx]
        second_low = lows[second_low_idx]

        # Double bottom: two lows within 2% of each other, price now above
        # the high between them. Require meaningful price swing (> 0.5%).
        if abs(first_low - second_low) / first_low < 0.02:
            neckline = float(
                np.max(data["high"].values[first_low_idx:second_low_idx])
            )
            swing_pct = (neckline - first_low) / first_low
            if swing_pct > 0.005 and close[-1] > neckline * 0.98:
                target = neckline + (neckline - first_low)  # Measured move
                return Pattern(
                    name="double_bottom",
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.LONG,
                    target_price=round(target, 2),
                    stop_price=round(min(first_low, second_low) * 0.99, 2),
                    confidence=0.65,
                )
        return None

    def _detect_double_top(
        self, data: pd.DataFrame, symbol: str, timeframe: str
    ) -> Optional[Pattern]:
        """Detect double top pattern (M shape)."""
        highs = data["high"].values
        close = data["close"].values

        mid = len(highs) // 2
        first_high_idx = np.argmax(highs[:mid])
        second_high_idx = mid + np.argmax(highs[mid:])

        first_high = highs[first_high_idx]
        second_high = highs[second_high_idx]

        if abs(first_high - second_high) / first_high < 0.02:
            neckline = float(
                np.min(data["low"].values[first_high_idx:second_high_idx])
            )
            swing_pct = (first_high - neckline) / first_high
            if swing_pct > 0.005 and close[-1] < neckline * 1.02:
                target = neckline - (first_high - neckline)
                return Pattern(
                    name="double_top",
                    symbol=symbol,
                    timeframe=timeframe,
                    direction=Direction.SHORT,
                    target_price=round(target, 2),
                    stop_price=round(
                        max(first_high, second_high) * 1.01, 2
                    ),
                    confidence=0.65,
                )
        return None
