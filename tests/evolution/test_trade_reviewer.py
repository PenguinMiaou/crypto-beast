import pytest
from datetime import datetime

from evolution.trade_reviewer import TradeReviewer
from core.models import LossCategory, LossClassification


@pytest.fixture
def reviewer():
    return TradeReviewer()


class TestClassifyLoss:
    def test_stop_too_tight_long(self, reviewer):
        """STOP_TOO_TIGHT: LONG trade where price reversed past entry after stop."""
        trade = {
            "id": 1,
            "pnl": -50,
            "fees": 5,
            "side": "LONG",
            "regime": "RANGING",
            "entry_price": 100,
            "exit_price": 95,
            "price_after_exit": 110,
        }
        result = reviewer.classify_loss(trade)
        assert result.category == LossCategory.STOP_TOO_TIGHT
        assert result.confidence == 0.8

    def test_against_trend_long_in_downtrend(self, reviewer):
        """AGAINST_TREND: LONG trade in TRENDING_DOWN regime."""
        trade = {
            "id": 2,
            "pnl": -100,
            "fees": 5,
            "side": "LONG",
            "regime": "TRENDING_DOWN",
        }
        result = reviewer.classify_loss(trade)
        assert result.category == LossCategory.AGAINST_TREND
        assert result.confidence == 0.9

    def test_fee_erosion(self, reviewer):
        """FEE_EROSION: positive gross PnL, negative net PnL."""
        trade = {
            "id": 3,
            "pnl": -2,
            "fees": 5,
            "side": "LONG",
            "regime": "RANGING",
        }
        # gross_pnl = -2 + 5 = 3 > 0, pnl = -2 < 0
        result = reviewer.classify_loss(trade)
        assert result.category == LossCategory.FEE_EROSION
        assert result.confidence == 0.95

    def test_bad_timing_default(self, reviewer):
        """BAD_TIMING: default when no specific cause found."""
        trade = {
            "id": 4,
            "pnl": -50,
            "fees": 2,
            "side": "LONG",
            "regime": "RANGING",
        }
        result = reviewer.classify_loss(trade)
        assert result.category == LossCategory.BAD_TIMING
        assert result.confidence == 0.5


class TestProfileWin:
    def test_capture_efficiency(self, reviewer):
        """Capture efficiency calculated correctly."""
        trade = {
            "entry_price": 100,
            "exit_price": 140,
            "take_profit": 150,
            "regime": "TRENDING_UP",
            "session": "US",
            "confluence_score": 7,
            "key_signals": ["ema_cross"],
            "pnl": 40,
        }
        profile = reviewer.profile_win(trade)
        # potential_move = |150 - 100| = 50, actual_move = |140 - 100| = 40
        # efficiency = 40/50 = 0.8
        assert profile.capture_efficiency == 0.8
        assert profile.session == "US"


class TestGetRecommendations:
    def test_most_frequent_first(self, reviewer):
        """Most frequent category listed first."""
        classifications = [
            LossClassification(1, LossCategory.BAD_TIMING, 0.5, "e", "r1"),
            LossClassification(2, LossCategory.BAD_TIMING, 0.6, "e", "r2"),
            LossClassification(3, LossCategory.FEE_EROSION, 0.9, "e", "r3"),
        ]
        recs = reviewer.get_recommendations(classifications)
        assert len(recs) == 2
        assert "2x BAD_TIMING" in recs[0]
        assert "1x FEE_EROSION" in recs[1]

    def test_empty_classifications(self, reviewer):
        assert reviewer.get_recommendations([]) == []


class TestGenerateReport:
    def test_correct_counts(self, reviewer):
        """generate_report: correct win/loss counts."""
        trades = [
            {"id": 1, "pnl": 50, "entry_price": 100, "exit_price": 110, "regime": "RANGING"},
            {"id": 2, "pnl": 30, "entry_price": 100, "exit_price": 105, "regime": "TRENDING_UP"},
            {"id": 3, "pnl": -20, "fees": 2, "side": "LONG", "regime": "RANGING"},
        ]
        report = reviewer.generate_report(trades, period="daily")
        assert report.total_trades == 3
        assert report.wins == 2
        assert report.losses == 1
        assert len(report.loss_classifications) == 1
        assert len(report.win_profiles) == 2
        assert report.period == "daily"
