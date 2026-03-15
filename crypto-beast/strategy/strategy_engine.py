# strategy/strategy_engine.py
"""Multi-strategy orchestrator with weighted signal generation and deduplication."""

from typing import Dict, List, Optional

import pandas as pd

from core.models import ConfluenceScore, MarketRegime, SignalType, TradeSignal
from analysis.market_regime import MarketRegimeDetector
from analysis.multi_timeframe import MultiTimeframe
from analysis.session_trader import SessionTrader
from strategy.base_strategy import BaseStrategy
from strategy.trend_follower import TrendFollower
from strategy.mean_reversion import MeanReversion
from strategy.momentum import Momentum
from strategy.breakout import Breakout
from strategy.scalper import Scalper


class StrategyEngine:
    """Orchestrates multiple trading strategies with weighted scoring."""

    def __init__(
        self,
        regime_detector: MarketRegimeDetector,
        session_trader: SessionTrader,
        multi_timeframe: MultiTimeframe,
    ):
        self._regime_detector = regime_detector
        self._session_trader = session_trader
        self._multi_timeframe = multi_timeframe

        self._strategies: Dict[str, BaseStrategy] = {
            "trend_follower": TrendFollower(),
            "mean_reversion": MeanReversion(),
            "momentum": Momentum(),
            "breakout": Breakout(),
            "scalper": Scalper(),
        }
        # Default equal weights, updated by Evolver
        self._weights: Dict[str, float] = {name: 0.2 for name in self._strategies}

    def generate_signals(self, symbol: str, klines: pd.DataFrame) -> List[TradeSignal]:
        """Generate signals from all strategies, apply weights, deduplicate.

        Args:
            symbol: Trading pair (e.g. "BTCUSDT").
            klines: OHLCV DataFrame for the primary timeframe.

        Returns:
            Deduplicated signals sorted by weighted confidence (descending).
        """
        if len(klines) < 50:
            return []

        regime = self._regime_detector.detect(klines)
        session_weights = self._session_trader.get_strategy_weights()
        confluence = self._multi_timeframe.get_confluence(symbol)

        signals: List[TradeSignal] = []

        for name, strategy in self._strategies.items():
            raw_signals = strategy.generate(klines, symbol, regime)
            for sig in raw_signals:
                # Apply weight: strategy_weight * session_weight
                weight = self._weights.get(name, 0.2) * session_weights.get(name, 1.0)
                sig.confidence = round(sig.confidence * weight, 4)
                # Set timeframe score from MultiTimeframe
                if confluence is not None:
                    sig.timeframe_score = confluence.score
                signals.append(sig)

        # Deduplicate: per symbol, keep highest confidence direction only
        best_per_symbol: Dict[str, TradeSignal] = {}
        for sig in signals:
            key = sig.symbol
            if key not in best_per_symbol or sig.confidence > best_per_symbol[key].confidence:
                best_per_symbol[key] = sig

        return sorted(best_per_symbol.values(), key=lambda s: s.confidence, reverse=True)

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """Update strategy weights (called by Evolver)."""
        self._weights.update(new_weights)

    def get_strategy_weights(self) -> Dict[str, float]:
        """Return current strategy weights."""
        return self._weights.copy()
