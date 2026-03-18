# defense/risk_manager.py
from typing import Optional

from loguru import logger

from config import Config
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


class RiskManager:
    def __init__(self, config: Config):
        self.config = config

    def validate(self, signal: TradeSignal, portfolio: Portfolio,
                 min_confidence: float = 0.3) -> Optional[ValidatedOrder]:
        # Reject low confidence signals
        if signal.confidence < min_confidence:
            logger.debug(f"Signal rejected: confidence {signal.confidence} < {min_confidence}")
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

        # Correlation check: reduce confidence for correlated positions
        correlated_pairs = {
            "BTCUSDT": ["ETHUSDT", "SOLUSDT"],
            "ETHUSDT": ["BTCUSDT", "SOLUSDT"],
            "SOLUSDT": ["BTCUSDT", "ETHUSDT"],
        }
        for pos in portfolio.positions:
            if pos.symbol in correlated_pairs.get(signal.symbol, []):
                if pos.direction == signal.direction:
                    signal.confidence *= 0.8
                    logger.debug(f"Correlation penalty: {signal.symbol} same direction as {pos.symbol}")

        # Determine leverage based on confidence
        if signal.confidence >= 0.8:
            leverage = self.config.leverage_high_confidence
        elif signal.confidence >= 0.5:
            leverage = self.config.leverage_medium_confidence
        else:
            leverage = max(3, self.config.leverage_medium_confidence // 2)

        # Calculate available capital per position
        used_margin = sum(
            pos.quantity * pos.entry_price / pos.leverage
            for pos in portfolio.positions
        )
        available = portfolio.equity - used_margin

        # Check minimum notional requirement for this symbol
        min_notional = MIN_NOTIONAL.get(signal.symbol, DEFAULT_MIN_NOTIONAL)
        min_margin_needed = min_notional / leverage

        # Allocate capital: ensure at least min_margin_needed, cap at 50% of equity
        remaining_slots = self.config.max_concurrent_positions - len(portfolio.positions)
        if remaining_slots <= 0:
            return None
        max_per_position = available / remaining_slots
        capital_for_this = max(min_margin_needed * 1.05, max_per_position)  # 5% buffer above minimum
        capital_for_this = min(capital_for_this, available * 0.95, portfolio.equity * 0.5)

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

        # Calculate position size based on risk
        risk_per_trade = capital_for_this * self.config.max_risk_per_trade
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

        return ValidatedOrder(
            signal=signal,
            quantity=round(quantity, 8),
            leverage=leverage,
            order_type=OrderType.MARKET,
            risk_amount=round(risk_amount, 4),
            max_slippage=0.001,
        )

    def validate_fast(self, signal: TradeSignal, portfolio: Portfolio) -> Optional[ValidatedOrder]:
        """Fast validation for altcoin lag strategy."""
        return self.validate(signal, portfolio)
