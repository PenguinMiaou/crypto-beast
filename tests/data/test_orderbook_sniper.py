"""Tests for OrderBookSniper."""

import pytest

from core.models import SignalType
from data.orderbook_sniper import OrderBookSniper


@pytest.fixture
def sniper():
    return OrderBookSniper()


@pytest.fixture
def bid_heavy_orderbook():
    """Order book with much more bid volume than ask volume."""
    return {
        "bids": [[50000 - i, 10.0] for i in range(20)],  # 200 total
        "asks": [[50001 + i, 2.0] for i in range(20)],   # 40 total -> ratio = 5.0
    }


@pytest.fixture
def ask_heavy_orderbook():
    """Order book with much more ask volume than bid volume."""
    return {
        "bids": [[50000 - i, 2.0] for i in range(20)],   # 40 total
        "asks": [[50001 + i, 10.0] for i in range(20)],  # 200 total -> ratio = 0.2
    }


@pytest.fixture
def balanced_orderbook():
    """Balanced order book."""
    return {
        "bids": [[50000 - i, 5.0] for i in range(20)],
        "asks": [[50001 + i, 5.0] for i in range(20)],  # ratio = 1.0
    }


@pytest.fixture
def wall_orderbook():
    """Order book with a large wall on the bid side."""
    bids = [[50000 - i, 1.0] for i in range(20)]
    bids[5] = [49995, 100.0]  # Wall: 100x normal
    asks = [[50001 + i, 1.0] for i in range(20)]
    return {"bids": bids, "asks": asks}


class TestOrderBookSniper:
    def test_bid_heavy_bullish(self, sniper, bid_heavy_orderbook):
        """Bid-heavy orderbook should produce BULLISH signal."""
        signal = sniper.get_signal("BTCUSDT", bid_heavy_orderbook)
        assert signal.direction == SignalType.BULLISH
        assert signal.confidence > 0.0
        assert signal.source == "orderbook_sniper"

    def test_ask_heavy_bearish(self, sniper, ask_heavy_orderbook):
        """Ask-heavy orderbook should produce BEARISH signal."""
        signal = sniper.get_signal("BTCUSDT", ask_heavy_orderbook)
        assert signal.direction == SignalType.BEARISH
        assert signal.confidence > 0.0

    def test_balanced_neutral(self, sniper, balanced_orderbook):
        """Balanced orderbook should produce NEUTRAL signal."""
        signal = sniper.get_signal("BTCUSDT", balanced_orderbook)
        assert signal.direction == SignalType.NEUTRAL
        assert signal.confidence == 0.1

    def test_wall_detection(self, sniper, wall_orderbook):
        """Should detect wall with quantity > 5x average."""
        walls = sniper.detect_walls(wall_orderbook)
        assert len(walls) > 0
        assert walls[0]["quantity"] == 100.0
        assert walls[0]["type"] == "support"

    def test_empty_orderbook(self, sniper):
        """Empty orderbook should be handled gracefully."""
        signal = sniper.get_signal("BTCUSDT", {"bids": [], "asks": []})
        # With no asks, imbalance is inf -> bullish (or handle edge case)
        # get_imbalance returns 0/0 case: bid_vol=0, ask_vol=0 -> inf
        # Actually bid_vol=0, ask_vol=0 -> inf from division guard
        assert signal is not None

    def test_empty_orderbook_walls(self, sniper):
        """Wall detection on empty orderbook should return empty list."""
        walls = sniper.detect_walls({"bids": [], "asks": []})
        assert walls == []

    def test_imbalance_calculation(self, sniper):
        """Test imbalance ratio calculation."""
        orderbook = {
            "bids": [[100, 10.0]],
            "asks": [[101, 5.0]],
        }
        assert sniper.get_imbalance(orderbook) == 2.0
