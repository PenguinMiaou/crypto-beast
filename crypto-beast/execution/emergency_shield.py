from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from config import Config
from core.models import Portfolio, ShieldAction


class EmergencyShield:
    def __init__(self, config: Config):
        self.config = config
        self._cooldown_until: Optional[datetime] = None
        self._halted = False

    def check(self, portfolio: Portfolio) -> ShieldAction:
        # Check total drawdown first (most severe)
        if portfolio.drawdown_pct >= self.config.max_total_drawdown:
            self._halted = True
            self._cooldown_until = None  # Requires manual reset
            logger.critical(
                f"EMERGENCY CLOSE: drawdown {portfolio.drawdown_pct:.1%} >= {self.config.max_total_drawdown:.1%}"
            )
            return ShieldAction.EMERGENCY_CLOSE

        # Check daily loss
        daily_loss_pct = abs(portfolio.daily_pnl) / max(portfolio.peak_equity, 1.0)
        if portfolio.daily_pnl < 0 and daily_loss_pct >= self.config.max_daily_loss:
            self._halted = True
            self._cooldown_until = datetime.utcnow() + timedelta(hours=24)
            logger.warning(
                f"HALT: daily loss {daily_loss_pct:.1%} >= {self.config.max_daily_loss:.1%}. "
                f"Cooldown until {self._cooldown_until}"
            )
            return ShieldAction.HALT

        return ShieldAction.CONTINUE

    def is_in_cooldown(self) -> bool:
        if not self._halted:
            return False
        if self._cooldown_until is None:
            return True  # Requires manual reset
        if datetime.utcnow() < self._cooldown_until:
            return True
        # Cooldown expired
        self._halted = False
        self._cooldown_until = None
        return False

    def reset(self) -> None:
        self._halted = False
        self._cooldown_until = None
        logger.info("Emergency shield reset manually")
