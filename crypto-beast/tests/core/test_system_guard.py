import pytest

from core.models import SystemStatus


class TestSystemGuard:
    def test_healthy_by_default(self):
        from core.system_guard import SystemGuard

        guard = SystemGuard()
        assert guard.check() == SystemStatus.HEALTHY
        assert guard.should_trade() is True

    def test_degraded_on_module_failure(self):
        from core.system_guard import SystemGuard

        guard = SystemGuard()
        guard.report_module_status("whale_tracker", False)
        assert guard.check() == SystemStatus.DEGRADED
        assert guard.should_trade() is True  # Still trades with non-critical modules down

    def test_critical_on_core_module_failure(self):
        from core.system_guard import SystemGuard

        guard = SystemGuard()
        guard.report_module_status("data_feed", False)
        assert guard.check() == SystemStatus.CRITICAL
        assert guard.should_trade() is False

    def test_high_latency_warning(self):
        from core.system_guard import SystemGuard

        guard = SystemGuard()
        guard.update_latency(1500)
        assert guard.check() == SystemStatus.DEGRADED

    def test_critical_latency(self):
        from core.system_guard import SystemGuard

        guard = SystemGuard()
        guard.update_latency(3000)
        assert guard.check() == SystemStatus.CRITICAL
        assert guard.should_trade() is False
