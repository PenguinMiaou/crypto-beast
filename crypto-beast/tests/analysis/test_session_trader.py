"""Tests for session-based strategy weighting."""

import pytest
from analysis.session_trader import SessionTrader, SESSION_WEIGHTS


@pytest.fixture
def trader():
    return SessionTrader()


class TestGetSessionForHour:
    def test_asia_session(self, trader):
        assert trader.get_session_for_hour(3) == "ASIA"

    def test_europe_session(self, trader):
        assert trader.get_session_for_hour(10) == "EUROPE"

    def test_us_overlap_session(self, trader):
        assert trader.get_session_for_hour(15) == "US_OVERLAP"

    def test_us_session(self, trader):
        assert trader.get_session_for_hour(19) == "US"

    def test_off_hours_session(self, trader):
        assert trader.get_session_for_hour(22) == "OFF_HOURS"

    def test_boundary_asia_start(self, trader):
        assert trader.get_session_for_hour(0) == "ASIA"

    def test_boundary_asia_end(self, trader):
        assert trader.get_session_for_hour(7) == "ASIA"

    def test_boundary_europe_start(self, trader):
        assert trader.get_session_for_hour(8) == "EUROPE"

    def test_boundary_us_overlap_start(self, trader):
        assert trader.get_session_for_hour(13) == "US_OVERLAP"

    def test_boundary_off_hours_end(self, trader):
        assert trader.get_session_for_hour(23) == "OFF_HOURS"


class TestStrategyWeights:
    def test_weights_differ_by_session(self, trader):
        """Strategy weights should differ between sessions."""
        asia_weights = SESSION_WEIGHTS["ASIA"]
        us_overlap_weights = SESSION_WEIGHTS["US_OVERLAP"]
        assert asia_weights != us_overlap_weights

    def test_us_overlap_higher_trend_than_asia(self, trader):
        """US_OVERLAP should have higher trend_follower weight than ASIA."""
        assert (
            SESSION_WEIGHTS["US_OVERLAP"]["trend_follower"]
            > SESSION_WEIGHTS["ASIA"]["trend_follower"]
        )

    def test_us_overlap_higher_momentum_than_asia(self, trader):
        """US_OVERLAP should have higher momentum weight than ASIA."""
        assert (
            SESSION_WEIGHTS["US_OVERLAP"]["momentum"]
            > SESSION_WEIGHTS["ASIA"]["momentum"]
        )

    def test_get_strategy_weights_returns_dict(self, trader):
        weights = trader.get_strategy_weights()
        assert isinstance(weights, dict)
        assert "trend_follower" in weights
        assert "momentum" in weights
        assert "breakout" in weights
        assert "mean_reversion" in weights
        assert "scalper" in weights

    def test_get_strategy_weights_returns_copy(self, trader):
        """Modifying returned weights should not affect internal data."""
        weights = trader.get_strategy_weights()
        session = trader.get_current_session()
        weights["trend_follower"] = 999.0
        assert SESSION_WEIGHTS[session]["trend_follower"] != 999.0


class TestGetCurrentSession:
    def test_returns_valid_session(self, trader):
        session = trader.get_current_session()
        assert session in SESSION_WEIGHTS
