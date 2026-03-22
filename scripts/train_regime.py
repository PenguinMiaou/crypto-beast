#!/usr/bin/env python3
"""Train LightGBM regime detection model from historical kline data.

Usage: python scripts/train_regime.py
Output: models/regime_model.pkl

Uses cached klines from crypto_beast.db (klines_cache table).
If no cached data, fetches from Binance API.
"""
import os
import sys
import math
import numpy as np
import pandas as pd
from typing import List, Tuple
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def extract_features(klines: pd.DataFrame, idx: int) -> List[float]:
    """Extract features for a single bar (same as MLRegimeDetector._extract_features)."""
    import ta

    window = klines.iloc[max(0, idx-100):idx+1]
    if len(window) < 50:
        return []

    close = window["close"]
    high = window["high"]
    low = window["low"]
    volume = window["volume"]
    price = close.iloc[-1]

    if price <= 0:
        return []

    try:
        adx_val = ta.trend.adx(high, low, close, window=14).iloc[-1]
        ema9 = ta.trend.ema_indicator(close, window=9).iloc[-1]
        ema21 = ta.trend.ema_indicator(close, window=21).iloc[-1]
        ema20 = ta.trend.ema_indicator(close, window=20).iloc[-1]
        ema50 = ta.trend.ema_indicator(close, window=50).iloc[-1]
        ema9_21_spread = (ema9 - ema21) / price
        ema20_50_spread = (ema20 - ema50) / price
        macd_hist = ta.trend.macd_diff(close).iloc[-1]

        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_width = bb.bollinger_wband().iloc[-1]
        atr = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]
        atr_pct = atr / price
        recent_ranges = (high.iloc[-5:] - low.iloc[-5:]).std()

        rsi = ta.momentum.rsi(close, window=14).iloc[-1]
        rsi_prev = ta.momentum.rsi(close, window=14).iloc[-6] if len(close) > 20 else rsi
        rsi_change = rsi - rsi_prev

        vol_sma20 = volume.rolling(20).mean().iloc[-1]
        vol_ratio = volume.iloc[-1] / vol_sma20 if vol_sma20 > 0 else 1.0
        vol_trend = 1.0 if volume.iloc[-1] > volume.iloc[-4] else -1.0

        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_range = bb_upper - bb_lower
        bb_position = (price - bb_lower) / bb_range if bb_range > 0 else 0.5

        if "open_time" in window.columns and hasattr(window["open_time"].iloc[-1], 'hour'):
            hour = window["open_time"].iloc[-1].hour
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

        return [0.0 if (np.isnan(f) or np.isinf(f)) else float(f) for f in features]
    except Exception:
        return []


def generate_label(klines: pd.DataFrame, idx: int, horizon: int = 12) -> str:
    """Generate regime label based on future price movement.

    Looks forward `horizon` bars (default 12 = 1 hour on 5m):
    - Up > 0.5% → TRENDING_UP
    - Down > 0.5% → TRENDING_DOWN
    - Range > 1.5% but no clear direction → HIGH_VOLATILITY
    - Range < 0.3% → LOW_VOLATILITY
    - Otherwise → RANGING
    """
    if idx + horizon >= len(klines):
        return ""

    future = klines["close"].iloc[idx+1:idx+horizon+1]
    current = klines["close"].iloc[idx]

    if current <= 0:
        return ""

    max_price = future.max()
    min_price = future.min()
    end_price = future.iloc[-1]

    pct_change = (end_price - current) / current
    pct_range = (max_price - min_price) / current

    if pct_change > 0.005:
        return "TRENDING_UP"
    elif pct_change < -0.005:
        return "TRENDING_DOWN"
    elif pct_range > 0.015:
        return "HIGH_VOLATILITY"
    elif pct_range < 0.003:
        return "LOW_VOLATILITY"
    else:
        return "RANGING"


def load_data() -> pd.DataFrame:
    """Load klines from cache or generate sample data for testing."""
    import sqlite3
    db_path = str(project_root / "crypto_beast.db")

    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            df = pd.read_sql(
                "SELECT open_time, open, high, low, close, volume "
                "FROM klines_cache WHERE symbol='BTCUSDT' AND interval='5m' "
                "ORDER BY open_time LIMIT 50000",
                conn
            )
            if len(df) > 1000:
                df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
                print(f"Loaded {len(df)} bars from cache")
                return df
        except Exception as e:
            print(f"Cache load failed: {e}")
        finally:
            conn.close()

    # Generate synthetic data for initial model
    print("No cached data found. Generating synthetic training data...")
    np.random.seed(42)
    n = 10000
    dates = pd.date_range("2025-01-01", periods=n, freq="5min")
    close = 65000 + np.cumsum(np.random.randn(n) * 50)
    high = close + np.abs(np.random.randn(n) * 30)
    low = close - np.abs(np.random.randn(n) * 30)
    volume = np.random.uniform(100, 2000, n)

    return pd.DataFrame({
        "open_time": dates, "open": close + np.random.randn(n) * 10,
        "high": high, "low": low, "close": close, "volume": volume,
    })


def main():
    print("=== ML Regime Model Training ===")

    klines = load_data()
    if len(klines) < 500:
        print("ERROR: Not enough data for training (need >= 500 bars)")
        sys.exit(1)

    # Extract features and labels
    print("Extracting features...")
    X = []
    y = []
    for i in range(100, len(klines) - 12):
        features = extract_features(klines, i)
        label = generate_label(klines, i)
        if features and label:
            X.append(features)
            y.append(label)

    print(f"Generated {len(X)} samples")

    if len(X) < 200:
        print("ERROR: Too few valid samples")
        sys.exit(1)

    X = np.array(X)
    y = np.array(y)

    # Print label distribution
    unique, counts = np.unique(y, return_counts=True)
    print("Label distribution:")
    for label, count in zip(unique, counts):
        print(f"  {label}: {count} ({count/len(y)*100:.1f}%)")

    # Train with 5-fold CV
    from sklearn.model_selection import cross_val_score
    import lightgbm as lgb

    model = lgb.LGBMClassifier(
        n_estimators=100,
        max_depth=6,
        learning_rate=0.1,
        min_child_samples=20,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        verbose=-1,
    )

    print("Training with 5-fold CV...")
    scores = cross_val_score(model, X, y, cv=5, scoring="accuracy")
    print(f"CV Accuracy: {scores.mean():.4f} ± {scores.std():.4f}")

    # Train final model on all data
    model.fit(X, y)

    # Save
    import joblib
    os.makedirs(str(project_root / "models"), exist_ok=True)
    model_path = str(project_root / "models" / "regime_model.pkl")
    joblib.dump(model, model_path)
    print(f"Model saved to {model_path}")

    # Feature importance
    print("\nTop features:")
    feature_names = [
        "adx", "ema9_21_spread", "ema20_50_spread", "macd_hist",
        "bb_width", "atr_pct", "range_std",
        "rsi", "rsi_change",
        "vol_ratio", "vol_trend",
        "bb_position",
        "hour_sin", "hour_cos",
    ]
    importances = model.feature_importances_
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: -x[1])[:5]:
        print(f"  {name}: {imp}")

    print("\nDone!")


if __name__ == "__main__":
    main()
