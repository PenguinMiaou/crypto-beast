"""HarmonicDivergence: Multi-indicator divergence detection strategy.

Faithfully ported from FreqST HarmonicDivergence (16.24% ROI, 63.97% win rate).
Detects bullish/bearish divergence across 11 momentum indicators simultaneously.
"""
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import ta as ta_lib

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class HarmonicDivergence(BaseStrategy):
    name = "harmonic_divergence"

    PIVOT_WINDOW = 5          # bars on each side for pivot detection
    DIVERGENCE_LOOKBACK = 5   # how many previous pivots to check

    # All 11 indicators for divergence detection
    INDICATORS = [
        "rsi", "stoch", "roc", "uo", "ao", "macd",
        "cci", "cmf", "obv", "mfi", "adx",
    ]

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> List[TradeSignal]:
        if len(klines) < 60:  # need enough data for indicators + pivots
            return []

        df = klines.copy()
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # Calculate all 11 indicators
        indicators = self._calculate_indicators(df)

        # Detect pivot points
        pivot_lows, pivot_highs = self._detect_pivots(close)

        # Count divergences across all indicators
        n = len(close)
        total_bullish = np.zeros(n)
        total_bearish = np.zeros(n)

        for ind_name in self.INDICATORS:
            if ind_name not in indicators:
                continue
            ind_values = indicators[ind_name]
            bull_div, bear_div = self._find_divergences(
                close.values, ind_values, pivot_lows, pivot_highs
            )
            for i in range(n):
                if bull_div[i]:
                    # Offset by 30 bars like original (divergence confirmed later)
                    target = max(0, i - 30)
                    total_bullish[target] += 1
                if bear_div[i]:
                    target = max(0, i - 30)
                    total_bearish[target] += 1

        # Keltner Channel for two_bands_check
        ema20 = ta_lib.trend.ema_indicator(close, window=20)
        atr10 = ta_lib.volatility.average_true_range(high, low, close, window=10)
        kc_upper = ema20 + atr10
        kc_lower = ema20 - atr10

        # ATR for SL/TP
        atr14 = ta_lib.volatility.average_true_range(high, low, close, window=14)

        signals: List[TradeSignal] = []
        price = close.iloc[-1]
        prev_idx = n - 2  # previous bar (shift 1)

        if prev_idx < 0:
            return []

        # Two bands check: NOT (low < kc_lower AND high > kc_upper) — extreme volatility filter
        low_val = low.iloc[-1]
        high_val = high.iloc[-1]
        kc_low = kc_lower.iloc[-1]
        kc_up = kc_upper.iloc[-1]
        two_bands_ok = not (low_val < kc_low and high_val > kc_up)

        # Volume check
        vol_ok = volume.iloc[-1] > 0

        atr_val = atr14.iloc[-1]
        if np.isnan(atr_val) or atr_val <= 0:
            atr_val = price * 0.02

        # Buy: bullish divergence on previous bar + two_bands_check + volume
        if total_bullish[prev_idx] > 0 and two_bands_ok and vol_ok:
            num_indicators = int(total_bullish[prev_idx])
            base_conf = 0.35 + min(0.45, num_indicators * 0.08)  # 1 ind→0.43, 5+ ind→0.75

            # Regime adjustment
            if regime == MarketRegime.RANGING:
                base_conf += 0.05   # divergence works well in ranging
            elif regime == MarketRegime.TRENDING_DOWN:
                base_conf += 0.10   # bullish divergence in downtrend = reversal
            elif regime == MarketRegime.TRENDING_UP:
                base_conf -= 0.05   # already trending up, less value

            confidence = min(0.95, max(0.30, base_conf))

            # SL: recent pivot low − ATR (like original custom_stoploss)
            recent_pivot_low = self._find_recent_pivot(pivot_lows, close.values, n - 1, "low")
            sl = round(recent_pivot_low - atr_val, 2) if recent_pivot_low > 0 else round(price * 0.98, 2)

            # TP: recent pivot high + ATR (like original takeprofit)
            recent_pivot_high = self._find_recent_pivot(pivot_highs, close.values, n - 1, "high")
            tp = round(recent_pivot_high + atr_val, 2) if recent_pivot_high > 0 else round(price * 1.02, 2)

            # Ensure SL < entry < TP for LONG
            if sl < price < tp:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    confidence=confidence,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    strategy="harmonic_divergence",
                    regime=regime,
                    timeframe_score=0,
                ))

        # Sell: bearish divergence (mirror logic)
        if total_bearish[prev_idx] > 0 and two_bands_ok and vol_ok:
            num_indicators = int(total_bearish[prev_idx])
            base_conf = 0.35 + min(0.45, num_indicators * 0.08)

            if regime == MarketRegime.RANGING:
                base_conf += 0.05
            elif regime == MarketRegime.TRENDING_UP:
                base_conf += 0.10   # bearish divergence in uptrend = reversal
            elif regime == MarketRegime.TRENDING_DOWN:
                base_conf -= 0.05

            confidence = min(0.95, max(0.30, base_conf))

            recent_pivot_high = self._find_recent_pivot(pivot_highs, close.values, n - 1, "high")
            sl = round(recent_pivot_high + atr_val, 2) if recent_pivot_high > 0 else round(price * 1.02, 2)

            recent_pivot_low = self._find_recent_pivot(pivot_lows, close.values, n - 1, "low")
            tp = round(recent_pivot_low - atr_val, 2) if recent_pivot_low > 0 else round(price * 0.98, 2)

            if tp < price < sl:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    confidence=confidence,
                    entry_price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    strategy="harmonic_divergence",
                    regime=regime,
                    timeframe_score=0,
                ))

        return signals

    # ------------------------------------------------------------------
    # Indicator calculation
    # ------------------------------------------------------------------

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, np.ndarray]:
        """Calculate all 11 momentum indicators."""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        indicators: Dict[str, np.ndarray] = {}

        try:
            indicators["rsi"] = ta_lib.momentum.rsi(close, window=14).values
        except Exception:
            pass

        try:
            indicators["stoch"] = ta_lib.momentum.stoch(
                high, low, close, window=14, smooth_window=3
            ).values
        except Exception:
            pass

        try:
            indicators["roc"] = ta_lib.momentum.roc(close, window=10).values
        except Exception:
            pass

        try:
            indicators["uo"] = ta_lib.momentum.ultimate_oscillator(high, low, close).values
        except Exception:
            pass

        try:
            # Awesome Oscillator: SMA(5) of midpoint − SMA(34) of midpoint
            midpoint = (high + low) / 2
            ao = midpoint.rolling(5).mean() - midpoint.rolling(34).mean()
            indicators["ao"] = ao.values
        except Exception:
            pass

        try:
            indicators["macd"] = ta_lib.trend.macd_diff(close).values
        except Exception:
            pass

        try:
            indicators["cci"] = ta_lib.trend.cci(high, low, close, window=20).values
        except Exception:
            pass

        try:
            # Chaikin Money Flow
            mfv = ((close - low) - (high - close)) / (high - low + 1e-10)
            mfv = mfv * volume
            cmf = mfv.rolling(20).sum() / volume.rolling(20).sum()
            indicators["cmf"] = cmf.values
        except Exception:
            pass

        try:
            # On Balance Volume
            obv = np.zeros(len(close))
            close_arr = close.values
            vol_arr = volume.values
            for i in range(1, len(close_arr)):
                if close_arr[i] > close_arr[i - 1]:
                    obv[i] = obv[i - 1] + vol_arr[i]
                elif close_arr[i] < close_arr[i - 1]:
                    obv[i] = obv[i - 1] - vol_arr[i]
                else:
                    obv[i] = obv[i - 1]
            indicators["obv"] = obv
        except Exception:
            pass

        try:
            indicators["mfi"] = ta_lib.volume.money_flow_index(
                high, low, close, volume, window=14
            ).values
        except Exception:
            pass

        try:
            indicators["adx"] = ta_lib.trend.adx(high, low, close, window=14).values
        except Exception:
            pass

        return indicators

    # ------------------------------------------------------------------
    # Pivot detection
    # ------------------------------------------------------------------

    def _detect_pivots(self, close: pd.Series) -> Tuple[np.ndarray, np.ndarray]:
        """Detect pivot highs and lows using window-based method.

        Pivot low: close is strictly lower than W bars on each side.
        Pivot high: close is strictly higher than W bars on each side.
        """
        n = len(close)
        w = self.PIVOT_WINDOW
        pivot_lows = np.full(n, np.nan)
        pivot_highs = np.full(n, np.nan)
        values = close.values

        for i in range(w, n - w):
            is_low = True
            is_high = True
            for j in range(1, w + 1):
                if values[i] >= values[i - j] or values[i] >= values[i + j]:
                    is_low = False
                if values[i] <= values[i - j] or values[i] <= values[i + j]:
                    is_high = False
                if not is_low and not is_high:
                    break
            if is_low:
                pivot_lows[i] = values[i]
            if is_high:
                pivot_highs[i] = values[i]

        # Check the second-to-last bar (like original, partial right window)
        if n > w + 2:
            i = n - 2
            is_low = True
            is_high = True
            for j in range(1, min(w + 1, i + 1)):
                left = i - j
                if left < 0:
                    break
                if values[i] >= values[left] or values[i] >= values[i + 1]:
                    is_low = False
                if values[i] <= values[left] or values[i] <= values[i + 1]:
                    is_high = False
            if is_low:
                pivot_lows[i] = values[i]
            if is_high:
                pivot_highs[i] = values[i]

        return pivot_lows, pivot_highs

    # ------------------------------------------------------------------
    # Divergence detection
    # ------------------------------------------------------------------

    def _find_divergences(
        self,
        close: np.ndarray,
        indicator: np.ndarray,
        pivot_lows: np.ndarray,
        pivot_highs: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Find bullish and bearish divergences between price and indicator.

        Bullish: price makes lower low but indicator makes higher low (or hidden variant).
        Bearish: price makes higher high but indicator makes lower high (or hidden variant).
        """
        n = len(close)
        bullish = np.zeros(n, dtype=bool)
        bearish = np.zeros(n, dtype=bool)

        # Build sorted pivot index lists
        low_pivots = [i for i in range(n) if not np.isnan(pivot_lows[i])]
        high_pivots = [i for i in range(n) if not np.isnan(pivot_highs[i])]

        # Check bullish divergence at each pivot low
        for idx in range(len(low_pivots)):
            current = low_pivots[idx]
            if np.isnan(indicator[current]):
                continue
            start = max(0, idx - self.DIVERGENCE_LOOKBACK)
            for prev_idx in range(idx - 1, start - 1, -1):
                prev = low_pivots[prev_idx]
                if np.isnan(indicator[prev]):
                    continue
                # Regular bullish: price lower low, indicator higher low
                if close[current] < close[prev] and indicator[current] > indicator[prev]:
                    if self._validate_divergence(close, indicator, prev, current, "bullish"):
                        bullish[current] = True
                        break
                # Hidden bullish: price higher low, indicator lower low
                elif close[current] > close[prev] and indicator[current] < indicator[prev]:
                    if self._validate_divergence(close, indicator, prev, current, "bullish"):
                        bullish[current] = True
                        break

        # Check bearish divergence at each pivot high
        for idx in range(len(high_pivots)):
            current = high_pivots[idx]
            if np.isnan(indicator[current]):
                continue
            start = max(0, idx - self.DIVERGENCE_LOOKBACK)
            for prev_idx in range(idx - 1, start - 1, -1):
                prev = high_pivots[prev_idx]
                if np.isnan(indicator[prev]):
                    continue
                # Regular bearish: price higher high, indicator lower high
                if close[current] > close[prev] and indicator[current] < indicator[prev]:
                    if self._validate_divergence(close, indicator, prev, current, "bearish"):
                        bearish[current] = True
                        break
                # Hidden bearish: price lower high, indicator higher high
                elif close[current] < close[prev] and indicator[current] > indicator[prev]:
                    if self._validate_divergence(close, indicator, prev, current, "bearish"):
                        bearish[current] = True
                        break

        return bullish, bearish

    def _validate_divergence(
        self,
        close: np.ndarray,
        indicator: np.ndarray,
        start: int,
        end: int,
        div_type: str,
    ) -> bool:
        """Validate that the divergence trendline doesn't cross intermediate data.

        For bullish: price & indicator should stay above the interpolated line between pivots.
        For bearish: price & indicator should stay below the interpolated line between pivots.
        """
        length = end - start
        if length <= 1:
            return False

        price_start = close[start]
        price_end = close[end]
        ind_start = indicator[start]
        ind_end = indicator[end]

        for i in range(1, length):
            idx = start + i
            # Interpolate the divergence lines
            price_point = price_start + (price_end - price_start) * i / length
            ind_point = ind_start + (ind_end - ind_start) * i / length

            if div_type == "bullish":
                # Price and indicator should stay above the interpolated line
                if close[idx] < price_point or indicator[idx] < ind_point:
                    return False
            else:
                # Price and indicator should stay below the interpolated line
                if close[idx] > price_point or indicator[idx] > ind_point:
                    return False

        return True

    # ------------------------------------------------------------------
    # Pivot search helper
    # ------------------------------------------------------------------

    def _find_recent_pivot(
        self,
        pivots: np.ndarray,
        close: np.ndarray,
        current_idx: int,
        pivot_type: str,
    ) -> float:
        """Find the most recent pivot value at or before current_idx."""
        for i in range(current_idx - 1, max(0, current_idx - 50) - 1, -1):
            if not np.isnan(pivots[i]):
                return float(pivots[i])
        # Fallback to min/max of recent window
        window = close[max(0, current_idx - 20): current_idx + 1]
        if len(window) == 0:
            return 0.0
        if pivot_type == "low":
            return float(np.min(window))
        else:
            return float(np.max(window))
