# defense/risk_manager.py
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from loguru import logger

from config import Config
from core.database import Database
from core.models import (
    Direction,
    OrderType,
    Portfolio,
    Position,
    TradeSignal,
    ValidatedOrder,
)

# Binance Futures minimum notional per symbol
MIN_NOTIONAL = {
    "BTCUSDT": 100,
    "ETHUSDT": 20,
    "SOLUSDT": 20,
    "BNBUSDT": 20,
    "XRPUSDT": 20,
    "DOGEUSDT": 20,
    "ADAUSDT": 20,
    "AVAXUSDT": 20,
    "LINKUSDT": 20,
    "DOTUSDT": 20,
    "MATICUSDT": 20,
}
DEFAULT_MIN_NOTIONAL = 20


class AdaptiveRiskState:
    """Tracks recent trade performance and returns a position-size scale factor (0.0–1.3)."""

    def __init__(self, db: Optional[Database], lookback: int = 10, cooldown_hours: int = 2):
        self._db = db
        self._lookback = lookback
        self._cooldown_hours = cooldown_hours
        self._cooldown_until: Optional[datetime] = None
        self._grace_until: Optional[datetime] = None
        self._cache_scale: Optional[float] = None
        self._cache_ts: float = 0.0
        self._cache_ttl: float = 60.0  # seconds

    def get_scale_factor(self) -> float:
        """Return a multiplier (0.0–1.3) to apply to position size."""
        now_ts = time.monotonic()
        if self._cache_scale is not None and (now_ts - self._cache_ts) < self._cache_ttl:
            return self._cache_scale

        scale = self._compute_scale()
        self._cache_scale = scale
        self._cache_ts = now_ts
        return scale

    def _compute_scale(self) -> float:
        # Handle active cooldown
        if self._cooldown_until is not None:
            now = datetime.now(timezone.utc)
            if now < self._cooldown_until:
                return 0.0
            else:
                # Cooldown expired — resume at 0.5 scale for the NEXT cooldown period
                # This prevents re-triggering immediately when historical win_rate is still low
                logger.info("AdaptiveRisk: cooldown expired, resuming at 0.5 scale")
                self._cooldown_until = None
                # Set a grace period: don't re-evaluate win_rate for another cooldown period
                self._grace_until = now + timedelta(hours=self._cooldown_hours)
                return 0.5

        # Grace period after cooldown: trade at reduced scale without re-checking win_rate
        if hasattr(self, '_grace_until') and self._grace_until is not None:
            now = datetime.now(timezone.utc)
            if now < self._grace_until:
                return 0.5  # Reduced scale during grace
            else:
                self._grace_until = None  # Grace expired, resume normal evaluation

        if self._db is None:
            return 1.0

        try:
            cursor = self._db.execute(
                "SELECT pnl FROM trades WHERE status='CLOSED' AND pnl IS NOT NULL"
                " ORDER BY exit_time DESC LIMIT ?",
                (self._lookback,),
            )
            rows = cursor.fetchall()
        except Exception as exc:
            logger.warning(f"AdaptiveRisk: DB query failed: {exc}")
            return 1.0

        if not rows:
            return 1.0

        pnls: List[float] = [row[0] for row in rows]

        # Count consecutive losses from most recent
        consecutive_losses = 0
        for pnl in pnls:
            if pnl < 0:
                consecutive_losses += 1
            else:
                break

        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100  # percent

        # Win-rate at or below 30% → enter cooldown, block trading
        if win_rate <= 30.0:
            self._cooldown_until = datetime.now(timezone.utc) + timedelta(hours=self._cooldown_hours)
            logger.warning(
                f"AdaptiveRisk: win_rate={win_rate:.0f}% <= 30% — entering {self._cooldown_hours}h cooldown"
            )
            return 0.0

        # Consecutive-loss scaling
        if consecutive_losses >= 5:
            logger.info(f"AdaptiveRisk: {consecutive_losses} consecutive losses → 0.25 scale")
            return 0.25
        if consecutive_losses >= 3:
            logger.info(f"AdaptiveRisk: {consecutive_losses} consecutive losses → 0.50 scale")
            return 0.50

        # Winning streak bonus
        if win_rate > 70.0 and consecutive_losses == 0:
            return 1.3

        return 1.0

    def get_min_confidence_boost(self) -> float:
        """Return extra confidence threshold when performance is poor."""
        scale = self.get_scale_factor()
        if scale <= 0.25:
            return 0.15
        if scale <= 0.50:
            return 0.10
        return 0.0


