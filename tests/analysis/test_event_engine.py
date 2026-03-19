"""Tests for EventEngine."""

from datetime import datetime, timezone

import pytest

from analysis.event_engine import EventEngine


@pytest.fixture
def engine():
    return EventEngine()


class TestIsNearFundingForTime:
    def test_745_utc_near_0800_funding(self, engine):
        """7:45 UTC is 15 min before 8:00 funding -> True."""
        assert engine.is_near_funding_for_time(7, 45, minutes_before=30) is True

    def test_0600_utc_not_near_funding(self, engine):
        """6:00 UTC is 120 min before 8:00 funding -> False."""
        assert engine.is_near_funding_for_time(6, 0, minutes_before=30) is False

    def test_2345_utc_wraps_to_0000(self, engine):
        """23:45 UTC is 15 min before 0:00 funding (wrap) -> True."""
        assert engine.is_near_funding_for_time(23, 45, minutes_before=30) is True

    def test_exact_funding_time_not_near(self, engine):
        """At exact funding time diff=0 which is not > 0 -> False."""
        assert engine.is_near_funding_for_time(8, 0, minutes_before=30) is False

    def test_1550_utc_near_1600(self, engine):
        """15:50 UTC is 10 min before 16:00 -> True with 15 min window."""
        assert engine.is_near_funding_for_time(15, 50, minutes_before=15) is True


class TestShouldReduceExposure:
    def test_should_reduce_at_1550(self, engine):
        """should_reduce_exposure uses 15 min window internally."""
        # We test via is_near_funding_for_time since should_reduce_exposure
        # uses real time. Just verify the 15 min logic is correct.
        assert engine.is_near_funding_for_time(15, 50, minutes_before=15) is True
        assert engine.is_near_funding_for_time(15, 30, minutes_before=15) is False


class TestCustomEvents:
    def test_add_event(self, engine):
        ts = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        engine.add_event("CPI Release", ts, impact="high")
        assert len(engine._custom_events) == 1
        assert engine._custom_events[0]["name"] == "CPI Release"
        assert engine._custom_events[0]["impact"] == "high"

    def test_add_event_default_impact(self, engine):
        ts = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
        engine.add_event("FOMC", ts)
        assert engine._custom_events[0]["impact"] == "medium"

    def test_get_upcoming_events_returns_list(self, engine):
        """get_upcoming_events returns a list (may be empty with stale timestamps)."""
        result = engine.get_upcoming_events()
        assert isinstance(result, list)
