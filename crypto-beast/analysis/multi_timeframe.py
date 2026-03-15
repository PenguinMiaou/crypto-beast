"""Multi-timeframe confluence scoring module."""

import logging
from typing import Optional, Dict

import pandas as pd
import ta

from core.models import ConfluenceScore, SignalType

logger = logging.getLogger(__name__)


class MultiTimeframe:
    """Calculate confluence scores across multiple timeframes.

    Uses EMA9/EMA21 crossover on each timeframe with weighted voting
    to produce a single confluence score from -10 to +10.
    """

    def __init__(self) -> None:
        self._timeframe_weights: Dict[str, int] = {
            "4h": 4,
            "1h": 3,
            "15m": 2,
            "5m": 1,
        }
        self._confluences: Dict[str, ConfluenceScore] = {}

    def update(self, symbol: str, klines_by_tf: Dict[str, pd.DataFrame]) -> ConfluenceScore:
        """Calculate confluence score from multiple timeframe klines.

        Args:
            symbol: Trading pair symbol (e.g. "BTCUSDT").
            klines_by_tf: Mapping of timeframe label to OHLCV DataFrame.
                Each DataFrame must have a "close" column.

        Returns:
            ConfluenceScore with weighted vote tally.
        """
        breakdown: Dict[str, int] = {}
        weighted_sum = 0

        for tf, weight in self._timeframe_weights.items():
            df = klines_by_tf.get(tf)
            if df is None or df.empty:
                continue

            vote = self._vote(df)
            breakdown[tf] = vote
            weighted_sum += vote * weight

        # Clamp to [-10, +10]
        score = max(-10, min(10, weighted_sum))

        if score > 0:
            direction = SignalType.BULLISH
        elif score < 0:
            direction = SignalType.BEARISH
        else:
            direction = SignalType.NEUTRAL

        result = ConfluenceScore(
            symbol=symbol,
            score=score,
            direction=direction,
            breakdown=breakdown,
        )
        self._confluences[symbol] = result
        return result

    def get_confluence(self, symbol: str) -> Optional[ConfluenceScore]:
        """Get cached confluence score for symbol."""
        return self._confluences.get(symbol)

    def filter_signal(self, symbol: str, direction: SignalType) -> bool:
        """Return True if signal direction aligns with confluence.

        A signal passes only when:
        - A cached confluence exists for the symbol
        - |score| >= 6
        - The confluence direction matches the requested direction
        """
        conf = self._confluences.get(symbol)
        if conf is None:
            return False
        if abs(conf.score) < 6:
            return False
        return conf.direction == direction

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _vote(df: pd.DataFrame) -> int:
        """Return +1 if EMA9 > EMA21 on latest bar, else -1."""
        close = df["close"]
        ema9 = ta.trend.ema_indicator(close, window=9)
        ema21 = ta.trend.ema_indicator(close, window=21)
        latest_ema9 = ema9.iloc[-1]
        latest_ema21 = ema21.iloc[-1]
        return 1 if latest_ema9 > latest_ema21 else -1
