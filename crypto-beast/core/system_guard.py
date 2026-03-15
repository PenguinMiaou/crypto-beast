from typing import Dict

from loguru import logger

from core.models import SystemStatus


class SystemGuard:
    CORE_MODULES = {"data_feed", "executor", "risk_manager", "emergency_shield"}

    def __init__(self, latency_warn: int = 500, latency_halt: int = 2000):
        self._module_status: Dict[str, bool] = {}
        self._api_latency_ms: float = 0.0
        self._latency_warn = latency_warn
        self._latency_halt = latency_halt

    def check(self) -> SystemStatus:
        # Check latency
        if self._api_latency_ms >= self._latency_halt:
            logger.critical(f"API latency critical: {self._api_latency_ms}ms")
            return SystemStatus.CRITICAL

        # Check core modules
        for module in self.CORE_MODULES:
            if module in self._module_status and not self._module_status[module]:
                logger.critical(f"Core module down: {module}")
                return SystemStatus.CRITICAL

        # Check for any degradation
        if self._api_latency_ms >= self._latency_warn:
            return SystemStatus.DEGRADED

        for module, healthy in self._module_status.items():
            if not healthy and module not in self.CORE_MODULES:
                return SystemStatus.DEGRADED

        return SystemStatus.HEALTHY

    def should_trade(self) -> bool:
        return self.check() != SystemStatus.CRITICAL

    def report_module_status(self, module: str, healthy: bool) -> None:
        prev = self._module_status.get(module, True)
        self._module_status[module] = healthy
        if prev and not healthy:
            logger.warning(f"Module {module} reported unhealthy")
        elif not prev and healthy:
            logger.info(f"Module {module} recovered")

    def update_latency(self, latency_ms: float) -> None:
        self._api_latency_ms = latency_ms

    def get_status_report(self) -> dict:
        return {
            "status": self.check().value,
            "api_latency_ms": self._api_latency_ms,
            "modules": dict(self._module_status),
        }
