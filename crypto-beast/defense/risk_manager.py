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


class RiskManager:
    def __init__(self, config: Config):
        self.config = config

    def validate(self, signal: TradeSignal, portfolio: Portfolio, min_confidence: float = 0.3) -> Optional[ValidatedOrder]:
        # Reject low confidence signals
        if signal.confidence < min_confidence:
            logger.debug(f"Signal rejected: confidence {signal.confidence} < 0.5")
            return None

        # Check max concurrent positions
        if len(portfolio.positions) >= self.config.max_concurrent_positions:
            logger.debug("Signal rejected: max positions reached")
            return None

        # Check if already have position in same symbol
        for pos in portfolio.positions:
            if pos.symbol == signal.symbol:
                logger.debug(f"Signal rejected: already have position in {signal.symbol}")
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
                    signal.confidence *= 0.8  # 20% penalty for correlated same-direction
                    logger.debug(f"Correlation penalty: {signal.symbol} same direction as {pos.symbol}")

        # Determine leverage based on confidence
        if signal.confidence >= 0.8:
            leverage = self.config.leverage_high_confidence
        elif signal.confidence >= 0.5:
            leverage = self.config.leverage_medium_confidence
        else:
            leverage = max(1, self.config.leverage_medium_confidence // 2)

        # Calculate position size based on risk
        risk_per_trade = portfolio.equity * self.config.max_risk_per_trade
        entry = signal.entry_price
        stop = signal.stop_loss
        risk_distance = abs(entry - stop)

        if risk_distance == 0:
            logger.warning("Signal rejected: zero risk distance")
            return None

        # Position size in base currency
        quantity = risk_per_trade / risk_distance

        # Notional value check (Binance minimum ~$5)
        notional = quantity * entry
        if notional < 5.0:
            # Increase to minimum
            quantity = 5.0 / entry

        # Ensure we don't exceed available balance with leverage
        required_margin = (quantity * entry) / leverage
        if required_margin > portfolio.available_balance:
            quantity = (portfolio.available_balance * leverage) / entry * 0.95  # 5% buffer
            if quantity * entry < 5.0:
                logger.debug("Signal rejected: insufficient balance for minimum order")
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
        """Fast validation for altcoin lag strategy - skips some checks."""
        return self.validate(signal, portfolio)
