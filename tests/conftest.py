# tests/conftest.py
import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def sample_klines():
    """Generate realistic OHLCV data for testing."""
    np.random.seed(42)
    n = 500
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = np.clip(close + np.random.randn(n) * 30, low, high)  # Ensure open is between low and high
    volume = np.random.uniform(100, 1000, n)

    df = pd.DataFrame({
        "open_time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


@pytest.fixture
def sample_orderbook():
    """Generate a sample order book."""
    price = 65000.0
    bids = [[price - i * 0.5, np.random.uniform(0.1, 5.0)] for i in range(20)]
    asks = [[price + i * 0.5, np.random.uniform(0.1, 5.0)] for i in range(20)]
    return {"bids": bids, "asks": asks, "symbol": "BTCUSDT", "timestamp": datetime.utcnow()}


@pytest.fixture
def db(tmp_path):
    from core.database import Database
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db
