"""Tests for WhaleTracker."""

from datetime import datetime, timedelta

import pytest

from core.models import SignalType
from data.whale_tracker import WhaleTracker


@pytest.fixture
def tracker():
    return WhaleTracker()


class TestWhaleTracker:
    def test_large_buy_trades_bullish(self, tracker):
        """Large buy trades should produce BULLISH signal."""
        now = datetime.utcnow()
        for _ in range(5):
            tracker.process_trade({
                "price": 50000.0,
                "quantity": 3.0,  # $150k notional
                "is_buyer_maker": False,  # taker buy
                "timestamp": now,
            })
        signal = tracker.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BULLISH
        assert signal.confidence > 0.0
        assert signal.source == "whale_tracker"

    def test_large_sell_trades_bearish(self, tracker):
        """Large sell trades should produce BEARISH signal."""
        now = datetime.utcnow()
        for _ in range(5):
            tracker.process_trade({
                "price": 50000.0,
                "quantity": 3.0,
                "is_buyer_maker": True,  # maker = sell
                "timestamp": now,
            })
        signal = tracker.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BEARISH
        assert signal.confidence > 0.0

    def test_no_trades_neutral(self, tracker):
        """No trades should give NEUTRAL with 0 confidence."""
        signal = tracker.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
        assert signal.confidence == 0.0
        assert "No whale activity" in signal.reason

    def test_old_trades_pruned(self, tracker):
        """Trades older than 15 minutes should be pruned."""
        old_time = datetime.utcnow() - timedelta(minutes=20)
        tracker.process_trade({
            "price": 50000.0,
            "quantity": 3.0,
            "is_buyer_maker": False,
            "timestamp": old_time,
        })
        # The old trade should be pruned when a new one is added
        tracker.process_trade({
            "price": 50000.0,
            "quantity": 3.0,
            "is_buyer_maker": False,
            "timestamp": datetime.utcnow(),
        })
        # Only one trade should remain (the recent one)
        assert len(tracker._large_trades) == 1

    def test_trades_below_threshold_ignored(self, tracker):
        """Trades with notional < $100k should be ignored."""
        tracker.process_trade({
            "price": 50000.0,
            "quantity": 1.0,  # $50k - below threshold
            "is_buyer_maker": False,
            "timestamp": datetime.utcnow(),
        })
        assert len(tracker._large_trades) == 0
        signal = tracker.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL

    def test_balanced_trades_neutral(self, tracker):
        """Equal buys and sells should give NEUTRAL."""
        now = datetime.utcnow()
        for _ in range(3):
            tracker.process_trade({
                "price": 50000.0, "quantity": 3.0,
                "is_buyer_maker": False, "timestamp": now,
            })
            tracker.process_trade({
                "price": 50000.0, "quantity": 3.0,
                "is_buyer_maker": True, "timestamp": now,
            })
        signal = tracker.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
