"""Tests for AltcoinRadar."""

import pytest

from analysis.altcoin_radar import AltcoinRadar


@pytest.fixture
def radar():
    return AltcoinRadar(max_alts=3)


class TestScoreCoin:
    def test_high_volume_positive_momentum(self, radar):
        """High volume + positive momentum -> high score."""
        score = radar.score_coin(
            "ETHUSDT", volume_24h=2_000_000_000, price_change_24h=8.0
        )
        assert score > 0.5

    def test_score_between_0_and_1(self, radar):
        score = radar.score_coin(
            "SOLUSDT", volume_24h=500_000_000, price_change_24h=3.0,
            btc_correlation=0.7,
        )
        assert 0.0 <= score <= 1.0

    def test_low_correlation_boosts_score(self, radar):
        """Lower BTC correlation should give higher corr_score component."""
        score_high_corr = radar.score_coin(
            "A", volume_24h=1e9, price_change_24h=5.0, btc_correlation=0.9
        )
        score_low_corr = radar.score_coin(
            "B", volume_24h=1e9, price_change_24h=5.0, btc_correlation=0.1
        )
        assert score_low_corr > score_high_corr


class TestGetTopAlts:
    def test_empty_scores_empty_list(self, radar):
        assert radar.get_top_alts() == []

    def test_returns_max_alts(self, radar):
        radar.score_coin("A", 1e9, 5.0)
        radar.score_coin("B", 2e9, 8.0)
        radar.score_coin("C", 500e6, 2.0)
        radar.score_coin("D", 300e6, 1.0)
        top = radar.get_top_alts()
        assert len(top) == 3

    def test_ordered_by_score(self, radar):
        radar.score_coin("LOW", 100e6, 1.0)
        radar.score_coin("HIGH", 2e9, 9.0)
        top = radar.get_top_alts()
        assert top[0] == "HIGH"


class TestGetScores:
    def test_returns_copy(self, radar):
        radar.score_coin("X", 1e9, 5.0)
        scores = radar.get_scores()
        scores["X"] = 999.0
        assert radar._scores["X"] != 999.0
