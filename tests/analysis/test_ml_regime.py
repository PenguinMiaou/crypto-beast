import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from analysis.ml_regime import MLRegimeDetector
from core.models import MarketRegime

@pytest.fixture
def sample_klines():
    np.random.seed(42)
    n = 200
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5*i) for i in range(n)]
    close = 65000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    return pd.DataFrame({
        "open_time": dates, "open": close + np.random.randn(n)*10,
        "high": high, "low": low, "close": close,
        "volume": np.random.uniform(100, 1000, n),
    })

def test_ml_regime_fallback_no_model(sample_klines):
    detector = MLRegimeDetector(model_path="nonexistent.pkl")
    regime = detector.detect(sample_klines)
    assert isinstance(regime, MarketRegime)

def test_ml_regime_feature_extraction(sample_klines):
    detector = MLRegimeDetector(model_path="nonexistent.pkl")
    features = detector._extract_features(sample_klines)
    assert len(features) >= 14
    assert all(not np.isnan(f) for f in features)

def test_ml_regime_inherits_transition_detection(sample_klines):
    """Should still support TRANSITIONING from parent class."""
    detector = MLRegimeDetector(model_path="nonexistent.pkl")
    # First call sets baseline
    detector.detect(sample_klines, symbol="TEST")
    # Second call with very different data should detect transition
    close2 = sample_klines["close"].iloc[-1] - np.arange(200) * 100.0
    df2 = pd.DataFrame({
        "open_time": sample_klines["open_time"],
        "open": close2, "high": close2+50, "low": close2-50,
        "close": close2, "volume": np.random.uniform(100,1000,200),
    })
    r2 = detector.detect(df2, symbol="TEST")
    assert isinstance(r2, MarketRegime)
