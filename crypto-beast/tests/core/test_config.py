import json
import os
from pathlib import Path


class TestConfig:
    def test_default_config_loads(self):
        from config import Config

        cfg = Config()
        assert cfg.starting_capital == 100.0
        assert cfg.max_leverage == 10
        assert cfg.max_risk_per_trade == 0.02
        assert cfg.main_loop_interval == 5

    def test_recovery_thresholds_ordered(self):
        from config import Config

        cfg = Config()
        assert cfg.recovery_cautious < cfg.recovery_recovery < cfg.recovery_critical < cfg.max_total_drawdown

    def test_override_from_dict(self):
        from config import Config

        cfg = Config()
        cfg.apply_overrides({"max_leverage": 5, "main_loop_interval": 10})
        assert cfg.max_leverage == 5
        assert cfg.main_loop_interval == 10

    def test_save_and_load_overrides(self, tmp_path):
        from config import Config

        cfg = Config()
        cfg.apply_overrides({"max_leverage": 7})
        override_file = tmp_path / "overrides.json"
        cfg.save_overrides(str(override_file))

        cfg2 = Config()
        cfg2.load_overrides(str(override_file))
        assert cfg2.max_leverage == 7

    def test_env_loading(self, tmp_path, monkeypatch):
        from config import Config

        env_file = tmp_path / ".env"
        env_file.write_text("BINANCE_API_KEY=test_key\nBINANCE_API_SECRET=test_secret\nTRADING_MODE=paper\n")
        monkeypatch.chdir(tmp_path)
        # Clear real env vars so test .env takes effect
        monkeypatch.delenv("BINANCE_API_KEY", raising=False)
        monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
        monkeypatch.delenv("TRADING_MODE", raising=False)

        cfg = Config(env_path=str(env_file))
        assert cfg.binance_api_key == "test_key"
        assert cfg.trading_mode == "paper"


class TestWatchdogConfig:
    def test_watchdog_defaults(self):
        from config import Config

        config = Config()
        assert config.watchdog_heartbeat_interval == 30
        assert config.watchdog_frozen_threshold == 300
        assert config.watchdog_max_restarts == 3
        assert config.watchdog_restart_window == 600
        assert config.watchdog_claude_cooldown == 3600
        assert config.watchdog_daily_claude_budget == 3
        assert config.watchdog_review_hour == 0
        assert config.watchdog_review_minute == 30
        assert config.watchdog_event_queue_max == 5
