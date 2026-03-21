# strategy/mean_reversion.py
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class MeanReversion(BaseStrategy):
    name = "mean_reversion"

    def __init__(self, bb_window: int = 20, bb_dev: int = 2, rsi_window: int = 14):
        self.bb_window = bb_window
        self.bb_dev = bb_dev
        self.rsi_window = rsi_window

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < self.bb_window + 5:
            return []

        df = klines.copy()
        bb = ta.volatility.BollingerBands(df["close"], window=self.bb_window, window_dev=self.bb_dev)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_middle"] = bb.bollinger_mavg()
        df["bb_lower"] = bb.bollinger_lband()
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=self.rsi_window).rsi()

        signals = []
        last = df.iloc[-1]

        if pd.isna(last["bb_upper"]) or pd.isna(last["rsi"]):
            return []

        price = last["close"]
        upper = last["bb_upper"]
        middle = last["bb_middle"]
        lower = last["bb_lower"]
        rsi = last["rsi"]
        bb_width = upper - lower

        # LONG: close < lower_band AND RSI < 30
        if price < lower and rsi < 30:
            confidence = 0.6
            if regime == MarketRegime.RANGING:
                confidence += 0.1
            elif regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
                confidence -= 0.2

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.LONG,
                confidence=round(max(0.1, confidence), 3),
                entry_price=price,
                stop_loss=round(lower - 0.5 * bb_width, 2),
                take_profit=round(upper, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        # SHORT: close > upper_band AND RSI > 70
        elif price > upper and rsi > 70:
            confidence = 0.6
            if regime == MarketRegime.RANGING:
                confidence += 0.1
            elif regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN):
                confidence -= 0.2

            signals.append(TradeSignal(
                symbol=symbol,
                direction=Direction.SHORT,
                confidence=round(max(0.1, confidence), 3),
                entry_price=price,
                stop_loss=round(upper + 0.5 * bb_width, 2),
                take_profit=round(lower, 2),
                strategy=self.name,
                regime=regime,
                timeframe_score=0,
            ))

        return signals