class RiskManager:
    def __init__(self, config: Config, db: Optional[Database] = None,
                 compound_engine: Optional[object] = None):
        self.config = config
        self._adaptive = (
            AdaptiveRiskState(db, config.adaptive_lookback, config.adaptive_cooldown_hours)
            if db else None
        )
        self._compound = compound_engine

    def validate(self, signal: TradeSignal, portfolio: Portfolio,
                 min_confidence: float = 0.3) -> Optional[ValidatedOrder]:
        # Reject low confidence signals
        if signal.confidence < min_confidence:
            logger.debug(f"Signal rejected: confidence {signal.confidence} < {min_confidence}")
            return None

        # Adaptive risk check
        if self._adaptive:
            adaptive_scale = self._adaptive.get_scale_factor()
            if adaptive_scale <= 0.0:
                logger.debug("Signal rejected: adaptive cooldown (win_rate < 30%)")
                return None
            conf_boost = self._adaptive.get_min_confidence_boost()
            if signal.confidence < (min_confidence + conf_boost):
                logger.debug(f"Signal rejected: adaptive min_confidence {min_confidence + conf_boost:.2f}")
                return None

        # Kelly criterion: reject strategies with negative expected value
        if self._compound:
            strategy_kelly = self._compound.get_kelly_fraction(signal.strategy)
            if strategy_kelly <= 0.0:
                logger.debug(f"Signal rejected: Kelly too low ({strategy_kelly:.4f}) for {signal.strategy}")
                return None

        # Check max concurrent positions
        if len(portfolio.positions) >= self.config.max_concurrent_positions:
            logger.debug("Signal rejected: max positions reached")
            return None

        # Check if already have position in same symbol + same direction
        # Opposite direction is allowed (caller handles closing the old position first)
        for pos in portfolio.positions:
            if pos.symbol == signal.symbol and pos.direction == signal.direction:
                logger.debug(f"Signal rejected: already have {signal.direction.value} in {signal.symbol}")
                return None

        # Directional exposure check: reject if same-dir notional exceeds max_directional_leverage * equity
        if not self._check_directional_exposure(signal, portfolio):
            return None

        # Correlation check: reduce confidence for correlated positions
        correlated_pairs = {
            "BTCUSDT": ["ETHUSDT", "SOLUSDT"],
            "ETHUSDT": ["BTCUSDT", "SOLUSDT"],
            "SOLUSDT": ["BTCUSDT", "ETHUSDT"],
        }
        for pos in portfolio.positions:
            if pos.symbol in correlated_pairs.get(signal.symbol, []):
                if pos.direction == signal.direction:
                    signal.confidence *= self.config.correlation_penalty
                    logger.debug(f"Correlation penalty: {signal.symbol} same direction as {pos.symbol}")

        # Determine leverage based on confidence
        if signal.confidence >= 0.8:
            leverage = self.config.leverage_high_confidence
        elif signal.confidence >= 0.5:
            leverage = self.config.leverage_medium_confidence
        else:
            leverage = max(3, self.config.leverage_medium_confidence // 2)

        # Calculate available capital per position (exclude profit-locked capital)
        locked = self._compound.get_locked_capital() if self._compound else 0
        effective_equity = max(portfolio.equity - locked, 0)
        used_margin = sum(
            pos.quantity * pos.entry_price / pos.leverage
            for pos in portfolio.positions
        )
        available = effective_equity - used_margin

        # Check minimum notional requirement for this symbol
        min_notional = MIN_NOTIONAL.get(signal.symbol, DEFAULT_MIN_NOTIONAL)
        min_margin_needed = min_notional / leverage

        # Allocate capital: ensure at least min_margin_needed, cap at 40% of equity
        remaining_slots = self.config.max_concurrent_positions - len(portfolio.positions)
        if remaining_slots <= 0:
            return None
        max_per_position = available / remaining_slots
        capital_for_this = max(min_margin_needed * 1.05, max_per_position)  # 5% buffer above minimum
        capital_for_this = min(capital_for_this, available * 0.95, effective_equity * 0.4)

        if capital_for_this <= 0:
            logger.debug("Signal rejected: no available capital")
            return None

        # Check minimum profit vs fees (TP must cover at least 3x round-trip fees)
        entry = signal.entry_price
        stop = signal.stop_loss
        tp = signal.take_profit
        if entry > 0 and tp > 0:
            tp_distance_pct = abs(tp - entry) / entry
            min_profit_pct = self.config.taker_fee * 2 * 3 / leverage  # 3x round-trip fees / leverage
            if tp_distance_pct < min_profit_pct:
                logger.debug(
                    f"Signal rejected: TP too close ({tp_distance_pct:.4%} < {min_profit_pct:.4%} min for {leverage}x)"
                )
                return None

        # Confidence-scaled risk: continuous scaling from 1.0x at min confidence to 3.5x at 1.0
        base_risk = self.config.max_risk_per_trade  # 0.03 base
        MIN_CONF = 0.3
        MAX_MULTIPLIER = 3.5
        if signal.confidence <= MIN_CONF:
            risk_multiplier = 1.0
        else:
            risk_multiplier = 1.0 + (signal.confidence - MIN_CONF) / (1.0 - MIN_CONF) * (MAX_MULTIPLIER - 1.0)
        risk_multiplier = max(1.0, min(MAX_MULTIPLIER, risk_multiplier))

        # Calculate position size based on risk
        risk_per_trade = capital_for_this * base_risk * risk_multiplier
        risk_distance = abs(entry - stop)

        if risk_distance == 0:
            logger.warning("Signal rejected: zero risk distance")
            return None

        # Position size in base currency
        quantity = risk_per_trade / risk_distance

        # Check notional (quantity * price) meets minimum
        min_notional = MIN_NOTIONAL.get(signal.symbol, DEFAULT_MIN_NOTIONAL)
        notional = quantity * entry
        if notional < min_notional:
            # Increase to minimum notional
            quantity = min_notional / entry

        # Cap notional to available margin * leverage
        max_notional = capital_for_this * leverage
        if quantity * entry > max_notional:
            quantity = max_notional / entry

        # Final notional check — if still below minimum after capping, reject
        notional = quantity * entry
        required_margin = notional / leverage
        if notional < min_notional:
            logger.debug(f"Signal rejected: notional ${notional:.2f} < min ${min_notional}")
            return None
        if required_margin > available:
            logger.debug(f"Signal rejected: margin ${required_margin:.2f} > available ${available:.2f}")
            return None

        risk_amount = quantity * risk_distance

        # Apply adaptive risk scaling to final quantity
        if self._adaptive:
            quantity = quantity * self._adaptive.get_scale_factor()

        return ValidatedOrder(
            signal=signal,
            quantity=round(quantity, 8),
            leverage=leverage,
            order_type=OrderType.MARKET,
            risk_amount=round(risk_amount, 4),
            max_slippage=0.001,
        )

    def _check_directional_exposure(self, signal: TradeSignal, portfolio: Portfolio) -> bool:
        """Return False (reject) if adding this signal would exceed directional exposure limits."""
        same_dir_positions = [p for p in portfolio.positions if p.direction == signal.direction]

        # Check total same-direction notional vs equity
        same_dir_notional = sum(p.quantity * p.entry_price for p in same_dir_positions)
        # Estimate proposed notional: use max_risk_per_trade * MAX_MULTIPLIER as rough proxy
        # Actual quantity not yet known, so use min_notional as conservative floor
        min_notional = MIN_NOTIONAL.get(signal.symbol, DEFAULT_MIN_NOTIONAL)
        proposed_notional = max(min_notional, portfolio.equity * self.config.max_risk_per_trade)
        if same_dir_notional + proposed_notional > portfolio.equity * self.config.max_directional_leverage:
            logger.debug(
                f"Signal rejected: directional exposure ${same_dir_notional + proposed_notional:.2f}"
                f" > {self.config.max_directional_leverage}x equity ${portfolio.equity:.2f}"
            )
            return False

        # Check correlated same-direction count
        correlated_group = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        if signal.symbol in correlated_group:
            same_dir_corr_count = sum(
                1 for p in same_dir_positions if p.symbol in correlated_group
            )
            if same_dir_corr_count >= self.config.max_correlated_same_dir:
                logger.debug(
                    f"Signal rejected: {same_dir_corr_count} correlated same-dir positions"
                    f" >= limit {self.config.max_correlated_same_dir}"
                )
                return False

        return True

    def validate_fast(self, signal: TradeSignal, portfolio: Portfolio) -> Optional[ValidatedOrder]:
        """Fast validation for altcoin lag strategy."""
        return self.validate(signal, portfolio)
