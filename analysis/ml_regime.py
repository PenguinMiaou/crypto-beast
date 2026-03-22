"""ML-enhanced regime detection using LightGBM."""
import math
import os
from typing import List, Optional

import numpy as np
import pandas as pd
import ta
from loguru import logger

from analysis.market_regime import MarketRegimeDetector
from core.models import MarketRegime


class MLRegimeDetector(MarketRegimeDetector):
    """LightGBM regime detector with rule-based fallback."""

    def __init__(self, model_path: str = "models/regime_model.pkl", **kwargs):
        super().__init__(**kwargs)
        self._model = None
        self._model_path = model_path
        self._load_model()

    def _load_model(self):
        if os.path.exists(self._model_path):
            try:
                import joblib
                self._model = joblib.load(self._model_path)
                logger.info(f"ML regime model loaded from {self._model_path}")
            except Exception as e:
                logger.warning(f"Failed to load ML regime model: {e}")

    def detect(self, klines: pd.DataFrame, symbol: str = "") -> MarketRegime:
        if self._model is None or len(klines) < 50:
            return super().detect(klines, symbol=symbol)

        try:
            features = self._extract_features(klines)
            if any(np.isnan(f) for f in features):
                return super().detect(klines, symbol=symbol)
            prediction = self._model.predict([features])[0]
            try:
                return MarketRegime(prediction)
            except ValueError:
                logger.debug(f"ML regime prediction '{prediction}' unknown, using rules")
                return super().detect(klines, symbol=symbol)
        except Exception as e:
            logger.debug(f"ML regime error: {e}, using rules")
            return super().detect(klines, symbol=symbol)

    def _extract_features(self, klines: pd.DataFrame) -> List[float]:
        """Extract ~18 features for ML prediction."""
        close = klines["close"]
        high = klines["high"]
        low = klines["low"]
        volume = klines["volume"]

        # Trend features
        adx_val = ta.trend.adx(high, low, close, window=14).iloc[-1]
        ema9 = ta.trend.ema_indicator(close, window=9).iloc[-1]
        ema21 = ta.trend.ema_indicator(close, window=21).iloc[-1]
        ema20 = ta.trend.ema_indicator(close, window=20).iloc[-1]
        ema50 = ta.trend.ema_indicator(close, window=50).iloc[-1]
        price = close.iloc[-1]
        ema9_21_spread = (ema9 - ema21) / price if price > 0 else 0
        ema20_50_spread = (ema20 - ema50) / price if price > 0 else 0
        macd_hist = ta.trend.macd_diff(close).iloc[-1]

        # Volatility features
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_width = bb.bollinger_wband().iloc[-1]
        atr = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]
        atr_pct = atr / price if price > 0 else 0

        # Recent range std (volatility change)
        recent_ranges = (high.iloc[-5:] - low.iloc[-5:]).std()

        # Momentum features
        rsi = ta.momentum.rsi(close, window=14).iloc[-1]
        rsi_change = rsi - ta.momentum.rsi(close, window=14).iloc[-6] if len(close) > 20 else 0

        # Volume features
        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1.0
        vol_trend = 1.0 if volume.iloc[-1] > volume.iloc[-4] else -1.0

        # Structure features
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_position = (price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        # Time features (cyclical encoding)
        if "open_time" in klines.columns:
            hour = klines["open_time"].iloc[-1].hour if hasattr(klines["open_time"].iloc[-1], 'hour') else 12
        else:
            hour = 12
        hour_sin = math.sin(2 * math.pi * hour / 24)
        hour_cos = math.cos(2 * math.pi * hour / 24)

        features = [
            adx_val, ema9_21_spread, ema20_50_spread, macd_hist,
            bb_width, atr_pct, recent_ranges,
            rsi, rsi_change,
            vol_ratio, vol_trend,
            bb_position,
            hour_sin, hour_cos,
        ]

        # Replace any NaN with 0
        return [0.0 if np.isnan(f) else float(f) for f in features]
