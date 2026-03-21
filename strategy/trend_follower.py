# strategy/trend_follower.py
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class TrendFollower(BaseStrategy):
    name = "trend_follower"

    def __init__(self, fast_ema: int = 9, slow_ema: int = 21, atr_period: int = 14, atr_sl_mult: float = 1.5, atr_tp_mult: float = 3.0):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < self.slow_ema + 5:
            return []

        df = klines.copy()
        df["ema_fast"] = ta.trend.ema_indicator(df["close"], window=self.fast_ema)
        df["ema_slow"] = ta.trend.ema_indicator(df["close"], window=self.slow_ema)
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=self.atr_period)

        signals = []
        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["ema_fast"]) or pd.isna(last["ema_slow"]) or pd.isna(last["atr"]):
            return []

        atr = last["atr"]
        price = last["close"]

        # Bullish crossover or fast above slow
        if last["ema_fast"] > last["ema_slow"]:
            # Dynamic confidence based on EMA spread percentage
            spread_pct = (last["ema_fast"] - last["ema_slow"]) / price
            base_conf = 0.35 + min(0.45, spread_pct * 100)
            regime_adj = 0.0
            if regime == MarketRegime.TRENDING_UP:
                regime_adj = 0.1
            elif regime in (MarketRegime.RANGING, MarketRegime.TRENDING_DOWN):
                regime_adj = -0.15
            confidence = min(0.95, max(0.3, base_conf + regime_adj))

            if confidence >= 0.3:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    confidence=round(confidence, 3),
                    entry_price=price,
                    stop_loss=round(price - atr * self.atr_sl_mult, 2),
                    take_profit=round(price + atr * self.atr_tp_mult, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                ))

        # Bearish: fast below slow
        elif last["ema_fast"] < last["ema_slow"]:
            spread_pct = (last["ema_slow"] - last["ema_fast"]) / price
            base_conf = 0.35 + min(0.45, spread_pct * 100)
            regime_adj = 0.0
            if regime == MarketRegime.TRENDING_DOWN:
                regime_adj = 0.1
            elif regime in (MarketRegime.RANGING, MarketRegime.TRENDING_UP):
                regime_adj = -0.15
            confidence = min(0.95, max(0.3, base_conf + regime_adj))

            if confidence >= 0.3:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    confidence=round(confidence, 3),
                    entry_price=price,
                    stop_loss=round(price + atr * self.atr_sl_mult, 2),
                    take_profit=round(price - atr * self.atr_tp_mult, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                ))

        return signals
