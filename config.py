import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    # Capital
    starting_capital: float = 100.0

    # Leverage
    max_leverage: int = 10
    leverage_high_confidence: int = 10
    leverage_medium_confidence: int = 5

    # Risk
    max_risk_per_trade: float = 0.03
    max_concurrent_positions: int = 3
    max_daily_loss: float = 0.10
    max_total_drawdown: float = 0.30
    circuit_breaker_pct: float = 0.85  # Emergency close if wallet < 85% of peak wallet
    max_directional_leverage: float = 15.0
    max_correlated_same_dir: int = 2
    correlation_penalty: float = 0.6

    # Recovery thresholds
    recovery_cautious: float = 0.08
    recovery_recovery: float = 0.10
    recovery_critical: float = 0.20
    halt_cooldown_hours: int = 8

    # Fees
    maker_fee: float = 0.0002
    taker_fee: float = 0.0004
    daily_fee_budget: float = 0.005

    # Compound
    kelly_fraction: float = 0.5
    profit_lock_milestones: dict = field(default_factory=lambda: {150: 20, 200: 50, 500: 150})

    # Intelligence thresholds
    whale_trade_threshold: float = 100000.0  # $100k
    fear_greed_bullish: int = 20  # Below = extreme fear (contrarian buy)
    fear_greed_bearish: int = 80  # Above = extreme greed (contrarian sell)
    cascade_multiplier: float = 2.0
    orderbook_imbalance_bullish: float = 1.5
    orderbook_imbalance_bearish: float = 0.67

    # Funding rate
    funding_rate_extreme: float = 0.001  # 0.1% per 8h

    # Pattern detection
    pattern_min_confidence: float = 0.5

    # MultiTimeframe
    mtf_min_confluence: int = 4

    # Profit protection
    profit_protect_activation_pct: float = 0.08   # Activate after 8% leveraged PnL
    profit_protect_drawback_pct: float = 0.35      # Close if 35% of peak profit given back
    breakeven_sl_threshold: float = 0.05           # Move SL to breakeven when leveraged PnL > 5%

    # Position timeout
    position_timeout_hours: int = 48
    timeout_pnl_min: float = -0.01
    timeout_pnl_max: float = 0.02

    # System
    main_loop_interval: int = 5
    api_latency_warn: int = 3000
    api_latency_halt: int = 8000
    dashboard_port: int = 8080

    # Watchdog
    watchdog_heartbeat_interval: int = 30
    watchdog_frozen_threshold: int = 300
    watchdog_max_restarts: int = 3
    watchdog_restart_window: int = 600
    watchdog_claude_cooldown: int = 3600
    watchdog_daily_claude_budget: int = 3
    watchdog_review_hour: int = 0
    watchdog_review_minute: int = 30
    watchdog_event_queue_max: int = 5

    # Credentials (loaded from .env)
    binance_api_key: str = ""
    binance_api_secret: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    trading_mode: str = "paper"

    def __init__(self, env_path: str = ".env"):
        import dataclasses
        # Set all defaults from field definitions
        for f in fields(self.__class__):
            if f.default is not dataclasses.MISSING:
                setattr(self, f.name, f.default)
            elif f.default_factory is not dataclasses.MISSING:
                setattr(self, f.name, f.default_factory())

        # Load environment variables
        if Path(env_path).exists():
            load_dotenv(env_path)
        self.binance_api_key = os.getenv("BINANCE_API_KEY", "")
        self.binance_api_secret = os.getenv("BINANCE_API_SECRET", "")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.trading_mode = os.getenv("TRADING_MODE", "paper")

    def apply_overrides(self, overrides: dict) -> None:
        for key, value in overrides.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def save_overrides(self, path: str) -> None:
        """Save non-default, non-credential fields to JSON."""
        import dataclasses as dc
        defaults = Config.__new__(Config)
        for f in fields(self.__class__):
            if f.default is not dc.MISSING:
                setattr(defaults, f.name, f.default)
            else:
                setattr(defaults, f.name, f.default_factory())

        overrides = {}
        skip = {"binance_api_key", "binance_api_secret", "telegram_bot_token", "telegram_chat_id", "trading_mode"}
        for f in fields(self.__class__):
            if f.name in skip:
                continue
            current = getattr(self, f.name)
            default = getattr(defaults, f.name)
            if current != default:
                overrides[f.name] = current

        Path(path).write_text(json.dumps(overrides, indent=2))

    def load_overrides(self, path: str) -> None:
        if Path(path).exists():
            overrides = json.loads(Path(path).read_text())
            self.apply_overrides(overrides)
