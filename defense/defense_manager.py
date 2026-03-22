"""Unified defense: combines recovery mode + emergency shield into single state machine."""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from loguru import logger

from config import Config
from core.models import Portfolio, RecoveryState, ShieldAction


@dataclass
class DefenseResult:
    """Result of defense check — action to take + adjusted trading params."""
    action: ShieldAction
    recovery_state: RecoveryState
    params: Dict[str, object]


# Relaxed params for small accounts (vs old: NORMAL 0.5/6, CAUTIOUS 0.75/3/7, RECOVERY 0.8/2/8, CRITICAL 0.9/1/9)
RECOVERY_PARAMS: Dict[RecoveryState, Dict[str, object]] = {
    RecoveryState.NORMAL:   {"max_leverage": 7, "min_confidence": 0.4, "mtf_min_score": 5},
    RecoveryState.CAUTIOUS: {"max_leverage": 7, "min_confidence": 0.4, "mtf_min_score": 5},
    RecoveryState.RECOVERY: {"max_leverage": 5,  "min_confidence": 0.5, "mtf_min_score": 6},
    RecoveryState.CRITICAL: {"max_leverage": 3,  "min_confidence": 0.6, "mtf_min_score": 7},
}


class DefenseManager:
    """Unified defense state machine replacing RecoveryMode + EmergencyShield."""
    LOG_INTERVAL_HOURS = 6
    _STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "shield.state")

    def __init__(self, config: Config):
        self.config = config
        self._recovery_state = RecoveryState.NORMAL
        self._halted = False
        self._cooldown_until: Optional[datetime] = None
        self._last_action: Optional[ShieldAction] = None
        self._just_resumed = False
        self._last_log_time: Optional[datetime] = None
        self._load_state()

    def check(self, portfolio: Portfolio) -> DefenseResult:
        """Run full defense check: emergency → halt → recovery state."""
        now = datetime.now(timezone.utc)

        # 1. Total drawdown → EMERGENCY_CLOSE
        if portfolio.drawdown_pct >= self.config.max_total_drawdown:
            self._halted = True
            self._cooldown_until = None
            self._save_state()
            logger.critical(
                f"EMERGENCY CLOSE: drawdown {portfolio.drawdown_pct:.1%} >= {self.config.max_total_drawdown:.1%}"
            )
            if self._last_action != ShieldAction.EMERGENCY_CLOSE:
                self._last_action = ShieldAction.EMERGENCY_CLOSE
                return DefenseResult(ShieldAction.EMERGENCY_CLOSE, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL].copy())
            return DefenseResult(ShieldAction.ALREADY_NOTIFIED, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL].copy())

        # 2. Daily loss → HALT (configurable hours, default 8h)
        daily_loss_pct = abs(portfolio.daily_pnl) / max(portfolio.peak_equity, 1.0)
        if portfolio.daily_pnl < 0 and daily_loss_pct >= self.config.max_daily_loss:
            if not self._halted:
                self._halted = True
                self._cooldown_until = now + timedelta(hours=self.config.halt_cooldown_hours)
                self._save_state()
            # Log every 6 hours
            if self._last_log_time is None or (now - self._last_log_time).total_seconds() >= self.LOG_INTERVAL_HOURS * 3600:
                self._last_log_time = now
                resume_str = self._cooldown_until.strftime("%H:%M UTC") if self._cooldown_until else "manual reset"
                logger.warning(f"HALT: daily loss {daily_loss_pct:.1%}. Resumes at {resume_str}")
            if self._last_action != ShieldAction.HALT:
                self._last_action = ShieldAction.HALT
                return DefenseResult(ShieldAction.HALT, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL].copy())
            return DefenseResult(ShieldAction.ALREADY_NOTIFIED, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL].copy())

        # 3. Recovery state based on drawdown
        dd = portfolio.drawdown_pct
        if dd >= self.config.recovery_critical:
            new_state = RecoveryState.CRITICAL
        elif dd >= self.config.recovery_recovery:
            new_state = RecoveryState.RECOVERY
        elif dd >= self.config.recovery_cautious:
            new_state = RecoveryState.CAUTIOUS
        else:
            new_state = RecoveryState.NORMAL

        if new_state != self._recovery_state:
            logger.warning(f"Defense state: {self._recovery_state.value} -> {new_state.value} (dd={dd:.1%})")
            self._recovery_state = new_state

        self._last_action = None
        return DefenseResult(ShieldAction.CONTINUE, self._recovery_state, RECOVERY_PARAMS[self._recovery_state].copy())

    def is_halted(self) -> bool:
        """Check if currently in HALT or EMERGENCY state."""
        return self._halted

    def is_in_cooldown(self) -> bool:
        """Check if still in cooldown period. Auto-clears when cooldown expires."""
        if not self._halted:
            return False
        if self._cooldown_until is None:
            return True  # Requires manual reset
        if datetime.now(timezone.utc) < self._cooldown_until:
            return True
        # Cooldown expired
        self._halted = False
        self._cooldown_until = None
        self._last_action = None
        self._just_resumed = True
        self._save_state()
        return False

    def pop_just_resumed(self) -> bool:
        """Returns True once (and resets) when cooldown just expired — for resume notification."""
        if self._just_resumed:
            self._just_resumed = False
            return True
        return False

    def reset(self) -> None:
        """Manual reset of all defense state."""
        self._halted = False
        self._cooldown_until = None
        self._last_action = None
        self._last_log_time = None
        self._just_resumed = True
        self._recovery_state = RecoveryState.NORMAL
        self._save_state()
        logger.info("Defense manager reset manually")

    @property
    def current_state(self) -> RecoveryState:
        return self._recovery_state

    def _save_state(self) -> None:
        """Persist HALT state to disk so restarts don't clear it."""
        state = {
            "halted": self._halted,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "last_action": self._last_action.value if self._last_action else None,
        }
        try:
            with open(self._STATE_FILE, "w") as f:
                json.dump(state, f)
            logger.debug(f"Shield state saved to {self._STATE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save shield state: {e}")

    def _load_state(self) -> None:
        """Load HALT state from disk on startup."""
        try:
            if os.path.exists(self._STATE_FILE):
                with open(self._STATE_FILE) as f:
                    state = json.load(f)
                self._halted = state.get("halted", False)
                cd = state.get("cooldown_until")
                if cd:
                    self._cooldown_until = datetime.fromisoformat(cd)
                    if datetime.now(timezone.utc) >= self._cooldown_until:
                        self._halted = False
                        self._cooldown_until = None
                        self._just_resumed = True
                la = state.get("last_action")
                if la:
                    self._last_action = ShieldAction(la)
                if self._halted:
                    logger.warning(f"HALT state restored from disk (cooldown={self._cooldown_until})")
        except Exception as e:
            logger.debug(f"Failed to load shield state: {e}")
