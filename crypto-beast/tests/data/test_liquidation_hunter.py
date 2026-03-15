"""Tests for LiquidationHunter."""

from datetime import datetime, timedelta, timezone

import pytest

from core.models import SignalType
from data.liquidation_hunter import LiquidationHunter


@pytest.fixture
def hunter():
    return LiquidationHunter(cascade_multiplier=2.0, window_minutes=5)


class TestLiquidationHunter:
    def test_cascade_detection(self, hunter):
        """High volume events should trigger cascade detection."""
        now = datetime.now(timezone.utc)
        # Set a low average so current volume exceeds 2x
        hunter.update_average(1000.0)

        # Add large liquidation events within the window
        for i in range(5):
            hunter.process_liquidation({
                "side": "LONG",
                "quantity": 10.0,
                "price": 50000.0,  # $500k each
                "timestamp": now,
            })

        assert hunter.is_cascade_active() is True

    def test_bullish_after_long_cascade(self, hunter):
        """Long liquidation cascade should produce BULLISH signal (reversal)."""
        now = datetime.now(timezone.utc)
        hunter.update_average(1000.0)

        for _ in range(5):
            hunter.process_liquidation({
                "side": "LONG",
                "quantity": 10.0,
                "price": 50000.0,
                "timestamp": now,
            })

        signal = hunter.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BULLISH
        assert signal.confidence > 0.0
        assert "Long liquidation cascade" in signal.reason

    def test_bearish_after_short_cascade(self, hunter):
        """Short liquidation cascade should produce BEARISH signal."""
        now = datetime.now(timezone.utc)
        hunter.update_average(1000.0)

        for _ in range(5):
            hunter.process_liquidation({
                "side": "SHORT",
                "quantity": 10.0,
                "price": 50000.0,
                "timestamp": now,
            })

        signal = hunter.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BEARISH
        assert signal.confidence > 0.0

    def test_no_events_neutral(self, hunter):
        """No liquidation events should give NEUTRAL."""
        signal = hunter.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
        assert signal.confidence == 0.0
        assert "No liquidation data" in signal.reason

    def test_normal_activity_neutral(self, hunter):
        """Non-cascade activity should give NEUTRAL."""
        now = datetime.now(timezone.utc)
        # Set high average so current volume doesn't exceed 2x
        hunter.update_average(10_000_000.0)

        hunter.process_liquidation({
            "side": "LONG",
            "quantity": 1.0,
            "price": 50000.0,
            "timestamp": now,
        })

        signal = hunter.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
        assert "Normal liquidation activity" in signal.reason

    def test_old_events_pruned(self, hunter):
        """Events older than 30 minutes should be pruned."""
        old_time = datetime.now(timezone.utc) - timedelta(minutes=35)
        hunter.process_liquidation({
            "side": "LONG",
            "quantity": 10.0,
            "price": 50000.0,
            "timestamp": old_time,
        })
        # Add a recent event to trigger pruning
        hunter.process_liquidation({
            "side": "LONG",
            "quantity": 1.0,
            "price": 50000.0,
            "timestamp": datetime.now(timezone.utc),
        })
        assert len(hunter._events) == 1

    def test_update_average(self, hunter):
        """update_average should maintain rolling average."""
        hunter.update_average(100.0)
        hunter.update_average(200.0)
        assert hunter._avg_volume == 150.0
        assert len(hunter._volume_history) == 2
