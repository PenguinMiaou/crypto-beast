# strategy/scalper.py
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class Scalper(BaseStrategy):
    name = "scalper"

    def __init__(self, rsi_window: int = 2, atr_window: int = 14):
        self.rsi_window = rsi_window
        self.atr_window = atr_window

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < self.atr_window + 5:
            return []

        df = klines.copy()
        df["rsi2"] = ta.momentum.RSIIndicator(df["close"], window=self.rsi_window).rsi()
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=self.atr_window)

        signals = []
        last = df.iloc[-1]

        if pd.isna(last["rsi2"]) or pd.isna(last["atr"]):
            return []

        price = last["close"]
        rsi2 = last["rsi2"]
        atr = last["atr"]

        # LONG: RSI(2) < 10
        if rsi2 < 10:
            # Dynamic confidence: more extreme RSI = higher confidence
            rsi_extreme_distance = min(abs(rsi2), abs(100 - rsi2))
            base_conf = 0.35 + min(0.35, (50 - rsi_extreme_distance) / 50 * 0.35)
            regime_adj = 0.1 if regime == MarketRegime.RANGING else 0.0
            confidence = min(0.95, max(0.3, base_conf + regime_adj))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.LONG,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price - 0.3 * atr, 2),
                take_profit=round(price + 1.5 * atr, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        # SHORT: RSI(2) > 90
        elif rsi2 > 90:
            # Dynamic confidence: more extreme RSI = higher confidence
            rsi_extreme_distance = min(abs(rsi2), abs(100 - rsi2))
            base_conf = 0.35 + min(0.35, (50 - rsi_extreme_distance) / 50 * 0.35)
            regime_adj = 0.1 if regime == MarketRegime.RANGING else 0.0
            confidence = min(0.95, max(0.3, base_conf + regime_adj))

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.SHORT,
                confidence=round(confidence, 3),
                entry_price=price,
                stop_loss=round(price + 0.3 * atr, 2),
                take_profit=round(price - 1.5 * atr, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        return signals
