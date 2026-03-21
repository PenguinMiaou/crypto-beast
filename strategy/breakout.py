# strategy/breakout.py
import numpy as np
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class Breakout(BaseStrategy):
    name = "breakout"

    def __init__(self, bb_window: int = 20, bb_dev: int = 2, squeeze_lookback: int = 120, squeeze_pct: float = 20.0, vol_mult: float = 1.5):
        self.bb_window = bb_window
        self.bb_dev = bb_dev
        self.squeeze_lookback = squeeze_lookback
        self.squeeze_pct = squeeze_pct
        self.vol_mult = vol_mult

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < self.squeeze_lookback + 5:
            return []

        df = klines.copy()
        bb = ta.volatility.BollingerBands(df["close"], window=self.bb_window, window_dev=self.bb_dev)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_width"] = df["bb_upper"] - df["bb_lower"]
        df["vol_sma"] = df["volume"].rolling(window=20).mean()
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14)

        signals = []
        last = df.iloc[-1]

        if pd.isna(last["bb_upper"]) or pd.isna(last["vol_sma"]):
            return []

        # BB squeeze detection: check if the minimum BB width in a recent
        # pre-breakout window is below the 20th percentile of the full lookback.
        # This catches squeezes that are now expanding into a breakout.
        lookback_widths = df["bb_width"].iloc[-self.squeeze_lookback:]
        if lookback_widths.isna().any():
            return []

        # Use min width in the 10 candles before the last candle as the squeeze reference
        pre_breakout_widths = df["bb_width"].iloc[-11:-1]
        min_recent_width = pre_breakout_widths.min()
        threshold = np.percentile(lookback_widths.values, self.squeeze_pct)

        is_squeeze = min_recent_width <= threshold

        if not is_squeeze:
            return []

        price = last["close"]
        upper = last["bb_upper"]
        lower = last["bb_lower"]
        atr = last["atr"] if not pd.isna(last["atr"]) else (upper - lower) / 4
        vol_avg = last["vol_sma"]
        volume_ratio = last["volume"] / vol_avg if vol_avg > 0 else 0

        # Volume must exceed threshold
        if volume_ratio < self.vol_mult:
            return []

        # LONG breakout: close above upper band
        if price > upper:
            # Dynamic confidence based on volume ratio strength
            base_conf = 0.40 + min(0.40, (volume_ratio - 1.0) * 0.15)
            if is_squeeze:
                base_conf += 0.1
            confidence = min(0.95, max(0.3, base_conf))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.LONG,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price - 2.0 * atr, 2),
                take_profit=round(price + (price - lower), 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        # SHORT breakout: close below lower band
        elif price < lower:
            # Dynamic confidence based on volume ratio strength
            base_conf = 0.40 + min(0.40, (volume_ratio - 1.0) * 0.15)
            if is_squeeze:
                base_conf += 0.1
            confidence = min(0.95, max(0.3, base_conf))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.SHORT,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price + 2.0 * atr, 2),
                take_profit=round(price - (upper - price), 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        return signals
