"""Market regime detection using ADX, EMA alignment, and Bollinger Band width."""

import numpy as np
import pandas as pd
import ta
from typing import Dict, Optional

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

        # Per-symbol state for transition detection
        self._last_regime: Dict[str, MarketRegime] = {}
        self._regime_change_bar: Dict[str, int] = {}
        self._transition_cooldown: int = 6  # 6 bars (30min on 5m TF)

    def detect(self, klines: pd.DataFrame, symbol: str = "") -> MarketRegime:
        """Detect market regime from OHLCV data.

        Args:
            klines: DataFrame with columns: open, high, low, close, volume
            symbol: Symbol identifier used for per-symbol transition tracking.

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

        # === Determine raw regime (store instead of returning immediately) ===
        raw_regime = MarketRegime.RANGING  # default

        if not np.isnan(adx) and adx > self.adx_trending_threshold:
            if ema_fast_last > ema_slow_last:
                raw_regime = MarketRegime.TRENDING_UP
            else:
                raw_regime = MarketRegime.TRENDING_DOWN
        elif not np.isnan(adx) and adx < self.adx_ranging_threshold:
            raw_regime = MarketRegime.RANGING
        else:
            # Bollinger Band width for volatility regimes (ADX between 20-25)
            bb = ta.volatility.BollingerBands(close=close, window=self.bb_period)
            bb_width = bb.bollinger_wband()
            bb_width_clean = bb_width.dropna()

            if len(bb_width_clean) > 0:
                current_width = bb_width_clean.iloc[-1]
                pct_high = np.percentile(bb_width_clean, self.bb_high_pct)
                pct_low = np.percentile(bb_width_clean, self.bb_low_pct)

                if current_width > pct_high:
                    raw_regime = MarketRegime.HIGH_VOLATILITY
                elif current_width < pct_low:
                    raw_regime = MarketRegime.LOW_VOLATILITY
                # else remains RANGING

        # === Transition Detection (added for v1.7) ===

        # 1. ADX rapid drop = regime transitioning
        adx_series = adx_indicator.adx()
        if len(adx_series) > 3:
            adx_3_ago = adx_series.iloc[-4]
            if not np.isnan(adx_3_ago):
                adx_drop = adx_3_ago - adx
                if adx_drop > 8:
                    self._last_regime[symbol] = raw_regime
                    return MarketRegime.TRANSITIONING

        # 2. RSI/Price divergence detection
        rsi_series = ta.momentum.rsi(close, window=14)
        if len(close) > 10 and len(rsi_series) > 10:
            rsi_now = rsi_series.iloc[-1]
            rsi_5ago = rsi_series.iloc[-6]
            price_now = close.iloc[-1]
            price_5ago = close.iloc[-6]
            if not (np.isnan(rsi_now) or np.isnan(rsi_5ago)):
                # Require meaningful divergence, not noise
                price_change_pct = abs(price_now - price_5ago) / price_5ago if price_5ago > 0 else 0
                rsi_change = abs(rsi_now - rsi_5ago)
                if price_change_pct > 0.005 and rsi_change > 5:
                    # Bullish divergence: price lower but RSI higher
                    if price_now < price_5ago and rsi_now > rsi_5ago:
                        self._last_regime[symbol] = raw_regime
                        return MarketRegime.TRANSITIONING
                    # Bearish divergence: price higher but RSI lower
                    if price_now > price_5ago and rsi_now < rsi_5ago:
                        self._last_regime[symbol] = raw_regime
                        return MarketRegime.TRANSITIONING

        # 3. Per-symbol regime change cooldown
        if symbol:
            last = self._last_regime.get(symbol)
            if last is not None and raw_regime != last:
                # Regime just changed — record the change bar and signal TRANSITIONING
                self._last_regime[symbol] = raw_regime
                self._regime_change_bar[symbol] = len(klines)
                return MarketRegime.TRANSITIONING

            # Update last known regime
            self._last_regime[symbol] = raw_regime

            # Still within cooldown window after a recent regime change
            change_bar = self._regime_change_bar.get(symbol, 0)
            if change_bar > 0 and (len(klines) - change_bar) < self._transition_cooldown:
                return MarketRegime.TRANSITIONING

        return raw_regime
