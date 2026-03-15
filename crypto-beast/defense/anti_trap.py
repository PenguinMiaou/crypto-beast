"""AntiTrap - False signal filtering for trap detection."""

import pandas as pd
from typing import Optional, List

from core.models import TradeSignal, Direction


class AntiTrap:
    """Filters false/trap signals by analyzing recent candle patterns."""

    def __init__(
        self,
        pin_bar_ratio: float = 2.5,
        volume_spike: float = 3.0,
        pump_threshold: float = 0.03,
    ):
        self.pin_bar_ratio = pin_bar_ratio
        self.volume_spike = volume_spike
        self.pump_threshold = pump_threshold

    def is_trap(self, signal: TradeSignal, klines: pd.DataFrame) -> bool:
        """Return True if signal looks like a trap (should be rejected).

        Checks for pin bars, volume divergence, and pump patterns.
        """
        if len(klines) < 3:
            return False

        if self._detect_pin_bar(klines, signal.direction):
            return True

        if self._detect_volume_divergence(klines, signal.direction):
            return True

        if self._detect_pump(klines):
            return True

        return False

    def _detect_pin_bar(self, klines: pd.DataFrame, direction: Direction) -> bool:
        """Detect pin bar (long wick relative to body).

        For LONG signals: a long upper wick suggests rejection at highs (bull trap).
        For SHORT signals: a long lower wick suggests rejection at lows (bear trap).
        """
        last = klines.iloc[-1]
        open_price = last["open"]
        close_price = last["close"]
        high = last["high"]
        low = last["low"]

        body = abs(close_price - open_price)
        if body == 0:
            body = 1e-10  # avoid division by zero

        if direction == Direction.LONG:
            # Upper wick: high - max(open, close)
            upper_wick = high - max(open_price, close_price)
            if upper_wick > self.pin_bar_ratio * body:
                return True
        else:
            # Lower wick: min(open, close) - low
            lower_wick = min(open_price, close_price) - low
            if lower_wick > self.pin_bar_ratio * body:
                return True

        return False

    def _detect_volume_divergence(
        self, klines: pd.DataFrame, direction: Direction
    ) -> bool:
        """Price moves in direction but volume decreasing (bearish divergence).

        Last 3 candles: price moving in signal direction but volume declining.
        """
        if len(klines) < 3:
            return False

        last_3 = klines.iloc[-3:]
        closes = last_3["close"].values
        volumes = last_3["volume"].values

        if direction == Direction.LONG:
            # Price should be going up
            price_up = closes[-1] > closes[0]
            # Volume should be declining
            vol_declining = volumes[-1] < volumes[-2] < volumes[-3]
            if price_up and vol_declining:
                return True
        else:
            # Price should be going down
            price_down = closes[-1] < closes[0]
            vol_declining = volumes[-1] < volumes[-2] < volumes[-3]
            if price_down and vol_declining:
                return True

        return False

    def _detect_pump(self, klines: pd.DataFrame) -> bool:
        """Sudden price spike (possible manipulation).

        Last candle change > pump_threshold (default 3%).
        """
        last = klines.iloc[-1]
        open_price = last["open"]
        close_price = last["close"]

        if open_price == 0:
            return False

        change = abs(close_price - open_price) / open_price
        return change > self.pump_threshold
