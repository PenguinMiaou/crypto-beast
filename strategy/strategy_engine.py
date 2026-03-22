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
from strategy.ichimoku_cloud import IchimokuCloud
from strategy.enhanced_bb_rsi import EnhancedBbRsi


class StrategyEngine:
    """Orchestrates multiple trading strategies with weighted scoring."""

    REGIME_WEIGHTS: Dict[str, Dict[str, float]] = {
        "TRENDING_UP": {
            "trend_follower": 0.30, "momentum": 0.25, "breakout": 0.15,
            "mean_reversion": 0.05, "scalper": 0.05,
            "ichimoku_cloud": 0.10, "enhanced_bb_rsi": 0.10,
        },
        "TRENDING_DOWN": {
            "trend_follower": 0.30, "momentum": 0.25, "breakout": 0.15,
            "mean_reversion": 0.05, "scalper": 0.05,
            "ichimoku_cloud": 0.10, "enhanced_bb_rsi": 0.10,
        },
        "RANGING": {
            "trend_follower": 0.05, "momentum": 0.05, "breakout": 0.05,
            "mean_reversion": 0.25, "scalper": 0.20,
            "ichimoku_cloud": 0.10, "enhanced_bb_rsi": 0.30,
        },
        "HIGH_VOLATILITY": {
            "trend_follower": 0.15, "momentum": 0.10, "breakout": 0.25,
            "mean_reversion": 0.10, "scalper": 0.05,
            "ichimoku_cloud": 0.15, "enhanced_bb_rsi": 0.20,
        },
        "LOW_VOLATILITY": {
            "trend_follower": 0.10, "momentum": 0.10, "breakout": 0.05,
            "mean_reversion": 0.25, "scalper": 0.20,
            "ichimoku_cloud": 0.10, "enhanced_bb_rsi": 0.20,
        },
        "TRANSITIONING": {
            "trend_follower": 0.10, "momentum": 0.10, "breakout": 0.10,
            "mean_reversion": 0.20, "scalper": 0.15,
            "ichimoku_cloud": 0.15, "enhanced_bb_rsi": 0.20,
        },
    }

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
            "ichimoku_cloud": IchimokuCloud(),
            "enhanced_bb_rsi": EnhancedBbRsi(),
        }
        # Default equal weights (1/7); overridden by regime logic or Evolver
        self._weights: Dict[str, float] = {name: 1.0 / len(self._strategies) for name in self._strategies}

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

        regime = self._regime_detector.detect(klines, symbol=symbol)
        # Regime-aware weights
        regime_weights = self.REGIME_WEIGHTS.get(regime.value, {})
        for name in self._strategies:
            self._weights[name] = regime_weights.get(name, 0.1)
        session_weights = self._session_trader.get_strategy_weights()
        confluence = self._multi_timeframe.get_confluence(symbol)

        signals: List[TradeSignal] = []

        for name, strategy in self._strategies.items():
            raw_signals = strategy.generate(klines, symbol, regime)
            for sig in raw_signals:
                # Session weight as mild time-of-day adjustment (0.5-1.3 range)
                # Strategy weight NOT applied to confidence — only used for dedup ranking
                session_w = session_weights.get(name, 1.0)
                sig.confidence = round(sig.confidence * session_w, 4)
                sig._strategy_weight = self._weights.get(name, 0.2)
                if confluence is not None:
                    sig.timeframe_score = confluence.score
                signals.append(sig)

        # Deduplicate: per symbol, keep highest weighted_score signal
        # weighted_score = confidence * strategy_weight ensures regime-appropriate
        # strategies win selection, while raw confidence drives position sizing
        best_per_symbol: Dict[str, tuple] = {}
        for sig in signals:
            key = sig.symbol
            weighted_score = sig.confidence * sig._strategy_weight
            if key not in best_per_symbol or weighted_score > best_per_symbol[key][0]:
                best_per_symbol[key] = (weighted_score, sig)

        return sorted(
            [v[1] for v in best_per_symbol.values()],
            key=lambda s: s.confidence, reverse=True,
        )

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """Update strategy weights (called by Evolver)."""
        self._weights.update(new_weights)

    def get_strategy_weights(self) -> Dict[str, float]:
        """Return current strategy weights."""
        return self._weights.copy()
