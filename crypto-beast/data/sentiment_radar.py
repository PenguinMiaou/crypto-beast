"""Sentiment Radar - Contrarian signals from Fear & Greed and Long/Short ratio."""

from typing import Optional

from core.models import DirectionalBias, SignalType


class SentimentRadar:
    UPDATE_INTERVAL = 300  # 5 min

    def __init__(self):
        self._fear_greed: Optional[int] = None  # 0-100
        self._long_short_ratio: Optional[float] = None

    def update_fear_greed(self, value: int) -> None:
        """Update Fear & Greed index (0=extreme fear, 100=extreme greed)."""
        self._fear_greed = max(0, min(100, value))

    def update_long_short_ratio(self, ratio: float) -> None:
        """Update long/short account ratio."""
        self._long_short_ratio = ratio

    def get_signal(self, symbol: str = "BTCUSDT") -> DirectionalBias:
        """Contrarian signal from sentiment data."""
        if self._fear_greed is None:
            return DirectionalBias(
                source="sentiment_radar", symbol=symbol,
                direction=SignalType.NEUTRAL, confidence=0.0,
                reason="No data",
            )

        fg = self._fear_greed
        # F&G component (contrarian): extreme fear = buy, extreme greed = sell
        fg_score = 0.0
        if fg < 20:
            fg_score = 0.7 * (20 - fg) / 20  # max 0.7
            fg_direction = SignalType.BULLISH
        elif fg > 80:
            fg_score = 0.7 * (fg - 80) / 20
            fg_direction = SignalType.BEARISH
        else:
            fg_score = 0.0
            fg_direction = SignalType.NEUTRAL

        # L/S ratio component
        ls_score = 0.0
        ls_direction = SignalType.NEUTRAL
        if self._long_short_ratio is not None:
            if self._long_short_ratio > 2.0:  # Too many longs = bearish
                ls_score = min(0.5, (self._long_short_ratio - 2.0) * 0.25)
                ls_direction = SignalType.BEARISH
            elif self._long_short_ratio < 0.5:  # Too many shorts = bullish
                ls_score = min(0.5, (0.5 - self._long_short_ratio) * 0.5)
                ls_direction = SignalType.BULLISH

        # Combine: 60% F&G, 40% L/S
        combined_score = fg_score * 0.6 + ls_score * 0.4

        # Determine direction
        if fg_direction != SignalType.NEUTRAL:
            direction = fg_direction
        elif ls_direction != SignalType.NEUTRAL:
            direction = ls_direction
        else:
            direction = SignalType.NEUTRAL

        reason = f"F&G={fg}"
        if self._long_short_ratio:
            reason += f", L/S={self._long_short_ratio:.2f}"

        return DirectionalBias(
            source="sentiment_radar", symbol=symbol,
            direction=direction, confidence=round(combined_score, 2),
            reason=reason,
        )
