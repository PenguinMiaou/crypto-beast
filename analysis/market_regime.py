"""Market regime detection using ADX, EMA alignment, and Bollinger Band width."""

import numpy as np
import pandas as pd
import ta
from typing import Optional

from core.models import MarketRegime


class MarketRegimeDetector:
    """Detects the current market regime from OHLCV kline data."""

    def __init__(
        self,
        adx_period: int = 14,
        ema_fast: int = 20,
        ema_slow: int = 50,
        bb_period: int = 20,
        adx_trending_threshold: float = 25.0,
        adx_ranging_threshold: float = 20.0,
        bb_high_pct: float = 90.0,
        bb_low_pct: float = 10.0,
    ):
        self.adx_period = adx_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.bb_period = bb_period
        self.adx_trending_threshold = adx_trending_threshold
        self.adx_ranging_threshold = adx_ranging_threshold
        self.bb_high_pct = bb_high_pct
        self.bb_low_pct = bb_low_pct

    def detect(self, klines: pd.DataFrame) -> MarketRegime:
        """Detect market regime from OHLCV data.

        Args:
            klines: DataFrame with columns: open, high, low, close, volume

        Returns:
            MarketRegime enum value.
        """
        close = klines["close"]
        high = klines["high"]
        low = klines["low"]

        # ADX
        adx_indicator = ta.trend.ADXIndicator(
            high=high, low=low, close=close, window=self.adx_period
        )
        adx_values = adx_indicator.adx()
        adx = adx_values.iloc[-1]

        # EMA 20 / 50
        ema_fast = ta.trend.EMAIndicator(close=close, window=self.ema_fast).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(close=close, window=self.ema_slow).ema_indicator()
        ema_fast_last = ema_fast.iloc[-1]
        ema_slow_last = ema_slow.iloc[-1]

        # Trend detection via ADX + EMA alignment (checked first)
        if not np.isnan(adx) and adx > self.adx_trending_threshold:
            if ema_fast_last > ema_slow_last:
                return MarketRegime.TRENDING_UP
            else:
                return MarketRegime.TRENDING_DOWN

        # Ranging when ADX is clearly low
        if not np.isnan(adx) and adx < self.adx_ranging_threshold:
            return MarketRegime.RANGING

        # Bollinger Band width for volatility regimes (ADX between 20-25)
        bb = ta.volatility.BollingerBands(close=close, window=self.bb_period)
        bb_width = bb.bollinger_wband()
        bb_width_clean = bb_width.dropna()

        if len(bb_width_clean) > 0:
            current_width = bb_width_clean.iloc[-1]
            pct_high = np.percentile(bb_width_clean, self.bb_high_pct)
            pct_low = np.percentile(bb_width_clean, self.bb_low_pct)

            if current_width > pct_high:
                return MarketRegime.HIGH_VOLATILITY
            if current_width < pct_low:
                return MarketRegime.LOW_VOLATILITY

        # Default: ranging
        return MarketRegime.RANGING
