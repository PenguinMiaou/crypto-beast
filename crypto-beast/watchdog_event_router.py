"""Event classification and L1 auto-fix handlers."""
import re
import subprocess
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple
from loguru import logger


class EventLevel(Enum):
    IGNORE = "ignore"
    L1 = "L1"
    L2 = "L2"


# Known log patterns -> (regex, category, L1 action)
KNOWN_PATTERNS = [
    (r"disk I/O error", "zombie_db_lock", "kill_zombies_restart"),
    (r"ConnectionError|Timeout|ECONNRESET", "network_transient", "wait_and_retry"),
    (r"Margin is insufficient", "margin_warning", "notify_only"),
    (r"HALT.*daily loss", "emergency_halt", "notify_only"),
    (r"Rate limit|429", "rate_limit", "notify_only"),
    (r"cancelAllOrders.*requires a symbol", "known_bug", "ignore"),
    (r"API latency critical", "high_latency", "notify_only"),
    (r"Trading cycle error", "cycle_error", "notify_only"),
    (r"Recovery state changed", "recovery_state", "notify_only"),
    (r"Failed to cancel orders", "cancel_orders_fail", "notify_only"),
    (r"Failed to fetch positions", "fetch_positions_fail", "notify_only"),
]

# Known Binance error codes that are operational, not bugs
KNOWN_BINANCE_ERRORS = {
    "-4120", "-4061", "-4164", "-2019", "-1015", "-1021",
}


class EventRouter:
    """Classify log events and execute L1 auto-fix actions."""

    def __init__(self, telegram, state, max_restarts: int = 3,
                 restart_window: int = 600):
        self._telegram = telegram
        self._state = state
        self._max_restarts = max_restarts
        self._restart_window = restart_window
        self._restart_times: List[float] = []
        self._l2_cooldowns: Dict[str, float] = {}  # error_key -> last_trigger_time
        self._cooldown_seconds = 3600  # 1 hour

    def should_escalate_l2(self, error_key: str) -> bool:
        """Check if this error type can be escalated (1/hour cooldown)."""
        import time as _time
        now = _time.time()
        last = self._l2_cooldowns.get(error_key, 0)
        if now - last < self._cooldown_seconds:
            return False
        self._l2_cooldowns[error_key] = now
        return True

    def classify(self, log_line: str) -> Tuple[EventLevel, str]:
        """Classify a log line into event level and action."""
        is_error = bool(re.search(r"\bERROR\b|\bCRITICAL\b", log_line))
        is_warning = bool(re.search(r"\bWARNING\b", log_line))

        if not is_error and not is_warning:
            return EventLevel.IGNORE, "none"

        for pattern, category, action in KNOWN_PATTERNS:
            if re.search(pattern, log_line):
                return EventLevel.L1, action

        # Check for known Binance error codes
        for code in KNOWN_BINANCE_ERRORS:
            if code in log_line:
                return EventLevel.L1, "notify_only"

        if is_error:
            return EventLevel.L2, "claude_fix"

        return EventLevel.IGNORE, "none"

    def record_restart(self) -> None:
        self._restart_times.append(time.time())

    def restart_limit_exceeded(self) -> bool:
        now = time.time()
        self._restart_times = [
            t for t in self._restart_times
            if now - t < self._restart_window
        ]
        return len(self._restart_times) >= self._max_restarts

    def handle_l1(self, action: str, context: str) -> Optional[str]:
        """Execute an L1 action. Returns result description or None."""
        if action == "ignore":
            return None

        if action == "notify_only":
            self._telegram.send(f"[L1] {context}")
            self._state.add_event("L1", context)
            return "notified"

        if action == "kill_zombies_restart":
            killed = self.kill_zombie_processes("crypto_system")
            msg = f"Killed {killed} zombie process(es), requesting restart"
            self._telegram.send(f"[L1] {context} — {msg}")
            self._state.add_event("L1", f"{context} — {msg}")
            return "restart_needed"

        if action == "wait_and_retry":
            self._state.add_event("L1", f"Network issue: {context}")
            return "transient"

        return None

    @staticmethod
    def kill_zombie_processes(process_name: str) -> int:
        """Kill duplicate processes matching name. Returns count killed."""
        try:
            result = subprocess.run(
                ["pgrep", "-f", process_name],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
            if len(pids) <= 1:
                return 0
            killed = 0
            for pid in pids[:-1]:
                try:
                    subprocess.run(["kill", "-9", pid], timeout=5)
                    killed += 1
                except Exception:
                    pass
            return killed
        except Exception as e:
            logger.error(f"Failed to kill zombies: {e}")
            return 0
