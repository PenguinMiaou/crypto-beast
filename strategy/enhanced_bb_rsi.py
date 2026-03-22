# strategy/enhanced_bb_rsi.py
"""Enhanced Bollinger Bands + RSI + MACD — optimized for ranging markets."""
from typing import List

import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class EnhancedBbRsi(BaseStrategy):
    name = "enhanced_bb_rsi"

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> List[TradeSignal]:
        if len(klines) < 50:
            return []

        close = klines["close"]
        high = klines["high"]
        low = klines["low"]

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        middle = bb.bollinger_mavg().iloc[-1]
        rsi = ta.momentum.rsi(close, window=14).iloc[-1]
        macd_diff = ta.trend.macd_diff(close)
        macd_hist = macd_diff.iloc[-1]
        macd_hist_prev = macd_diff.iloc[-2]
        adx = ta.trend.adx(high, low, close, window=14).iloc[-1]
        atr = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]
        price = close.iloc[-1]

        # Only trade in non-trending markets
        if adx > 28:
            return []

        signals: List[TradeSignal] = []
        bb_width = upper - lower if upper > lower else 1.0

        # LONG
        long_rsi = rsi < 35
        long_bb = price < (lower + bb_width * 0.25)
        long_macd = macd_hist > macd_hist_prev

        if (long_rsi or long_bb) and long_macd:
            dist_ratio = (price - lower) / bb_width if bb_width > 0 else 0.5
            base_conf = 0.40 + min(0.40, (1.0 - dist_ratio) * 0.5)
            if long_rsi and long_bb:
                base_conf += 0.10
            if regime == MarketRegime.RANGING:
                base_conf += 0.10
            elif regime == MarketRegime.TRENDING_DOWN:
                base_conf -= 0.10
            confidence = min(0.95, max(0.30, base_conf))
            signals.append(TradeSignal(
                symbol=symbol, direction=Direction.LONG, confidence=confidence,
                entry_price=price,
                stop_loss=round(price - 1.5 * atr, 2),
                take_profit=round(upper, 2),
                strategy="enhanced_bb_rsi", regime=regime, timeframe_score=0,
            ))

        # SHORT
        short_rsi = rsi > 65
        short_bb = price > (upper - bb_width * 0.25)
        short_macd = macd_hist < macd_hist_prev

        if (short_rsi or short_bb) and short_macd:
            dist_ratio = (upper - price) / bb_width if bb_width > 0 else 0.5
            base_conf = 0.40 + min(0.40, (1.0 - dist_ratio) * 0.5)
            if short_rsi and short_bb:
                base_conf += 0.10
            if regime == MarketRegime.RANGING:
                base_conf += 0.10
            elif regime == MarketRegime.TRENDING_UP:
                base_conf -= 0.10
            confidence = min(0.95, max(0.30, base_conf))
            signals.append(TradeSignal(
                symbol=symbol, direction=Direction.SHORT, confidence=confidence,
                entry_price=price,
                stop_loss=round(price + 1.5 * atr, 2),
                take_profit=round(lower, 2),
                strategy="enhanced_bb_rsi", regime=regime, timeframe_score=0,
            ))

        return signals
