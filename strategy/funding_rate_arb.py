"""FundingRateArb: Use extreme funding rates as a trading signal."""

from typing import Optional, Dict, List

import pandas as pd

from core.models import TradeSignal, Direction, MarketRegime
from strategy.base_strategy import BaseStrategy


class FundingRateArb(BaseStrategy):
    name = "funding_rate_arb"

    def __init__(self, extreme_threshold: float = 0.001) -> None:
        self.extreme_threshold = extreme_threshold  # 0.1% per 8h = very extreme
        self._funding_rates: Dict[str, float] = {}

    def update_funding_rate(self, symbol: str, rate: float) -> None:
        """Update current funding rate for a symbol."""
        self._funding_rates[symbol] = rate

    def generate(
        self, klines: pd.DataFrame, symbol: str, regime: MarketRegime
    ) -> List[TradeSignal]:
        """Generate signal based on extreme funding rates."""
        rate = self._funding_rates.get(symbol)
        if rate is None or len(klines) < 20:
            return []

        close = klines.iloc[-1]["close"]
        atr = (klines["high"] - klines["low"]).tail(14).mean()

        signals: List[TradeSignal] = []

        if rate > self.extreme_threshold:
            # High positive funding = longs pay shorts -> go SHORT (collect funding)
            confidence = min(0.7, 0.4 + (rate - self.extreme_threshold) * 100)
            signals.append(
                TradeSignal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    confidence=round(confidence, 3),
                    entry_price=close,
                    stop_loss=round(close + atr * 1.5, 2),
                    take_profit=round(close - atr * 3.0, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                )
            )

        elif rate < -self.extreme_threshold:
            # High negative funding = shorts pay longs -> go LONG
            confidence = min(0.7, 0.4 + (abs(rate) - self.extreme_threshold) * 100)
            signals.append(
                TradeSignal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    confidence=round(confidence, 3),
                    entry_price=close,
                    stop_loss=round(close - atr * 1.5, 2),
                    take_profit=round(close + atr * 3.0, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                )
            )

        return signals
