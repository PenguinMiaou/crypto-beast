# strategy/base_strategy.py
from abc import ABC, abstractmethod

import pandas as pd

from core.models import MarketRegime, TradeSignal


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        """Generate trade signals from OHLCV data."""
        pass
