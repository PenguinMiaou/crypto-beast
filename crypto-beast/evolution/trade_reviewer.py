from datetime import datetime
from typing import Dict, List, Optional
from collections import Counter

from core.models import (
    LossCategory,
    LossClassification,
    WinProfile,
    ReviewReport,
    MarketRegime,
    Direction,
)


class TradeReviewer:
    """Post-trade analysis and loss classification."""

    def __init__(self, db=None):
        self.db = db

    def classify_loss(self, trade: dict) -> LossClassification:
        """Classify why a trade lost."""
        trade_id = trade.get("id", 0)
        pnl = trade.get("pnl", 0)
        fees = trade.get("fees", 0)
        side = trade.get("side", "LONG")
        regime = trade.get("regime", "RANGING")

        # 1. FEE_EROSION: profitable before fees
        gross_pnl = pnl + fees
        if gross_pnl > 0 and pnl < 0:
            return LossClassification(
                trade_id=trade_id,
                category=LossCategory.FEE_EROSION,
                confidence=0.95,
                evidence=f"Gross PnL +{gross_pnl:.2f} eroded by fees {fees:.2f}",
                recommendation="Raise minimum confidence threshold or use limit orders",
            )

        # 2. AGAINST_TREND
        if self._is_against_trend(side, regime):
            return LossClassification(
                trade_id=trade_id,
                category=LossCategory.AGAINST_TREND,
                confidence=0.9,
                evidence=f"Traded {side} in {regime} regime",
                recommendation="Increase regime weight in signal scoring",
            )

        # 3. STOP_TOO_TIGHT: check if price reversed after stop
        if trade.get("price_after_exit") is not None:
            entry = trade.get("entry_price", 0)
            exit_price = trade.get("exit_price", 0)
            price_after = trade.get("price_after_exit", 0)

            if side == "LONG" and price_after > entry:
                return LossClassification(
                    trade_id=trade_id,
                    category=LossCategory.STOP_TOO_TIGHT,
                    confidence=0.8,
                    evidence=f"Price reversed to {price_after} after stop at {exit_price}",
                    recommendation="Widen ATR stop multiplier by 0.2",
                )
            elif side == "SHORT" and price_after < entry:
                return LossClassification(
                    trade_id=trade_id,
                    category=LossCategory.STOP_TOO_TIGHT,
                    confidence=0.8,
                    evidence=f"Price reversed to {price_after} after stop at {exit_price}",
                    recommendation="Widen ATR stop multiplier by 0.2",
                )

        # Default: BAD_TIMING
        return LossClassification(
            trade_id=trade_id,
            category=LossCategory.BAD_TIMING,
            confidence=0.5,
            evidence="No specific cause identified",
            recommendation="Review entry trigger sensitivity",
        )

    def _is_against_trend(self, side: str, regime: str) -> bool:
        """Check if trade was against the market regime."""
        if side == "LONG" and regime in ("TRENDING_DOWN",):
            return True
        if side == "SHORT" and regime in ("TRENDING_UP",):
            return True
        return False

    def profile_win(self, trade: dict) -> WinProfile:
        """Analyze a winning trade."""
        entry = trade.get("entry_price", 0)
        exit_price = trade.get("exit_price", 0)
        tp = trade.get("take_profit", exit_price)

        # Capture efficiency: how much of the potential move was captured
        potential_move = abs(tp - entry) if tp != entry else 1
        actual_move = abs(exit_price - entry)
        efficiency = min(1.0, actual_move / potential_move) if potential_move > 0 else 0

        return WinProfile(
            regime=MarketRegime(trade.get("regime", "RANGING")),
            session=trade.get("session", "UNKNOWN"),
            confluence_score=trade.get("confluence_score", 0),
            key_signals=trade.get("key_signals", []),
            capture_efficiency=round(efficiency, 2),
        )

    def get_recommendations(
        self, classifications: List[LossClassification]
    ) -> List[str]:
        """Generate recommendations from loss classifications."""
        if not classifications:
            return []

        # Count categories
        counter = Counter(c.category for c in classifications)
        recommendations = []

        for category, count in counter.most_common():
            # Find the classification with highest confidence for this category
            best = max(
                (c for c in classifications if c.category == category),
                key=lambda c: c.confidence,
            )
            recommendations.append(f"[{count}x {category.value}] {best.recommendation}")

        return recommendations

    def generate_report(
        self, trades: List[dict], period: str = "daily"
    ) -> ReviewReport:
        """Generate a comprehensive review report."""
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]

        loss_classifications = [self.classify_loss(t) for t in losses]
        win_profiles = [self.profile_win(t) for t in wins]
        recommendations = self.get_recommendations(loss_classifications)

        return ReviewReport(
            period=period,
            timestamp=datetime.utcnow(),
            total_trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            loss_classifications=loss_classifications,
            win_profiles=win_profiles,
            recommendations=recommendations,
            hypothetical_results={},
        )
