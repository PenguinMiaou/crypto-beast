"""Tests for SentimentRadar."""

import pytest

from core.models import SignalType
from data.sentiment_radar import SentimentRadar


@pytest.fixture
def radar():
    return SentimentRadar()


class TestSentimentRadar:
    def test_extreme_fear_bullish(self, radar):
        """F&G=10 (extreme fear) should give contrarian BULLISH signal."""
        radar.update_fear_greed(10)
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BULLISH
        assert signal.confidence > 0.0
        assert "F&G=10" in signal.reason

    def test_extreme_greed_bearish(self, radar):
        """F&G=90 (extreme greed) should give contrarian BEARISH signal."""
        radar.update_fear_greed(90)
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BEARISH
        assert signal.confidence > 0.0

    def test_neutral_fg_neutral(self, radar):
        """F&G=50 should give NEUTRAL signal."""
        radar.update_fear_greed(50)
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
        assert signal.confidence == 0.0

    def test_no_data_neutral(self, radar):
        """No data should give NEUTRAL with 0 confidence."""
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.NEUTRAL
        assert signal.confidence == 0.0
        assert "No data" in signal.reason

    def test_ls_ratio_integration(self, radar):
        """High L/S ratio combined with low F&G should produce signal."""
        radar.update_fear_greed(10)  # extreme fear -> bullish
        radar.update_long_short_ratio(0.3)  # too many shorts -> also bullish
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BULLISH
        # Combined confidence should be higher than F&G alone
        radar2 = SentimentRadar()
        radar2.update_fear_greed(10)
        signal_fg_only = radar2.get_signal("BTCUSDT")
        assert signal.confidence >= signal_fg_only.confidence

    def test_ls_only_signal(self, radar):
        """With neutral F&G but extreme L/S, L/S should drive direction."""
        radar.update_fear_greed(50)  # neutral
        radar.update_long_short_ratio(3.0)  # too many longs -> bearish
        signal = radar.get_signal("BTCUSDT")
        assert signal.direction == SignalType.BEARISH

    def test_fg_clamped(self, radar):
        """F&G values should be clamped to 0-100."""
        radar.update_fear_greed(-10)
        assert radar._fear_greed == 0
        radar.update_fear_greed(150)
        assert radar._fear_greed == 100
