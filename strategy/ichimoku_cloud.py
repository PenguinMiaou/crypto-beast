# strategy/ichimoku_cloud.py
"""Ichimoku Cloud trend strategy based on FreqST ichiV1."""
from typing import List

import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class IchimokuCloud(BaseStrategy):
    name = "ichimoku_cloud"

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> List[TradeSignal]:
        if len(klines) < 60:
            return []

        close = klines["close"]
        high = klines["high"]
        low = klines["low"]

        ichi = ta.trend.IchimokuIndicator(high, low, window1=9, window2=26, window3=52)
        tenkan = ichi.ichimoku_conversion_line()
        kijun = ichi.ichimoku_base_line()
        senkou_a = ichi.ichimoku_a()
        senkou_b = ichi.ichimoku_b()

        atr = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]
        price = close.iloc[-1]

        t = tenkan.iloc[-1]
        k = kijun.iloc[-1]
        t_prev = tenkan.iloc[-2]
        k_prev = kijun.iloc[-2]
        sa = senkou_a.iloc[-1]
        sb = senkou_b.iloc[-1]
        cloud_top = max(sa, sb)
        cloud_bottom = min(sa, sb)
        cloud_thickness = abs(sa - sb) / price if price > 0 else 0

        signals: List[TradeSignal] = []

        # LONG: Tenkan crosses above Kijun + price above cloud
        if t > k and t_prev <= k_prev and price > cloud_top:
            dist_from_cloud = (price - cloud_top) / price
            base_conf = 0.40 + min(0.35, cloud_thickness * 50) + min(0.15, dist_from_cloud * 20)
            if regime == MarketRegime.TRENDING_UP:
                base_conf += 0.10
            elif regime == MarketRegime.RANGING:
                base_conf -= 0.15
            elif regime == MarketRegime.TRENDING_DOWN:
                base_conf -= 0.10
            confidence = min(0.95, max(0.30, base_conf))
            signals.append(TradeSignal(
                symbol=symbol, direction=Direction.LONG, confidence=confidence,
                entry_price=price,
                stop_loss=round(max(cloud_bottom, price - 2.0 * atr), 2),
                take_profit=round(price + 3.0 * atr, 2),
                strategy="ichimoku_cloud", regime=regime, timeframe_score=0,
            ))

        # SHORT: Tenkan crosses below Kijun + price below cloud
        elif t < k and t_prev >= k_prev and price < cloud_bottom:
            dist_from_cloud = (cloud_bottom - price) / price
            base_conf = 0.40 + min(0.35, cloud_thickness * 50) + min(0.15, dist_from_cloud * 20)
            if regime == MarketRegime.TRENDING_DOWN:
                base_conf += 0.10
            elif regime == MarketRegime.RANGING:
                base_conf -= 0.15
            elif regime == MarketRegime.TRENDING_UP:
                base_conf -= 0.10
            confidence = min(0.95, max(0.30, base_conf))
            signals.append(TradeSignal(
                symbol=symbol, direction=Direction.SHORT, confidence=confidence,
                entry_price=price,
                stop_loss=round(min(cloud_top, price + 2.0 * atr), 2),
                take_profit=round(price - 3.0 * atr, 2),
                strategy="ichimoku_cloud", regime=regime, timeframe_score=0,
            ))

        return signals
