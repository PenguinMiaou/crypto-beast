from loguru import logger

from config import Config
from core.models import Portfolio, RecoveryState


class RecoveryMode:
    PARAMS = {
        RecoveryState.NORMAL:   {"max_leverage": 10, "min_confidence": 0.5, "mtf_min_score": 6},
        RecoveryState.CAUTIOUS: {"max_leverage": 3,  "min_confidence": 0.75, "mtf_min_score": 7},
        RecoveryState.RECOVERY: {"max_leverage": 2,  "min_confidence": 0.8, "mtf_min_score": 8},
        RecoveryState.CRITICAL: {"max_leverage": 1,  "min_confidence": 0.9, "mtf_min_score": 9},
    }

    def __init__(self, config: Config):
        self.config = config
        self._current_state = RecoveryState.NORMAL

    def assess_state(self, portfolio: Portfolio) -> RecoveryState:
        dd = portfolio.drawdown_pct
        if dd >= self.config.recovery_critical:
            new_state = RecoveryState.CRITICAL
        elif dd >= self.config.recovery_recovery:
            new_state = RecoveryState.RECOVERY
        elif dd >= self.config.recovery_cautious:
            new_state = RecoveryState.CAUTIOUS
        else:
            new_state = RecoveryState.NORMAL

        if new_state != self._current_state:
            logger.warning(f"Recovery state changed: {self._current_state.value} -> {new_state.value} (dd={dd:.1%})")
            self._current_state = new_state

        return self._current_state

    def get_adjusted_params(self) -> dict:
        return self.PARAMS[self._current_state].copy()

    @property
    def current_state(self) -> RecoveryState:
        return self._current_state
