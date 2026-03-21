# strategy/momentum.py
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class Momentum(BaseStrategy):
    name = "momentum"

    def __init__(self, ema_window: int = 20, vol_sma_window: int = 20):
        self.ema_window = ema_window
        self.vol_sma_window = vol_sma_window

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < 35:
            return []

        df = klines.copy()
        macd = ta.trend.MACD(df["close"])
        df["macd_hist"] = macd.macd_diff()
        df["ema20"] = ta.trend.ema_indicator(df["close"], window=self.ema_window)
        df["vol_sma"] = df["volume"].rolling(window=self.vol_sma_window).mean()

        signals = []
        last = df.iloc[-1]

        if pd.isna(last["macd_hist"]) or pd.isna(last["ema20"]) or pd.isna(last["vol_sma"]):
            return []

        # Need at least 3 histogram values for trend check
        hist_vals = df["macd_hist"].iloc[-3:]
        if hist_vals.isna().any():
            return []

        h1, h2, h3 = hist_vals.iloc[0], hist_vals.iloc[1], hist_vals.iloc[2]
        price = last["close"]
        ema20 = last["ema20"]
        atr = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=14).iloc[-1]
        if pd.isna(atr):
            return []

        volume_ratio = last["volume"] / last["vol_sma"] if last["vol_sma"] > 0 else 0

        # LONG: MACD hist > 0 and increasing and close > EMA20
        if h3 > 0 and h3 > h2 > h1 and price > ema20:
            # Dynamic confidence based on MACD histogram strength relative to ATR
            hist_strength = abs(h3) / atr if atr > 0 else 0
            base_conf = 0.35 + min(0.45, hist_strength * 8)
            regime_adj = 0.0
            if regime == MarketRegime.TRENDING_UP:
                regime_adj += 0.1
            volume_adj = 0.15 if volume_ratio > 1.2 else 0.0
            confidence = min(0.95, max(0.3, base_conf + regime_adj + volume_adj))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.LONG,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price - atr * 1.5, 2),
                take_profit=round(price + atr * 3.0, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        # SHORT: MACD hist < 0 and decreasing and close < EMA20
        elif h3 < 0 and h3 < h2 < h1 and price < ema20:
            # Dynamic confidence based on MACD histogram strength relative to ATR
            hist_strength = abs(h3) / atr if atr > 0 else 0
            base_conf = 0.35 + min(0.45, hist_strength * 8)
            regime_adj = 0.0
            if regime == MarketRegime.TRENDING_DOWN:
                regime_adj += 0.1
            volume_adj = 0.15 if volume_ratio > 1.2 else 0.0
            confidence = min(0.95, max(0.3, base_conf + regime_adj + volume_adj))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.SHORT,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price + atr * 1.5, 2),
                take_profit=round(price - atr * 3.0, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        return signals
