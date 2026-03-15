# Crypto Beast v1.0 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an autonomous, self-evolving crypto trading bot for Binance Futures that turns $100 into more through leveraged, multi-strategy trading with automated parameter optimization.

**Architecture:** Single Python asyncio process with 21 modules across 7 layers. Data flows bottom-up: DataFeed → Analysis → Strategy → Defense → Execution → Evolution → Monitoring. SQLite for persistence. ccxt for REST API, python-binance for WebSocket streams.

**Tech Stack:** Python 3.11+, asyncio, ccxt, python-binance, pandas, numpy, ta, optuna, streamlit, loguru, SQLite (WAL mode)

**Spec:** `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`

---

## File Structure

```
crypto-beast/
├── main.py                          # Entry point: arg parsing, main loop, shutdown
├── config.py                        # Config loading, defaults, Evolver overrides
├── requirements.txt                 # All Python dependencies
├── .env.example                     # API key template
├── .gitignore                       # Standard Python + .env
│
├── core/
│   ├── __init__.py
│   ├── models.py                    # All shared dataclasses and enums
│   ├── database.py                  # SQLite connection, WAL, write queue, schema init
│   ├── rate_limiter.py              # Centralized Binance API rate limiter
│   └── system_guard.py              # Health monitoring, module status tracking
│
├── data/
│   ├── __init__.py
│   ├── data_feed.py                 # WebSocket + REST market data
│   ├── whale_tracker.py             # Whale Alert + large trade detection
│   ├── sentiment_radar.py           # Fear & Greed, long/short ratio
│   ├── liquidation_hunter.py        # Forced liquidation stream
│   └── orderbook_sniper.py          # Order book depth analysis
│
├── analysis/
│   ├── __init__.py
│   ├── market_regime.py             # ADX/BB/MA regime classification
│   ├── event_engine.py              # Macro/crypto event calendar
│   ├── altcoin_radar.py             # Coin selection + BTC-alt lag
│   ├── pattern_scanner.py           # Chart pattern detection
│   ├── session_trader.py            # Trading session weights
│   └── multi_timeframe.py           # Confluence scoring across timeframes
│
├── strategy/
│   ├── __init__.py
│   ├── base_strategy.py             # Abstract base class for all strategies
│   ├── trend_follower.py            # EMA crossover + pullback
│   ├── mean_reversion.py            # Bollinger + RSI
│   ├── momentum.py                  # MACD momentum
│   ├── breakout.py                  # BB squeeze breakout
│   ├── scalper.py                   # RSI(2) scalping
│   ├── strategy_engine.py           # Multi-strategy orchestrator
│   └── funding_rate_arb.py          # Funding rate capture
│
├── defense/
│   ├── __init__.py
│   ├── anti_trap.py                 # False signal filtering
│   ├── risk_manager.py              # Position sizing, stops, portfolio risk
│   └── fee_optimizer.py             # Maker/taker optimization, fee budget
│
├── execution/
│   ├── __init__.py
│   ├── smart_order.py               # Tranched entry/exit planning
│   ├── executor.py                  # Live Binance order execution
│   ├── paper_executor.py            # Simulated execution for testing
│   ├── emergency_shield.py          # Last-resort loss protection
│   └── recovery_mode.py             # Drawdown-adaptive behavior
│
├── evolution/
│   ├── __init__.py
│   ├── compound_engine.py           # Kelly criterion, profit locking
│   ├── evolver.py                   # Parameter optimization
│   ├── backtest_lab.py              # Walk-forward, Monte Carlo
│   └── trade_reviewer.py            # Post-trade analysis
│
├── monitoring/
│   ├── __init__.py
│   ├── monitor.py                   # Streamlit dashboard
│   └── notifier.py                  # Telegram + macOS notifications
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared fixtures (sample data, mock exchange)
    ├── core/
    │   ├── __init__.py
    │   ├── test_models.py
    │   ├── test_database.py
    │   └── test_rate_limiter.py
    ├── data/
    │   ├── __init__.py
    │   └── test_data_feed.py
    ├── analysis/
    │   ├── __init__.py
    │   ├── test_market_regime.py
    │   ├── test_multi_timeframe.py
    │   └── test_session_trader.py
    ├── strategy/
    │   ├── __init__.py
    │   ├── test_trend_follower.py
    │   ├── test_mean_reversion.py
    │   ├── test_strategy_engine.py
    │   └── test_funding_rate_arb.py
    ├── defense/
    │   ├── __init__.py
    │   ├── test_anti_trap.py
    │   ├── test_risk_manager.py
    │   └── test_fee_optimizer.py
    ├── execution/
    │   ├── __init__.py
    │   ├── test_executor.py
    │   ├── test_paper_executor.py
    │   ├── test_emergency_shield.py
    │   └── test_recovery_mode.py
    ├── evolution/
    │   ├── __init__.py
    │   ├── test_compound_engine.py
    │   ├── test_backtest_lab.py
    │   └── test_trade_reviewer.py
    └── integration/
        ├── __init__.py
        ├── test_pipeline.py         # Full signal-to-execution pipeline
        └── test_paper_trading.py    # End-to-end paper trading
```

---

## Chunk 1: Foundation (Tasks 1-5)

This chunk builds the core infrastructure everything else depends on: models, config, database, rate limiter, and project scaffolding.

### Task 1: Project Scaffolding

**Files:**
- Create: `crypto-beast/requirements.txt`
- Create: `crypto-beast/.env.example`
- Create: `crypto-beast/.gitignore`
- Create: all `__init__.py` files

- [ ] **Step 1: Create project directory and requirements.txt**

```
crypto-beast/requirements.txt:
```
```txt
# Core exchange libraries
ccxt>=4.0.0
python-binance>=1.0.0

# Data & analysis
pandas>=2.0.0
numpy>=1.24.0
ta>=0.11.0

# Optimization
scipy>=1.11.0
optuna>=3.4.0

# Dashboard
streamlit>=1.30.0

# Notifications
python-telegram-bot>=20.0.0

# Utilities
python-dotenv>=1.0.0
schedule>=1.2.0
aiohttp>=3.9.0
websockets>=12.0
loguru>=0.7.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
```

- [ ] **Step 2: Create .env.example**

```
crypto-beast/.env.example:
```
```env
# Binance API (Futures enabled, Withdrawals DISABLED, IP restricted)
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here

# Telegram notifications (optional)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Mode: "paper" or "live"
TRADING_MODE=paper
```

- [ ] **Step 3: Create .gitignore**

```
crypto-beast/.gitignore:
```
```gitignore
# Environment
.env
.venv/
venv/

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/

# Database
*.db
backups/

# Logs
logs/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
```

- [ ] **Step 4: Create all __init__.py files**

Create empty `__init__.py` in: `core/`, `data/`, `analysis/`, `strategy/`, `defense/`, `execution/`, `evolution/`, `monitoring/`, `tests/`, `tests/core/`, `tests/data/`, `tests/analysis/`, `tests/strategy/`, `tests/defense/`, `tests/execution/`, `tests/evolution/`, `tests/integration/`

- [ ] **Step 5: Initialize virtual environment and install dependencies**

Run:
```bash
cd crypto-beast
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: project scaffolding with dependencies and directory structure"
```

---

### Task 2: Shared Data Models (core/models.py)

**Files:**
- Create: `crypto-beast/core/models.py`
- Create: `crypto-beast/tests/core/test_models.py`

- [ ] **Step 1: Write tests for all model types**

```python
# tests/core/test_models.py
from datetime import datetime

from core.models import (
    ConfluenceScore,
    Direction,
    DirectionalBias,
    ExecutionPlan,
    ExecutionResult,
    LossCategory,
    LossClassification,
    MarketRegime,
    OrderBook,
    OrderType,
    Portfolio,
    Position,
    PositionSizing,
    RecoveryState,
    ReviewReport,
    ShieldAction,
    SignalType,
    SystemStatus,
    TradeSignal,
    ValidatedOrder,
    WinProfile,
)


class TestEnums:
    def test_direction_values(self):
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"

    def test_signal_type_values(self):
        assert SignalType.BULLISH.value == "BULLISH"
        assert SignalType.BEARISH.value == "BEARISH"
        assert SignalType.NEUTRAL.value == "NEUTRAL"

    def test_market_regime_has_all_states(self):
        regimes = [r.value for r in MarketRegime]
        assert "TRENDING_UP" in regimes
        assert "TRENDING_DOWN" in regimes
        assert "RANGING" in regimes
        assert "HIGH_VOLATILITY" in regimes
        assert "LOW_VOLATILITY" in regimes

    def test_recovery_state_order(self):
        states = list(RecoveryState)
        assert states == [
            RecoveryState.NORMAL,
            RecoveryState.CAUTIOUS,
            RecoveryState.RECOVERY,
            RecoveryState.CRITICAL,
        ]

    def test_loss_category_has_all_types(self):
        cats = [c.value for c in LossCategory]
        assert len(cats) == 8
        assert "STOP_TOO_TIGHT" in cats
        assert "FEE_EROSION" in cats


class TestDirectionalBias:
    def test_create_bias(self):
        bias = DirectionalBias(
            source="whale_tracker",
            symbol="BTCUSDT",
            direction=SignalType.BULLISH,
            confidence=0.8,
            reason="Large withdrawal detected",
        )
        assert bias.source == "whale_tracker"
        assert bias.confidence == 0.8
        assert isinstance(bias.timestamp, datetime)


class TestTradeSignal:
    def test_create_signal(self):
        signal = TradeSignal(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            confidence=0.85,
            entry_price=65000.0,
            stop_loss=64000.0,
            take_profit=67000.0,
            strategy="trend_follower",
            regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )
        assert signal.symbol == "BTCUSDT"
        assert signal.direction == Direction.LONG
        assert signal.confidence == 0.85


class TestValidatedOrder:
    def test_create_order(self):
        signal = TradeSignal(
            symbol="BTCUSDT",
            direction=Direction.LONG,
            confidence=0.85,
            entry_price=65000.0,
            stop_loss=64000.0,
            take_profit=67000.0,
            strategy="trend_follower",
            regime=MarketRegime.TRENDING_UP,
            timeframe_score=8,
        )
        order = ValidatedOrder(
            signal=signal,
            quantity=0.001,
            leverage=10,
            order_type=OrderType.LIMIT,
            risk_amount=2.0,
            max_slippage=0.001,
        )
        assert order.leverage == 10
        assert order.risk_amount == 2.0


class TestPortfolio:
    def test_create_portfolio(self):
        portfolio = Portfolio(
            equity=100.0,
            available_balance=80.0,
            positions=[],
            peak_equity=100.0,
            locked_capital=0.0,
            daily_pnl=0.0,
            total_fees_today=0.0,
            drawdown_pct=0.0,
        )
        assert portfolio.equity == 100.0
        assert portfolio.drawdown_pct == 0.0


class TestReviewReport:
    def test_create_review(self):
        report = ReviewReport(
            period="daily",
            timestamp=datetime.utcnow(),
            total_trades=10,
            wins=6,
            losses=4,
            loss_classifications=[],
            win_profiles=[],
            recommendations=["widen stops"],
            hypothetical_results={"confluence_8": 150.0},
        )
        assert report.wins == 6
        assert report.recommendations == ["widen stops"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/core/test_models.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'core')

- [ ] **Step 3: Implement models.py**

Copy the full models definition from the spec (Appendix A: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md` lines 1312-1551). This includes all enums (`Direction`, `SignalType`, `MarketRegime`, `RecoveryState`, `SystemStatus`, `ShieldAction`, `OrderType`, `LossCategory`) and all dataclasses (`DirectionalBias`, `TradeSignal`, `ValidatedOrder`, `ExecutionPlan`, `ExecutionResult`, `Position`, `Portfolio`, `PositionSizing`, `ConfluenceScore`, `Pattern`, `MarketData`, `OrderBook`, `LossClassification`, `WinProfile`, `ReviewReport`, `SystemState`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/core/test_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/models.py tests/core/test_models.py
git commit -m "feat: add shared data models for all system types"
```

---

### Task 3: Configuration (config.py)

**Files:**
- Create: `crypto-beast/config.py`
- Create: `crypto-beast/tests/core/test_config.py`

- [ ] **Step 1: Write tests**

```python
# tests/core/test_config.py
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

    def test_capital_allocation(self):
        from config import Config

        cfg = Config()
        assert cfg.capital_allocation["BTC"] == 0.6
        assert cfg.capital_allocation["altcoins"] == 0.4

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

        cfg = Config(env_path=str(env_file))
        assert cfg.binance_api_key == "test_key"
        assert cfg.trading_mode == "paper"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/core/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config.py**

```python
# config.py
import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    # Capital
    starting_capital: float = 100.0
    capital_allocation: dict = field(default_factory=lambda: {"BTC": 0.6, "altcoins": 0.4})

    # Leverage
    max_leverage: int = 10
    leverage_high_confidence: int = 10
    leverage_medium_confidence: int = 5

    # Risk
    max_risk_per_trade: float = 0.02
    max_concurrent_positions: int = 3
    max_daily_loss: float = 0.10
    max_total_drawdown: float = 0.30

    # Recovery thresholds
    recovery_cautious: float = 0.05
    recovery_recovery: float = 0.10
    recovery_critical: float = 0.20

    # Fees
    maker_fee: float = 0.0002
    taker_fee: float = 0.0004
    daily_fee_budget: float = 0.005

    # Evolution
    evolution_time_utc: str = "00:00"
    backtest_train_days: int = 30
    backtest_test_days: int = 7
    max_param_change_pct: float = 0.20

    # Compound
    kelly_fraction: float = 0.5
    profit_lock_milestones: dict = field(default_factory=lambda: {150: 20, 200: 50, 500: 150})

    # MultiTimeframe
    mtf_min_confluence: int = 6

    # System
    main_loop_interval: int = 5
    api_latency_warn: int = 500
    api_latency_halt: int = 2000
    dashboard_port: int = 8080

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
        defaults = Config.__new__(Config)
        for f in fields(self.__class__):
            if f.default is not f.MISSING:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/core/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add config.py tests/core/test_config.py
git commit -m "feat: add configuration management with env loading and override persistence"
```

---

### Task 4: Database (core/database.py)

**Files:**
- Create: `crypto-beast/core/database.py`
- Create: `crypto-beast/tests/core/test_database.py`

- [ ] **Step 1: Write tests**

```python
# tests/core/test_database.py
import asyncio
from datetime import datetime

import pytest
import pytest_asyncio


@pytest.fixture
def db(tmp_path):
    from core.database import Database

    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    database.initialize()
    return database


class TestDatabase:
    def test_initialize_creates_tables(self, db):
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = [t[0] for t in tables]
        assert "trades" in table_names
        assert "equity_snapshots" in table_names
        assert "strategy_performance" in table_names
        assert "evolution_log" in table_names
        assert "klines" in table_names
        assert "whale_events" in table_names
        assert "trade_reviews" in table_names
        assert "review_reports" in table_names
        assert "system_health" in table_names

    def test_wal_mode_enabled(self, db):
        result = db.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"

    def test_insert_and_query_trade(self, db):
        db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("BTCUSDT", "LONG", 65000.0, 0.001, 10, "trend_follower", datetime.utcnow().isoformat(), "OPEN"),
        )
        trades = db.execute("SELECT * FROM trades").fetchall()
        assert len(trades) == 1
        assert trades[0][1] == "BTCUSDT"

    def test_insert_equity_snapshot(self, db):
        db.execute(
            "INSERT INTO equity_snapshots (timestamp, equity, unrealized_pnl) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), 100.0, 0.0),
        )
        snaps = db.execute("SELECT * FROM equity_snapshots").fetchall()
        assert len(snaps) == 1

    def test_backup(self, db, tmp_path):
        db.execute(
            "INSERT INTO equity_snapshots (timestamp, equity, unrealized_pnl) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), 100.0, 0.0),
        )
        backup_path = str(tmp_path / "backup.db")
        db.backup(backup_path)
        from core.database import Database

        backup_db = Database(backup_path)
        snaps = backup_db.execute("SELECT * FROM equity_snapshots").fetchall()
        assert len(snaps) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/core/test_database.py -v`
Expected: FAIL

- [ ] **Step 3: Implement database.py**

```python
# core/database.py
import shutil
import sqlite3
import threading
from pathlib import Path

from loguru import logger


class Database:
    def __init__(self, db_path: str = "crypto_beast.db"):
        self.db_path = db_path
        self._local = threading.local()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity REAL NOT NULL,
            leverage INTEGER NOT NULL,
            strategy TEXT NOT NULL,
            entry_time TIMESTAMP NOT NULL,
            exit_time TIMESTAMP,
            pnl REAL,
            fees REAL,
            status TEXT DEFAULT 'OPEN'
        );

        CREATE TABLE IF NOT EXISTS equity_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            equity REAL NOT NULL,
            unrealized_pnl REAL,
            locked_capital REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS strategy_performance (
            id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL,
            date DATE NOT NULL,
            trades INTEGER,
            wins INTEGER,
            total_pnl REAL,
            sharpe_ratio REAL,
            weight REAL
        );

        CREATE TABLE IF NOT EXISTS evolution_log (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            parameters_before JSON,
            parameters_after JSON,
            backtest_sharpe REAL,
            changes_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS klines (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            open_time TIMESTAMP NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        );

        CREATE TABLE IF NOT EXISTS whale_events (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            event_type TEXT,
            symbol TEXT,
            amount REAL,
            direction TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_reviews (
            id INTEGER PRIMARY KEY,
            trade_id INTEGER NOT NULL REFERENCES trades(id),
            review_date DATE NOT NULL,
            outcome TEXT NOT NULL,
            loss_category TEXT,
            classification_confidence REAL,
            evidence TEXT,
            recommendation TEXT,
            regime_at_entry TEXT,
            session_at_entry TEXT,
            confluence_at_entry INTEGER,
            capture_efficiency REAL
        );

        CREATE TABLE IF NOT EXISTS review_reports (
            id INTEGER PRIMARY KEY,
            period TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            total_trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            loss_distribution JSON,
            recommendations JSON,
            hypothetical_results JSON,
            report_text TEXT
        );

        CREATE TABLE IF NOT EXISTS system_health (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            status TEXT,
            api_latency_ms REAL,
            memory_mb REAL,
            active_modules INTEGER,
            details TEXT
        );
        """
        self._conn.executescript(schema)
        self._conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        cursor = self._conn.execute(query, params)
        if not query.strip().upper().startswith("SELECT"):
            self._conn.commit()
        return cursor

    def executemany(self, query: str, params_list: list[tuple]) -> None:
        self._conn.executemany(query, params_list)
        self._conn.commit()

    def backup(self, backup_path: str) -> None:
        backup_conn = sqlite3.connect(backup_path)
        self._conn.backup(backup_conn)
        backup_conn.close()
        logger.info(f"Database backed up to {backup_path}")

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/core/test_database.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/database.py tests/core/test_database.py
git commit -m "feat: add SQLite database with WAL mode and full schema"
```

---

### Task 5: Rate Limiter (core/rate_limiter.py)

**Files:**
- Create: `crypto-beast/core/rate_limiter.py`
- Create: `crypto-beast/tests/core/test_rate_limiter.py`

- [ ] **Step 1: Write tests**

```python
# tests/core/test_rate_limiter.py
import asyncio
import time

import pytest
import pytest_asyncio


@pytest.fixture
def limiter():
    from core.rate_limiter import BinanceRateLimiter

    return BinanceRateLimiter()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_data_slot_succeeds(self, limiter):
        result = await limiter.acquire_data_slot()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_order_slot_succeeds(self, limiter):
        result = await limiter.acquire_order_slot()
        assert result is True

    @pytest.mark.asyncio
    async def test_usage_tracking(self, limiter):
        await limiter.acquire_data_slot()
        await limiter.acquire_data_slot()
        await limiter.acquire_order_slot()
        usage = limiter.get_usage()
        assert usage["data_used"] == 2
        assert usage["order_used"] == 1

    @pytest.mark.asyncio
    async def test_data_limit_respected(self):
        from core.rate_limiter import BinanceRateLimiter

        limiter = BinanceRateLimiter(data_limit=5, order_limit=5, window_seconds=1)
        for _ in range(5):
            await limiter.acquire_data_slot()
        # 6th call should block briefly then succeed after window resets
        # We just test that usage is tracked correctly
        usage = limiter.get_usage()
        assert usage["data_used"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/core/test_rate_limiter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rate_limiter.py**

```python
# core/rate_limiter.py
import asyncio
import time
from collections import deque

from loguru import logger


class BinanceRateLimiter:
    def __init__(
        self,
        order_limit: int = 1200,
        data_limit: int = 2400,
        window_seconds: int = 60,
    ):
        self.order_limit = order_limit
        self.data_limit = data_limit
        self.window_seconds = window_seconds
        self._order_timestamps: deque[float] = deque()
        self._data_timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _clean_old(self, timestamps: deque[float]) -> None:
        cutoff = time.monotonic() - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    async def acquire_data_slot(self) -> bool:
        async with self._lock:
            self._clean_old(self._data_timestamps)
            if len(self._data_timestamps) >= self.data_limit:
                wait = self._data_timestamps[0] + self.window_seconds - time.monotonic()
                if wait > 0:
                    logger.warning(f"Data rate limit hit, waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    self._clean_old(self._data_timestamps)
            self._data_timestamps.append(time.monotonic())
            return True

    async def acquire_order_slot(self) -> bool:
        async with self._lock:
            self._clean_old(self._order_timestamps)
            if len(self._order_timestamps) >= self.order_limit:
                wait = self._order_timestamps[0] + self.window_seconds - time.monotonic()
                if wait > 0:
                    logger.warning(f"Order rate limit hit, waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    self._clean_old(self._order_timestamps)
            self._order_timestamps.append(time.monotonic())
            return True

    def get_usage(self) -> dict:
        self._clean_old(self._data_timestamps)
        self._clean_old(self._order_timestamps)
        return {
            "data_used": len(self._data_timestamps),
            "data_limit": self.data_limit,
            "order_used": len(self._order_timestamps),
            "order_limit": self.order_limit,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/core/test_rate_limiter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/rate_limiter.py tests/core/test_rate_limiter.py
git commit -m "feat: add centralized Binance API rate limiter"
```

---

## Chunk 2: Data Layer + First Strategy (Tasks 6-9)

This chunk gets market data flowing and implements the first tradeable strategy, creating the minimum viable signal pipeline.

### Task 6: DataFeed (data/data_feed.py)

**Files:**
- Create: `crypto-beast/data/data_feed.py`
- Create: `crypto-beast/tests/data/test_data_feed.py`
- Create: `crypto-beast/tests/conftest.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# tests/conftest.py
import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def sample_klines():
    """Generate realistic OHLCV data for testing."""
    np.random.seed(42)
    n = 500
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.cumsum(np.random.randn(n) * 100)
    high = close + np.abs(np.random.randn(n) * 50)
    low = close - np.abs(np.random.randn(n) * 50)
    open_ = np.clip(close + np.random.randn(n) * 30, low, high)  # Ensure open is between low and high
    volume = np.random.uniform(100, 1000, n)

    df = pd.DataFrame({
        "open_time": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    return df


@pytest.fixture
def sample_orderbook():
    """Generate a sample order book."""
    price = 65000.0
    bids = [[price - i * 0.5, np.random.uniform(0.1, 5.0)] for i in range(20)]
    asks = [[price + i * 0.5, np.random.uniform(0.1, 5.0)] for i in range(20)]
    return {"bids": bids, "asks": asks, "symbol": "BTCUSDT", "timestamp": datetime.utcnow()}


@pytest.fixture
def db(tmp_path):
    from core.database import Database
    db = Database(str(tmp_path / "test.db"))
    db.initialize()
    return db
```

- [ ] **Step 2: Write DataFeed tests**

```python
# tests/data/test_data_feed.py
import pytest
import pandas as pd
from unittest.mock import AsyncMock, MagicMock, patch


class TestDataFeed:
    def test_init(self):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m", "15m"])
        assert "BTCUSDT" in feed.symbols
        assert "5m" in feed.intervals

    def test_store_and_retrieve_klines(self, sample_klines):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        feed._cache["BTCUSDT"]["5m"] = sample_klines
        result = feed.get_klines("BTCUSDT", "5m", limit=100)
        assert len(result) == 100
        assert isinstance(result, pd.DataFrame)

    def test_get_klines_returns_latest(self, sample_klines):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        feed._cache["BTCUSDT"]["5m"] = sample_klines
        result = feed.get_klines("BTCUSDT", "5m", limit=10)
        # Should return the last 10 rows
        assert result.iloc[-1]["close"] == sample_klines.iloc[-1]["close"]

    def test_get_klines_unknown_symbol_returns_empty(self):
        from data.data_feed import DataFeed
        feed = DataFeed(symbols=["BTCUSDT"], intervals=["5m"])
        result = feed.get_klines("XYZUSDT", "5m", limit=10)
        assert len(result) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/data/test_data_feed.py -v`
Expected: FAIL

- [ ] **Step 4: Implement DataFeed**

```python
# data/data_feed.py
import asyncio
from collections import defaultdict
from datetime import datetime

import pandas as pd
from loguru import logger


class DataFeed:
    def __init__(self, symbols: list[str] = None, intervals: list[str] = None, rate_limiter=None):
        self.symbols = symbols or ["BTCUSDT"]
        self.intervals = intervals or ["5m", "15m", "1h", "4h"]
        self.rate_limiter = rate_limiter
        self._cache: dict[str, dict[str, pd.DataFrame]] = defaultdict(lambda: defaultdict(pd.DataFrame))
        self._connected = False

    async def connect(self) -> None:
        """Establish WebSocket connections for real-time data."""
        # Will be implemented with python-binance WebSocket
        # For now, use REST polling
        logger.info(f"DataFeed connecting for {self.symbols} on {self.intervals}")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("DataFeed disconnected")

    async def fetch_historical(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """Fetch historical klines via REST API."""
        if self.rate_limiter:
            await self.rate_limiter.acquire_data_slot()
        try:
            import ccxt.async_support as ccxt

            exchange = ccxt.binance({"options": {"defaultType": "future"}})
            timeframe_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}
            ohlcv = await exchange.fetch_ohlcv(
                symbol.replace("USDT", "/USDT"), timeframe_map[interval], limit=limit
            )
            await exchange.close()

            df = pd.DataFrame(ohlcv, columns=["open_time", "open", "high", "low", "close", "volume"])
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            self._cache[symbol][interval] = df
            return df
        except Exception as e:
            logger.error(f"Failed to fetch {symbol} {interval}: {e}")
            return pd.DataFrame()

    async def fetch(self) -> dict[str, dict[str, pd.DataFrame]]:
        """Fetch latest data for all symbols and intervals."""
        for symbol in self.symbols:
            for interval in self.intervals:
                await self.fetch_historical(symbol, interval)
        return dict(self._cache)

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """Get cached OHLCV data."""
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return pd.DataFrame()
        df = self._cache[symbol][interval]
        if len(df) == 0:
            return df
        return df.tail(limit).reset_index(drop=True)

    def get_current_price(self, symbol: str) -> float:
        """Get latest close price from cache."""
        df = self.get_klines(symbol, self.intervals[0], limit=1)
        if len(df) == 0:
            return 0.0
        return float(df.iloc[-1]["close"])

    def update_cache(self, symbol: str, interval: str, df: pd.DataFrame) -> None:
        """Manually update cache (used for testing and WebSocket updates)."""
        self._cache[symbol][interval] = df
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/data/test_data_feed.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add data/data_feed.py tests/data/test_data_feed.py tests/conftest.py
git commit -m "feat: add DataFeed with REST fetching and in-memory cache"
```

---

### Task 7: Base Strategy + TrendFollower

**Files:**
- Create: `crypto-beast/strategy/base_strategy.py`
- Create: `crypto-beast/strategy/trend_follower.py`
- Create: `crypto-beast/tests/strategy/test_trend_follower.py`

- [ ] **Step 1: Write tests**

```python
# tests/strategy/test_trend_follower.py
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from core.models import Direction, MarketRegime, TradeSignal


@pytest.fixture
def uptrend_data():
    """Create data with clear uptrend (price steadily increasing)."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.arange(n) * 50  # Steady uptrend
    high = close + 30
    low = close - 30
    open_ = close - 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def downtrend_data():
    """Create data with clear downtrend."""
    n = 100
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 - np.arange(n) * 50
    high = close + 30
    low = close - 30
    open_ = close + 10
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


@pytest.fixture
def sideways_data():
    """Create choppy sideways data."""
    n = 100
    np.random.seed(42)
    dates = [datetime(2026, 1, 1) + timedelta(minutes=5 * i) for i in range(n)]
    close = 65000 + np.random.randn(n) * 20  # Small random noise
    high = close + 15
    low = close - 15
    open_ = close + np.random.randn(n) * 5
    volume = np.random.uniform(500, 1500, n)
    return pd.DataFrame({"open_time": dates, "open": open_, "high": high, "low": low, "close": close, "volume": volume})


class TestTrendFollower:
    def test_generates_long_signal_in_uptrend(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        # Should generate at least one LONG signal in uptrend
        long_signals = [s for s in signals if s.direction == Direction.LONG]
        assert len(long_signals) > 0

    def test_generates_short_signal_in_downtrend(self, downtrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(downtrend_data, "BTCUSDT", MarketRegime.TRENDING_DOWN)
        short_signals = [s for s in signals if s.direction == Direction.SHORT]
        assert len(short_signals) > 0

    def test_low_confidence_in_sideways(self, sideways_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(sideways_data, "BTCUSDT", MarketRegime.RANGING)
        # In sideways, signals should have low confidence or be empty
        if signals:
            avg_confidence = sum(s.confidence for s in signals) / len(signals)
            assert avg_confidence < 0.7

    def test_signal_has_stop_loss_and_take_profit(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        if signals:
            s = signals[0]
            if s.direction == Direction.LONG:
                assert s.stop_loss < s.entry_price
                assert s.take_profit > s.entry_price
            else:
                assert s.stop_loss > s.entry_price
                assert s.take_profit < s.entry_price

    def test_signal_strategy_name(self, uptrend_data):
        from strategy.trend_follower import TrendFollower

        tf = TrendFollower()
        signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
        if signals:
            assert signals[0].strategy == "trend_follower"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/strategy/test_trend_follower.py -v`
Expected: FAIL

- [ ] **Step 3: Implement base_strategy.py**

```python
# strategy/base_strategy.py
from abc import ABC, abstractmethod

import pandas as pd

from core.models import MarketRegime, TradeSignal


class BaseStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        """Generate trade signals from OHLCV data."""
        pass
```

- [ ] **Step 4: Implement trend_follower.py**

```python
# strategy/trend_follower.py
import pandas as pd
import ta

from core.models import Direction, MarketRegime, TradeSignal
from strategy.base_strategy import BaseStrategy


class TrendFollower(BaseStrategy):
    name = "trend_follower"

    def __init__(self, fast_ema: int = 9, slow_ema: int = 21, atr_period: int = 14, atr_sl_mult: float = 1.5, atr_tp_mult: float = 3.0):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.atr_period = atr_period
        self.atr_sl_mult = atr_sl_mult
        self.atr_tp_mult = atr_tp_mult

    def generate(self, klines: pd.DataFrame, symbol: str, regime: MarketRegime) -> list[TradeSignal]:
        if len(klines) < self.slow_ema + 5:
            return []

        df = klines.copy()
        df["ema_fast"] = ta.trend.ema_indicator(df["close"], window=self.fast_ema)
        df["ema_slow"] = ta.trend.ema_indicator(df["close"], window=self.slow_ema)
        df["atr"] = ta.volatility.average_true_range(df["high"], df["low"], df["close"], window=self.atr_period)

        signals = []
        last = df.iloc[-1]
        prev = df.iloc[-2]

        if pd.isna(last["ema_fast"]) or pd.isna(last["ema_slow"]) or pd.isna(last["atr"]):
            return []

        atr = last["atr"]
        price = last["close"]

        # Bullish crossover or fast above slow
        if last["ema_fast"] > last["ema_slow"]:
            # Confidence based on regime and crossover strength
            spread = (last["ema_fast"] - last["ema_slow"]) / price
            confidence = min(0.9, 0.5 + spread * 100)
            if regime == MarketRegime.TRENDING_UP:
                confidence = min(0.95, confidence + 0.1)
            elif regime in (MarketRegime.RANGING, MarketRegime.TRENDING_DOWN):
                confidence *= 0.6

            if confidence >= 0.3:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    confidence=round(confidence, 3),
                    entry_price=price,
                    stop_loss=round(price - atr * self.atr_sl_mult, 2),
                    take_profit=round(price + atr * self.atr_tp_mult, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                ))

        # Bearish: fast below slow
        elif last["ema_fast"] < last["ema_slow"]:
            spread = (last["ema_slow"] - last["ema_fast"]) / price
            confidence = min(0.9, 0.5 + spread * 100)
            if regime == MarketRegime.TRENDING_DOWN:
                confidence = min(0.95, confidence + 0.1)
            elif regime in (MarketRegime.RANGING, MarketRegime.TRENDING_UP):
                confidence *= 0.6

            if confidence >= 0.3:
                signals.append(TradeSignal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    confidence=round(confidence, 3),
                    entry_price=price,
                    stop_loss=round(price + atr * self.atr_sl_mult, 2),
                    take_profit=round(price - atr * self.atr_tp_mult, 2),
                    strategy=self.name,
                    regime=regime,
                    timeframe_score=0,
                ))

        return signals
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/strategy/test_trend_follower.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add strategy/base_strategy.py strategy/trend_follower.py tests/strategy/test_trend_follower.py
git commit -m "feat: add BaseStrategy and TrendFollower with EMA crossover"
```

---

### Task 8: RiskManager (defense/risk_manager.py)

**Files:**
- Create: `crypto-beast/defense/risk_manager.py`
- Create: `crypto-beast/tests/defense/test_risk_manager.py`

- [ ] **Step 1: Write tests**

```python
# tests/defense/test_risk_manager.py
import pytest

from core.models import (
    Direction,
    MarketRegime,
    OrderType,
    Portfolio,
    Position,
    TradeSignal,
    ValidatedOrder,
)


@pytest.fixture
def empty_portfolio():
    return Portfolio(
        equity=100.0,
        available_balance=100.0,
        positions=[],
        peak_equity=100.0,
        locked_capital=0.0,
        daily_pnl=0.0,
        total_fees_today=0.0,
        drawdown_pct=0.0,
    )


@pytest.fixture
def full_portfolio():
    """Portfolio with max positions already open."""
    positions = [
        Position(symbol=f"COIN{i}USDT", direction=Direction.LONG, entry_price=100.0,
                 quantity=0.1, leverage=5, unrealized_pnl=0.0, strategy="test",
                 entry_time=None, current_stop=95.0)
        for i in range(3)
    ]
    return Portfolio(
        equity=100.0, available_balance=50.0, positions=positions,
        peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
        total_fees_today=0.0, drawdown_pct=0.0,
    )


@pytest.fixture
def long_signal():
    return TradeSignal(
        symbol="BTCUSDT", direction=Direction.LONG, confidence=0.85,
        entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
        strategy="trend_follower", regime=MarketRegime.TRENDING_UP,
        timeframe_score=8,
    )


class TestRiskManager:
    def test_validate_returns_order_for_valid_signal(self, empty_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, empty_portfolio)
        assert order is not None
        assert isinstance(order, ValidatedOrder)

    def test_position_size_respects_max_risk(self, empty_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, empty_portfolio)
        # Max risk per trade = 2% of $100 = $2
        assert order.risk_amount <= 2.0 + 0.01  # small float tolerance

    def test_rejects_when_max_positions_reached(self, full_portfolio, long_signal):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        order = rm.validate(long_signal, full_portfolio)
        assert order is None

    def test_leverage_based_on_confidence(self, empty_portfolio):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())

        high_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.9,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        order = rm.validate(high_conf, empty_portfolio)
        assert order.leverage == 10

        mid_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.6,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        order = rm.validate(mid_conf, empty_portfolio)
        assert order.leverage == 5

    def test_rejects_low_confidence(self, empty_portfolio):
        from defense.risk_manager import RiskManager
        from config import Config

        rm = RiskManager(Config())
        low_conf = TradeSignal(
            symbol="BTCUSDT", direction=Direction.LONG, confidence=0.3,
            entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
            strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
        )
        order = rm.validate(low_conf, empty_portfolio)
        assert order is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/defense/test_risk_manager.py -v`
Expected: FAIL

- [ ] **Step 3: Implement risk_manager.py**

```python
# defense/risk_manager.py
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

    def validate(self, signal: TradeSignal, portfolio: Portfolio) -> ValidatedOrder | None:
        # Reject low confidence signals
        if signal.confidence < 0.5:
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

        # Determine leverage based on confidence
        if signal.confidence >= 0.8:
            leverage = self.config.leverage_high_confidence
        elif signal.confidence >= 0.5:
            leverage = self.config.leverage_medium_confidence
        else:
            return None

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

    def validate_fast(self, signal: TradeSignal, portfolio: Portfolio) -> ValidatedOrder | None:
        """Fast validation for altcoin lag strategy - skips some checks."""
        return self.validate(signal, portfolio)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/defense/test_risk_manager.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add defense/risk_manager.py tests/defense/test_risk_manager.py
git commit -m "feat: add RiskManager with position sizing and confidence-based leverage"
```

---

### Task 9: PaperExecutor (execution/paper_executor.py)

**Files:**
- Create: `crypto-beast/execution/paper_executor.py`
- Create: `crypto-beast/tests/execution/test_paper_executor.py`

- [ ] **Step 1: Write tests**

```python
# tests/execution/test_paper_executor.py
import pytest
import pytest_asyncio

from core.models import (
    Direction,
    ExecutionPlan,
    MarketRegime,
    OrderType,
    TradeSignal,
    ValidatedOrder,
)


@pytest.fixture
def sample_plan():
    signal = TradeSignal(
        symbol="BTCUSDT", direction=Direction.LONG, confidence=0.85,
        entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
        strategy="trend_follower", regime=MarketRegime.TRENDING_UP, timeframe_score=8,
    )
    order = ValidatedOrder(
        signal=signal, quantity=0.001, leverage=10,
        order_type=OrderType.MARKET, risk_amount=1.0, max_slippage=0.001,
    )
    return ExecutionPlan(
        order=order,
        entry_tranches=[{"price": 65000.0, "quantity": 0.001, "type": "MARKET"}],
        exit_tranches=[{"price": 67000.0, "quantity": 0.001, "trigger": "TP"}],
    )


class TestPaperExecutor:
    @pytest.mark.asyncio
    async def test_execute_returns_success(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_generates_paper_order_id(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.order_ids[0].startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_execute_records_trade_in_db(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        await executor.execute(sample_plan)
        trades = db.execute("SELECT * FROM trades").fetchall()
        assert len(trades) == 1

    @pytest.mark.asyncio
    async def test_execute_calculates_fees(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65000.0)
        result = await executor.execute(sample_plan)
        assert result.fees_paid > 0

    @pytest.mark.asyncio
    async def test_get_positions(self, sample_plan, db):
        from execution.paper_executor import PaperExecutor

        executor = PaperExecutor(db=db, current_price_fn=lambda s: 65100.0)
        await executor.execute(sample_plan)
        positions = await executor.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTCUSDT"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/execution/test_paper_executor.py -v`
Expected: FAIL

- [ ] **Step 3: Implement paper_executor.py**

```python
# execution/paper_executor.py
import random
from datetime import datetime
from typing import Callable
from uuid import uuid4

from loguru import logger

from core.database import Database
from core.models import (
    Direction,
    ExecutionPlan,
    ExecutionResult,
    OrderType,
    Position,
)


class PaperExecutor:
    TAKER_FEE = 0.0004

    def __init__(self, db: Database, current_price_fn: Callable[[str], float]):
        self.db = db
        self._current_price_fn = current_price_fn

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        signal = plan.order.signal
        price = self._current_price_fn(signal.symbol)

        # Simulate slippage
        slippage = random.uniform(0, 0.001)
        if signal.direction == Direction.LONG:
            fill_price = price * (1 + slippage)
        else:
            fill_price = price * (1 - slippage)

        quantity = plan.order.quantity
        fees = quantity * fill_price * self.TAKER_FEE
        order_id = f"PAPER-{uuid4().hex[:12]}"

        # Record in database
        self.db.execute(
            """INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, fees, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.symbol,
                signal.direction.value,
                round(fill_price, 2),
                quantity,
                plan.order.leverage,
                signal.strategy,
                datetime.utcnow().isoformat(),
                round(fees, 6),
                "OPEN",
            ),
        )

        logger.info(
            f"PAPER {signal.direction.value} {signal.symbol} @ {fill_price:.2f} | "
            f"qty={quantity} | lev={plan.order.leverage}x | fee={fees:.4f}"
        )

        return ExecutionResult(
            success=True,
            order_ids=[order_id],
            avg_fill_price=round(fill_price, 2),
            total_filled=quantity,
            fees_paid=round(fees, 6),
            slippage=round(slippage, 6),
        )

    async def get_positions(self) -> list[Position]:
        rows = self.db.execute(
            "SELECT id, symbol, side, entry_price, quantity, leverage, strategy, entry_time FROM trades WHERE status = 'OPEN'"
        ).fetchall()
        positions = []
        for row in rows:
            symbol = row[1]
            direction = Direction.LONG if row[2] == "LONG" else Direction.SHORT
            entry_price = row[3]
            current_price = self._current_price_fn(symbol)

            if direction == Direction.LONG:
                unrealized = (current_price - entry_price) * row[4] * row[5]
            else:
                unrealized = (entry_price - current_price) * row[4] * row[5]

            positions.append(Position(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                quantity=row[4],
                leverage=row[5],
                unrealized_pnl=round(unrealized, 4),
                strategy=row[6],
                entry_time=row[7],
                current_stop=0.0,
                order_ids=[f"PAPER-{row[0]}"],
            ))
        return positions

    async def close_position(self, position: Position, order_type: OrderType = OrderType.MARKET) -> ExecutionResult:
        current_price = self._current_price_fn(position.symbol)
        fees = position.quantity * current_price * self.TAKER_FEE
        pnl = position.unrealized_pnl - fees

        # Update database
        trade_id = int(position.order_ids[0].replace("PAPER-", "")) if position.order_ids else None
        if trade_id:
            self.db.execute(
                "UPDATE trades SET exit_price = ?, exit_time = ?, pnl = ?, status = ? WHERE id = ?",
                (round(current_price, 2), datetime.utcnow().isoformat(), round(pnl, 4), "CLOSED", trade_id),
            )

        logger.info(f"PAPER CLOSE {position.symbol} @ {current_price:.2f} | PnL={pnl:.4f}")

        return ExecutionResult(
            success=True,
            order_ids=position.order_ids,
            avg_fill_price=current_price,
            total_filled=position.quantity,
            fees_paid=round(fees, 6),
            slippage=0.0,
        )

    async def cancel_all_pending(self) -> None:
        logger.info("PAPER: No pending orders to cancel")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/execution/test_paper_executor.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add execution/paper_executor.py tests/execution/test_paper_executor.py
git commit -m "feat: add PaperExecutor for simulated trading with DB recording"
```

---

## Chunk 3: Safety Layer (Tasks 10-12)

Critical safety modules that must work before any live trading.

### Task 10: EmergencyShield (execution/emergency_shield.py)

**Files:**
- Create: `crypto-beast/execution/emergency_shield.py`
- Create: `crypto-beast/tests/execution/test_emergency_shield.py`

- [ ] **Step 1: Write tests**

```python
# tests/execution/test_emergency_shield.py
import pytest
from datetime import datetime

from core.models import Direction, Portfolio, Position, ShieldAction


@pytest.fixture
def healthy_portfolio():
    return Portfolio(
        equity=100.0, available_balance=80.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=0.0,
    )


@pytest.fixture
def daily_loss_portfolio():
    return Portfolio(
        equity=88.0, available_balance=60.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=-12.0, total_fees_today=0.5, drawdown_pct=0.12,
    )


@pytest.fixture
def critical_drawdown_portfolio():
    return Portfolio(
        equity=65.0, available_balance=40.0, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=-5.0, total_fees_today=0.3, drawdown_pct=0.35,
    )


class TestEmergencyShield:
    def test_continue_on_healthy(self, healthy_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(healthy_portfolio)
        assert action == ShieldAction.CONTINUE

    def test_halt_on_daily_loss(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(daily_loss_portfolio)
        assert action == ShieldAction.HALT

    def test_emergency_close_on_critical_drawdown(self, critical_drawdown_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        action = shield.check(critical_drawdown_portfolio)
        assert action == ShieldAction.EMERGENCY_CLOSE

    def test_cooldown_after_halt(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        shield.check(daily_loss_portfolio)
        assert shield.is_in_cooldown() is True

    def test_reset_clears_cooldown(self, daily_loss_portfolio):
        from execution.emergency_shield import EmergencyShield
        from config import Config

        shield = EmergencyShield(Config())
        shield.check(daily_loss_portfolio)
        shield.reset()
        assert shield.is_in_cooldown() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/execution/test_emergency_shield.py -v`
Expected: FAIL

- [ ] **Step 3: Implement emergency_shield.py**

```python
# execution/emergency_shield.py
from datetime import datetime, timedelta

from loguru import logger

from config import Config
from core.models import Portfolio, ShieldAction


class EmergencyShield:
    def __init__(self, config: Config):
        self.config = config
        self._cooldown_until: datetime | None = None
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/execution/test_emergency_shield.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add execution/emergency_shield.py tests/execution/test_emergency_shield.py
git commit -m "feat: add EmergencyShield with daily loss halt and drawdown emergency close"
```

---

### Task 11: RecoveryMode (execution/recovery_mode.py)

**Files:**
- Create: `crypto-beast/execution/recovery_mode.py`
- Create: `crypto-beast/tests/execution/test_recovery_mode.py`

- [ ] **Step 1: Write tests**

```python
# tests/execution/test_recovery_mode.py
import pytest

from core.models import Portfolio, RecoveryState


def make_portfolio(drawdown: float):
    equity = 100.0 * (1 - drawdown)
    return Portfolio(
        equity=equity, available_balance=equity * 0.8, positions=[],
        peak_equity=100.0, locked_capital=0.0,
        daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=drawdown,
    )


class TestRecoveryMode:
    def test_normal_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.02))
        assert state == RecoveryState.NORMAL

    def test_cautious_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.07))
        assert state == RecoveryState.CAUTIOUS

    def test_recovery_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.15))
        assert state == RecoveryState.RECOVERY

    def test_critical_state(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        state = rm.assess_state(make_portfolio(0.25))
        assert state == RecoveryState.CRITICAL

    def test_adjust_reduces_leverage_in_cautious(self):
        from execution.recovery_mode import RecoveryMode
        from config import Config

        rm = RecoveryMode(Config())
        rm.assess_state(make_portfolio(0.07))
        params = rm.get_adjusted_params()
        assert params["max_leverage"] <= 3
        assert params["min_confidence"] > 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/execution/test_recovery_mode.py -v`
Expected: FAIL

- [ ] **Step 3: Implement recovery_mode.py**

```python
# execution/recovery_mode.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/execution/test_recovery_mode.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add execution/recovery_mode.py tests/execution/test_recovery_mode.py
git commit -m "feat: add RecoveryMode with 4-state drawdown-adaptive behavior"
```

---

### Task 12: SystemGuard (core/system_guard.py)

**Files:**
- Create: `crypto-beast/core/system_guard.py`
- Create: `crypto-beast/tests/core/test_system_guard.py`

- [ ] **Step 1: Write tests**

```python
# tests/core/test_system_guard.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && python -m pytest tests/core/test_system_guard.py -v`
Expected: FAIL

- [ ] **Step 3: Implement system_guard.py**

```python
# core/system_guard.py
from loguru import logger

from core.models import SystemStatus


class SystemGuard:
    CORE_MODULES = {"data_feed", "executor", "risk_manager", "emergency_shield"}

    def __init__(self, latency_warn: int = 500, latency_halt: int = 2000):
        self._module_status: dict[str, bool] = {}
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd crypto-beast && python -m pytest tests/core/test_system_guard.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/system_guard.py tests/core/test_system_guard.py
git commit -m "feat: add SystemGuard with health monitoring and graceful degradation"
```

---

## Chunk 4: Analysis + More Strategies (Tasks 13-18)

Builds the analysis layer and remaining strategies for multi-strategy trading.

### Task 13: MarketRegimeDetector (analysis/market_regime.py)

**Files:**
- Create: `crypto-beast/analysis/market_regime.py`
- Create: `crypto-beast/tests/analysis/test_market_regime.py`

- [ ] **Step 1: Write tests for regime detection**

Test that clear uptrend data → TRENDING_UP, sideways → RANGING, etc. Use the `uptrend_data`, `downtrend_data`, `sideways_data` fixtures from Task 7. Tests should verify:
- Uptrend → TRENDING_UP
- Downtrend → TRENDING_DOWN
- Sideways → RANGING

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement using ADX, Bollinger Band width, and EMA alignment**

Use `ta` library: `ta.trend.ADXIndicator` for ADX, `ta.volatility.BollingerBands` for BB width, and EMA 20/50 alignment. Logic:
- ADX > 25 and EMA20 > EMA50 → TRENDING_UP
- ADX > 25 and EMA20 < EMA50 → TRENDING_DOWN
- ADX < 20 → RANGING
- BB width > 90th percentile → HIGH_VOLATILITY
- BB width < 10th percentile → LOW_VOLATILITY

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add MarketRegimeDetector with ADX and BB width classification"
```

---

### Task 14: MultiTimeframe (analysis/multi_timeframe.py)

**Files:**
- Create: `crypto-beast/analysis/multi_timeframe.py`
- Create: `crypto-beast/tests/analysis/test_multi_timeframe.py`

- [ ] **Step 1: Write tests for confluence scoring**

Test that when all timeframes are bullish (EMA fast > slow), score = +10. Mixed → lower score. All bearish → -10. Test `filter_signal` rejects signals when |score| < 6.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement with per-timeframe EMA voting and weighted sum**

Weights: 4h=4, 1h=3, 15m=2, 5m=1. Vote per timeframe: EMA9 > EMA21 → +1, else -1. Score = weighted sum.

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add MultiTimeframe confluence scoring"
```

---

### Task 15: SessionTrader (analysis/session_trader.py)

**Files:**
- Create: `crypto-beast/analysis/session_trader.py`
- Create: `crypto-beast/tests/analysis/test_session_trader.py`

- [ ] **Step 1: Write tests**

Test session identification by UTC hour (e.g., hour=3 → ASIA, hour=10 → EUROPE, hour=15 → US_OVERLAP). Test strategy weight adjustments per session.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement session detection and weight mapping**

- [ ] **Step 4: Run tests to verify they pass**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add SessionTrader with time-based strategy weighting"
```

---

### Task 16: Remaining Strategies (MeanReversion, Momentum, Breakout, Scalper)

**Files:**
- Create: `crypto-beast/strategy/mean_reversion.py`
- Create: `crypto-beast/strategy/momentum.py`
- Create: `crypto-beast/strategy/breakout.py`
- Create: `crypto-beast/strategy/scalper.py`
- Create: `crypto-beast/tests/strategy/test_mean_reversion.py`
- Create: `crypto-beast/tests/strategy/test_momentum.py`
- Create: `crypto-beast/tests/strategy/test_breakout.py`
- Create: `crypto-beast/tests/strategy/test_scalper.py`

Each strategy follows the same pattern as TrendFollower:
1. Extends `BaseStrategy`
2. Uses `ta` library indicators
3. Returns `list[TradeSignal]`

- [ ] **Step 1: Write test for MeanReversion** in `test_mean_reversion.py`:
  - Test LONG signal when close < lower BB and RSI < 30 (oversold bounce)
  - Test SHORT signal when close > upper BB and RSI > 70
  - Test no signal when close is near BB middle
  - Test stop_loss at 2.5σ, take_profit at BB middle
  - Use `sideways_data` fixture

- [ ] **Step 2: Implement MeanReversion**
  - Indicators: `ta.volatility.BollingerBands(window=20, window_dev=2)`, `ta.momentum.RSIIndicator(window=14)`
  - LONG: close < lower_band AND RSI < 30 → entry=close, stop=lower_band - 0.5*BB_width, tp=middle_band
  - SHORT: close > upper_band AND RSI > 70 → entry=close, stop=upper_band + 0.5*BB_width, tp=middle_band
  - Confidence: base 0.6, +0.1 if regime==RANGING, -0.2 if regime==TRENDING

- [ ] **Step 3: Write test for Momentum** in `test_momentum.py`:
  - Test LONG when MACD histogram increasing for 3+ bars and price above EMA20
  - Test SHORT when MACD histogram decreasing for 3+ bars and price below EMA20
  - Test confidence scales with histogram magnitude

- [ ] **Step 4: Implement Momentum**
  - Indicators: `ta.trend.MACD`, `ta.trend.ema_indicator(window=20)`, volume SMA
  - LONG: MACD hist > 0 and hist[-1] > hist[-2] > hist[-3] and close > EMA20
  - Volume confirmation: current volume > 1.2x SMA(20) volume
  - Confidence: base 0.55, +0.15 if volume confirmed, +0.1 if regime==TRENDING_UP

- [ ] **Step 5: Write test for Breakout** in `test_breakout.py`:
  - Test signal when BB width is < 20th percentile (squeeze) then price breaks above upper BB
  - Test no signal during wide BB (no squeeze)

- [ ] **Step 6: Implement Breakout**
  - BB squeeze: BB width percentile over last 120 candles < 20
  - Entry: close breaks above upper_band (LONG) or below lower_band (SHORT) with volume > 1.5x avg
  - Stop: opposite BB band
  - Confidence: base 0.6, +0.1 if volume > 2x avg

- [ ] **Step 7: Write test for Scalper** in `test_scalper.py`:
  - Test LONG when RSI(2) < 10
  - Test SHORT when RSI(2) > 90
  - Test very tight stops (0.5x ATR)

- [ ] **Step 8: Implement Scalper**
  - Indicators: `ta.momentum.RSIIndicator(window=2)`, ATR(14)
  - LONG: RSI(2) < 10 → entry=close, stop=close - 0.5*ATR, tp=close + 1.0*ATR
  - SHORT: RSI(2) > 90 → entry=close, stop=close + 0.5*ATR, tp=close - 1.0*ATR
  - Confidence: base 0.5, +0.1 if regime==RANGING

- [ ] **Step 9: Run all strategy tests**

Run: `cd crypto-beast && python -m pytest tests/strategy/ -v`

- [ ] **Step 10: Commit**

```bash
git commit -m "feat: add MeanReversion, Momentum, Breakout, and Scalper strategies"
```

---

### Task 17: StrategyEngine (strategy/strategy_engine.py)

**Files:**
- Create: `crypto-beast/strategy/strategy_engine.py`
- Create: `crypto-beast/tests/strategy/test_strategy_engine.py`

**Note:** Strategies operate without intelligence module biases until Chunk 5. The `DirectionalBias` inputs from WhaleTracker, SentimentRadar, etc. will be integrated after Task 19.

- [ ] **Step 1: Write tests**

Test scenarios:
- All 5 strategies run and return signals
- Weight updates from Evolver change output ordering
- Conflicting signals for same symbol: if both LONG and SHORT signals exist for BTCUSDT, keep the one with higher weighted confidence, discard the other
- If no strategy produces a signal, return empty list
- `get_strategy_weights()` returns current weights

- [ ] **Step 2: Implement**

```python
# strategy/strategy_engine.py
class StrategyEngine:
    def __init__(self, data_feed, regime_detector, session_trader, multi_timeframe):
        self._strategies = {
            "trend_follower": TrendFollower(),
            "mean_reversion": MeanReversion(),
            "momentum": Momentum(),
            "breakout": Breakout(),
            "scalper": Scalper(),
        }
        # Default equal weights, updated by Evolver
        self._weights = {name: 0.2 for name in self._strategies}
        # ... store dependencies

    def generate_signals(self, symbol: str, klines: pd.DataFrame) -> list[TradeSignal]:
        regime = self._regime_detector.detect(symbol)
        session_weights = self._session_trader.get_strategy_weights()
        signals = []

        for name, strategy in self._strategies.items():
            raw_signals = strategy.generate(klines, symbol, regime)
            for sig in raw_signals:
                # Apply weight: strategy_weight * session_weight * regime_fit
                weight = self._weights[name] * session_weights.get(name, 1.0)
                sig.confidence *= weight
                # Set timeframe score from MultiTimeframe
                confluence = self._multi_timeframe.get_confluence(symbol)
                sig.timeframe_score = confluence.score
                signals.append(sig)

        # Deduplicate: per symbol, keep highest confidence direction only
        best_per_symbol = {}
        for sig in signals:
            key = sig.symbol
            if key not in best_per_symbol or sig.confidence > best_per_symbol[key].confidence:
                best_per_symbol[key] = sig

        return sorted(best_per_symbol.values(), key=lambda s: s.confidence, reverse=True)

    def update_weights(self, new_weights: dict[str, float]) -> None:
        self._weights.update(new_weights)

    def get_strategy_weights(self) -> dict[str, float]:
        return self._weights.copy()
```

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add StrategyEngine multi-strategy orchestrator with deduplication"
```

---

### Task 18: AntiTrap + FeeOptimizer

**Files:**
- Create: `crypto-beast/defense/anti_trap.py`
- Create: `crypto-beast/defense/fee_optimizer.py`
- Create: `crypto-beast/tests/defense/test_anti_trap.py`
- Create: `crypto-beast/tests/defense/test_fee_optimizer.py`

- [ ] **Step 1: Write AntiTrap tests** — pin bar detection, volume divergence, pump detection
- [ ] **Step 2: Implement AntiTrap** — filter signals using candle analysis
- [ ] **Step 3: Write FeeOptimizer tests** — maker vs taker selection, budget tracking
- [ ] **Step 4: Implement FeeOptimizer**
- [ ] **Step 5: Run tests and commit**

```bash
git commit -m "feat: add AntiTrap signal filter and FeeOptimizer"
```

---

## Chunk 5: Intelligence + Evolution (Tasks 19-24)

Data intelligence modules and the self-evolution system.

### Task 19a: WhaleTracker (data/whale_tracker.py)

**Files:**
- Create: `crypto-beast/data/whale_tracker.py`
- Create: `crypto-beast/tests/data/test_whale_tracker.py`

All intelligence modules follow the background updater pattern from spec Appendix B1: run on independent timers, cache results, never block the main 5-second loop.

- [ ] **Step 1: Write tests**
  - Test `get_signal()` returns BULLISH when recent large withdrawals detected
  - Test `get_signal()` returns BEARISH when recent large deposits detected
  - Test `get_signal()` returns NEUTRAL when no whale activity
  - Test caching: `update()` returns cached data without API call if within UPDATE_INTERVAL
  - Mock Binance trade data (trades > $100k) for testing

- [ ] **Step 2: Implement**
  - `UPDATE_INTERVAL = 60` seconds
  - `_background_updater()`: async loop that fetches large trades from Binance WebSocket aggTrade stream, filters trades > $100k notional
  - `update()` returns `self._cached_events` (never blocks)
  - `get_signal()`: if net large buys > net large sells in last 15min → BULLISH (confidence 0.3-0.7 based on volume ratio)

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add WhaleTracker with large trade detection and background caching"
```

---

### Task 19b: SentimentRadar (data/sentiment_radar.py)

**Files:**
- Create: `crypto-beast/data/sentiment_radar.py`
- Create: `crypto-beast/tests/data/test_sentiment_radar.py`

- [ ] **Step 1: Write tests**
  - Test BULLISH when Fear & Greed < 20 (extreme fear = contrarian buy)
  - Test BEARISH when Fear & Greed > 80 (extreme greed = contrarian sell)
  - Test NEUTRAL when Fear & Greed 30-70
  - Test long/short ratio integration
  - Mock `aiohttp` responses from alternative.me API

- [ ] **Step 2: Implement**
  - `UPDATE_INTERVAL = 300` seconds (5 min, F&G updates daily anyway)
  - Fetch Fear & Greed from `https://api.alternative.me/fng/`
  - Fetch long/short ratio from Binance API: `GET /futures/data/globalLongShortAccountRatio`
  - Combined signal: weight F&G 60%, L/S ratio 40%

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add SentimentRadar with Fear & Greed and long/short ratio"
```

---

### Task 19c: LiquidationHunter (data/liquidation_hunter.py)

**Files:**
- Create: `crypto-beast/data/liquidation_hunter.py`
- Create: `crypto-beast/tests/data/test_liquidation_hunter.py`

- [ ] **Step 1: Write tests**
  - Test cascade detection: mock 10 consecutive LONG liquidations > 2x average → `is_cascade_active()` returns True
  - Test BULLISH signal after long liquidation cascade subsides (exhaustion = entry point for longs)
  - Test no signal during normal liquidation activity

- [ ] **Step 2: Implement**
  - Subscribe to Binance `forceOrder` WebSocket stream
  - Track rolling windows: 1m, 5m, 15m cumulative liquidation volume
  - Cascade detection: current 5m volume > 2x average 5m volume
  - Signal: after cascade peaks and volume drops to < 1.5x average → entry signal in opposite direction
  - Confidence: based on cascade volume magnitude (0.4-0.8)

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add LiquidationHunter with cascade detection"
```

---

### Task 19d: OrderBookSniper (data/orderbook_sniper.py)

**Files:**
- Create: `crypto-beast/data/orderbook_sniper.py`
- Create: `crypto-beast/tests/data/test_orderbook_sniper.py`

- [ ] **Step 1: Write tests** using `sample_orderbook` fixture from conftest:
  - Test BULLISH when bid_volume / ask_volume > 1.5 at top 20 levels
  - Test BEARISH when ratio < 0.67
  - Test NEUTRAL when ratio 0.8-1.2
  - Test wall detection: single level with qty > 5x average

- [ ] **Step 2: Implement**
  - `get_imbalance()`: sum(bid_qty top 20) / sum(ask_qty top 20)
  - `get_signal()`: imbalance > 1.5 → BULLISH, < 0.67 → BEARISH
  - Wall detection: find levels with qty > 5x mean, flag as support/resistance

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add OrderBookSniper with imbalance and wall detection"
```

---

### Task 20: CompoundEngine (evolution/compound_engine.py)

**Files:**
- Create: `crypto-beast/evolution/compound_engine.py`
- Create: `crypto-beast/tests/evolution/test_compound_engine.py`

- [ ] **Step 1: Write tests**
  - Test Kelly fraction: given 60% win rate and 1.5 avg win/loss ratio → f = (1.5*0.6 - 0.4)/1.5 = 0.367, half-Kelly = 0.183
  - Test profit locking: equity $150 → $20 locked; equity $200 → $50 locked
  - Test available capital = equity - locked_capital
  - Test position sizing: available_capital * kelly_fraction / num_strategies

- [ ] **Step 2: Implement**

```python
# evolution/compound_engine.py
class CompoundEngine:
    def __init__(self, config: Config, db: Database):
        self.config = config
        self.db = db
        self._locked_capital = 0.0

    def get_kelly_fraction(self, strategy: str) -> float:
        """Calculate half-Kelly for a strategy from its trade history."""
        rows = self.db.execute(
            "SELECT pnl FROM trades WHERE strategy = ? AND status = 'CLOSED' ORDER BY exit_time DESC LIMIT 100",
            (strategy,)
        ).fetchall()
        if len(rows) < 10:
            return 0.02  # Default conservative fraction
        pnls = [r[0] for r in rows]
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]
        if not losses:
            return 0.1
        p = len(wins) / len(pnls)
        b = (sum(wins) / len(wins)) / (sum(losses) / len(losses)) if losses else 1.0
        kelly = (b * p - (1 - p)) / b
        return max(0.01, min(0.2, kelly * self.config.kelly_fraction))  # Half-Kelly, clamped

    def update_position_sizing(self, portfolio: Portfolio) -> PositionSizing:
        self._update_locks(portfolio.equity)
        available = portfolio.equity - self._locked_capital
        fractions = {}
        for strategy in ["trend_follower", "mean_reversion", "momentum", "breakout", "scalper"]:
            fractions[strategy] = self.get_kelly_fraction(strategy)
        return PositionSizing(available_capital=available, kelly_fractions=fractions, max_position_pct=0.3)

    def _update_locks(self, equity: float) -> None:
        for milestone, lock_amount in sorted(self.config.profit_lock_milestones.items()):
            if equity >= milestone:
                self._locked_capital = max(self._locked_capital, lock_amount)

    def get_locked_capital(self) -> float:
        return self._locked_capital
```

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add CompoundEngine with Kelly criterion and profit locking"
```

---

### Task 21: BacktestLab (evolution/backtest_lab.py)

**Files:**
- Create: `crypto-beast/evolution/backtest_lab.py`
- Create: `crypto-beast/tests/evolution/test_backtest_lab.py`

Additional models needed (add to `core/models.py`):

```python
@dataclass
class BacktestResult:
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_trades: int
    trades: list[dict]  # [{entry, exit, pnl, fees, ...}]

@dataclass
class WalkForwardResult:
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    best_params: dict
    is_valid: bool  # True if OOS sharpe > 0

@dataclass
class MonteCarloResult:
    median_return: float
    worst_case_drawdown: float  # 5th percentile
    probability_of_ruin: float  # % of simulations that hit max_drawdown
    confidence_95_return: float
```

- [ ] **Step 1: Write tests**
  - Test `run_backtest()`: run TrendFollower on sample_klines, verify it includes fees (0.04% taker) and slippage (0.05%)
  - Test that backtest result metrics are calculated correctly: win_rate = wins/total
  - Test `run_walk_forward()`: 30-day train, 7-day test split; OOS sharpe should differ from IS sharpe
  - Test `run_monte_carlo()`: 1000 iterations shuffling trade order, worst_case_drawdown should be >= max_drawdown of original

- [ ] **Step 2: Implement**

Core backtest loop:
```python
def run_backtest(self, strategy, data, config) -> BacktestResult:
    equity = config.get("starting_capital", 100.0)
    trades = []
    for i in range(lookback, len(data)):
        window = data.iloc[:i+1]
        signals = strategy.generate(window, symbol, regime)
        for signal in signals:
            # Simulate entry with slippage
            fill_price = signal.entry_price * (1 + 0.0005)  # 0.05% slippage
            fees = fill_price * quantity * 0.0004  # taker fee
            # Track position, check stop/TP on subsequent bars
            # Close position, record PnL
    return BacktestResult(...)
```

Walk-forward: split data into `train_days` chunks, optimize on each, test on next `test_days` chunk.

Monte Carlo: shuffle trade PnL list 1000 times, recalculate equity curve each time, find 5th percentile drawdown.

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add BacktestLab with walk-forward and Monte Carlo simulation"
```

---

### Task 22: Evolver (evolution/evolver.py)

**Files:**
- Create: `crypto-beast/evolution/evolver.py`
- Create: `crypto-beast/tests/evolution/test_evolver.py`

Additional model (add to `core/models.py`):

```python
@dataclass
class EvolutionReport:
    timestamp: datetime
    parameters_changed: dict  # {param: {old: x, new: y}}
    backtest_sharpe_before: float
    backtest_sharpe_after: float
    strategy_weights: dict
    recommendations_applied: list[str]
```

- [ ] **Step 1: Write tests**
  - Test that optimization finds better params: mock BacktestLab to return higher Sharpe for a known param set
  - Test 20% max change cap: if current EMA is 9, new EMA can be 7-11 at most
  - Test atomic swap: `_pending_config` is set, `apply_if_pending()` swaps it in
  - Test weight rebalancing: strategy with 0.6 Sharpe gets higher weight than 0.2 Sharpe

- [ ] **Step 2: Implement**

```python
# evolution/evolver.py
class Evolver:
    def __init__(self, config, backtest_lab, db):
        self._active_config = config
        self._pending_config = None
        self.backtest_lab = backtest_lab
        self.db = db

    async def run_daily_evolution(self, recommendations: list[str] = None) -> EvolutionReport:
        # 1. Define search space with 20% bounds around current values
        current_params = self._get_current_strategy_params()
        search_space = self._build_search_space(current_params, max_change=0.2)

        # 2. Optuna optimization
        study = optuna.create_study(direction="maximize")
        study.optimize(
            lambda trial: self._objective(trial, search_space, recommendations),
            n_trials=50,
        )

        # 3. Apply best params
        best = study.best_params
        new_config = self._active_config.copy()
        new_config.apply_overrides(best)

        # 4. Reweight strategies based on recent performance
        new_weights = self._calculate_strategy_weights()
        # ... set pending config for atomic swap
        self._pending_config = new_config
        # ... save to DB and return report

    def _objective(self, trial, search_space, recommendations):
        """Optuna objective: maximize Sharpe * sqrt(trade_count)."""
        params = {k: trial.suggest_float(k, *v) for k, v in search_space.items()}
        # Run walk-forward backtest with these params
        result = self.backtest_lab.run_walk_forward(strategy, train_days=30, test_days=7)
        fitness = result.out_of_sample_sharpe * (result.total_trades ** 0.5)
        # Bonus if addressing recommendations
        if recommendations and any("widen stops" in r for r in recommendations):
            # Favor wider stop params
            pass
        return fitness

    def apply_if_pending(self) -> bool:
        if self._pending_config:
            self._active_config = self._pending_config
            self._pending_config = None
            return True
        return False
```

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add Evolver with Optuna optimization and atomic parameter swap"
```

---

### Task 23: TradeReviewer (evolution/trade_reviewer.py)

**Files:**
- Create: `crypto-beast/evolution/trade_reviewer.py`
- Create: `crypto-beast/tests/evolution/test_trade_reviewer.py`

- [ ] **Step 1: Write tests**
  - Test STOP_TOO_TIGHT classification: insert a trade where price hit stop then moved 2x in the right direction within 4 hours
  - Test AGAINST_TREND classification: trade direction opposite to MarketRegime at entry time
  - Test FEE_EROSION: trade PnL positive before fees, negative after
  - Test win profiling: winning trade should have capture_efficiency calculated
  - Test `get_recommendations()`: most frequent loss category → recommendation

- [ ] **Step 2: Implement**

Key implementation: reconstruct context at entry time:
```python
async def _classify_loss(self, trade: dict) -> LossClassification:
    entry_time = trade["entry_time"]
    symbol = trade["symbol"]

    # Reconstruct market context at entry time from DB
    klines_at_entry = self.db.execute(
        "SELECT * FROM klines WHERE symbol=? AND interval='1h' AND open_time <= ? ORDER BY open_time DESC LIMIT 50",
        (symbol, entry_time)
    ).fetchall()

    # Check STOP_TOO_TIGHT: did price reverse after hitting stop?
    post_exit_klines = self.db.execute(
        "SELECT * FROM klines WHERE symbol=? AND interval='5m' AND open_time > ? ORDER BY open_time LIMIT 48",
        (symbol, trade["exit_time"])
    ).fetchall()
    if self._price_reversed_after_stop(trade, post_exit_klines):
        return LossClassification(trade["id"], LossCategory.STOP_TOO_TIGHT, 0.8,
            "Price reversed after stop hit", "Widen ATR stop multiplier by 0.2")

    # Check AGAINST_TREND: was trade against the regime?
    regime_at_entry = self._detect_regime_from_klines(klines_at_entry)
    if self._is_against_trend(trade["side"], regime_at_entry):
        return LossClassification(trade["id"], LossCategory.AGAINST_TREND, 0.9,
            f"Traded {trade['side']} in {regime_at_entry} regime",
            "Increase MarketRegime weight in signal scoring")

    # Check FEE_EROSION
    gross_pnl = trade["pnl"] + trade["fees"]
    if gross_pnl > 0 and trade["pnl"] < 0:
        return LossClassification(trade["id"], LossCategory.FEE_EROSION, 0.95,
            f"Gross PnL +{gross_pnl:.2f} eroded by fees {trade['fees']:.2f}",
            "Raise minimum confidence threshold")

    # ... check other categories
    return LossClassification(trade["id"], LossCategory.BAD_TIMING, 0.5,
        "No specific cause identified", "Review entry trigger sensitivity")
```

- [ ] **Step 3: Run tests and commit**

```bash
git commit -m "feat: add TradeReviewer for post-trade analysis and loss classification"
```

---

### Task 24: Remaining Analysis (EventEngine, AltcoinRadar, PatternScanner, FundingRateArb)

- [ ] **Step 1: EventEngine** — Binance funding settlement times (every 8h), basic economic calendar
- [ ] **Step 2: AltcoinRadar** — coin selection by volume/beta, BTC-alt lag fast path
- [ ] **Step 3: PatternScanner** — pivot point detection, double top/bottom, support/resistance
- [ ] **Step 4: FundingRateArb** — funding rate fetch, extreme detection, position sizing
- [ ] **Step 5: Tests for each**
- [ ] **Step 6: Commit**

```bash
git commit -m "feat: add EventEngine, AltcoinRadar, PatternScanner, FundingRateArb"
```

---

## Chunk 6: Execution + Monitoring + Integration (Tasks 25-30)

Wire everything together into a working system.

### Task 25: Executor Protocol + SmartOrder

**Files:**
- Create: `crypto-beast/execution/executor_protocol.py`
- Modify: `crypto-beast/execution/paper_executor.py` (add protocol)
- Create: `crypto-beast/execution/smart_order.py`
- Create: `crypto-beast/tests/execution/test_smart_order.py`

- [ ] **Step 1: Define ExecutorProtocol**

```python
# execution/executor_protocol.py
from typing import Protocol
from core.models import ExecutionPlan, ExecutionResult, OrderType, Position

class ExecutorProtocol(Protocol):
    async def execute(self, plan: ExecutionPlan) -> ExecutionResult: ...
    async def get_positions(self) -> list[Position]: ...
    async def close_position(self, position: Position, order_type: OrderType) -> ExecutionResult: ...
    async def cancel_all_pending(self) -> None: ...
```

- [ ] **Step 2: Update PaperExecutor** to implement `ExecutorProtocol` (add `class PaperExecutor(ExecutorProtocol):` — already compatible, just make explicit)

- [ ] **Step 3: Write SmartOrder tests** — DCA splits order into 3 tranches, scaled exit with TP1/TP2/trailing, time-based exit at 4 hours
- [ ] **Step 4: Implement SmartOrder** — `plan_execution()` creates `ExecutionPlan` with entry/exit tranches based on urgency and position size
- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add ExecutorProtocol and SmartOrder with DCA entry/scaled exit"
```

---

### Task 26: Live Executor (execution/executor.py)

**Files:**
- Create: `crypto-beast/execution/executor.py`
- Create: `crypto-beast/tests/execution/test_executor.py`

- [ ] **Step 1: Write tests** with mock ccxt exchange:
  - `execute()`: places order, returns fill info
  - `cancel_order()`: cancels by order ID
  - `get_positions()`: fetches open positions from exchange
  - `reconcile()`: compares local DB state vs exchange positions, reports discrepancies
  - All API calls go through `rate_limiter.acquire_order_slot()`

- [ ] **Step 2: Implement**
  - Implements `ExecutorProtocol`
  - Uses `ccxt.binance` with futures mode
  - Receives shared `BinanceRateLimiter` at init
  - Retry logic: 3 retries with exponential backoff (1s, 2s, 4s)
  - Reconciliation: if exchange has position not in DB → adopt it; if DB has position not on exchange → mark as CLOSED
  - All orders recorded to DB `trades` table

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add live Executor with ccxt, rate limiting, and reconciliation"
```

---

### Task 27: Notifier (monitoring/notifier.py)

- [ ] **Step 1: Write tests** — notification formatting, macOS notification fallback
- [ ] **Step 2: Implement** — Telegram bot integration + macOS `osascript` notifications
- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add Notifier with Telegram and macOS push notifications"
```

---

### Task 28: Monitor Dashboard (monitoring/monitor.py)

- [ ] **Step 1: Implement Streamlit dashboard** with 5 pages:
  - Overview: equity curve, P&L, positions
  - Trades: history table, win rate charts
  - Evolution: strategy weights, parameter history
  - Signals: real-time feed, regime indicator
  - Review: loss category pie chart, win heatmap
- [ ] **Step 2: Test that dashboard starts** on localhost:8080
- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add Streamlit monitoring dashboard with 5 pages"
```

---

### Task 29: Integration Tests

**Files:**
- Create: `crypto-beast/tests/integration/test_pipeline.py`
- Create: `crypto-beast/tests/integration/test_paper_trading.py`

- [ ] **Step 1: Write pipeline integration test**

```python
# tests/integration/test_pipeline.py
"""Test full signal-to-execution pipeline with mocked data."""
import pytest
from core.models import Direction

@pytest.mark.asyncio
async def test_full_pipeline_paper_trade(sample_klines, db):
    """Signal generated → risk validated → paper executed → trade in DB."""
    from config import Config
    from strategy.trend_follower import TrendFollower
    from analysis.market_regime import MarketRegimeDetector
    from defense.risk_manager import RiskManager
    from execution.paper_executor import PaperExecutor
    from core.models import Portfolio

    config = Config()
    regime_detector = MarketRegimeDetector()
    regime = regime_detector.detect_from_klines(sample_klines)
    strategy = TrendFollower()
    signals = strategy.generate(sample_klines, "BTCUSDT", regime)

    if not signals:
        pytest.skip("No signal generated from sample data")

    portfolio = Portfolio(equity=100.0, available_balance=100.0, positions=[],
        peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=0.0)

    rm = RiskManager(config)
    order = rm.validate(signals[0], portfolio)
    assert order is not None

    executor = PaperExecutor(db=db, current_price_fn=lambda s: signals[0].entry_price)
    from core.models import ExecutionPlan
    plan = ExecutionPlan(order=order,
        entry_tranches=[{"price": order.signal.entry_price, "quantity": order.quantity, "type": "MARKET"}],
        exit_tranches=[])
    result = await executor.execute(plan)
    assert result.success

    trades = db.execute("SELECT * FROM trades WHERE status='OPEN'").fetchall()
    assert len(trades) == 1
```

- [ ] **Step 2: Write paper trading end-to-end test**

Test that starts the main loop in paper mode, runs 3 iterations, and verifies no crashes.

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add integration tests for pipeline and paper trading"
```

---

### Task 30: Main Loop + Graceful Shutdown (main.py)

**Files:**
- Create: `crypto-beast/main.py`

- [ ] **Step 1: Implement GracefulShutdown class**

```python
# In main.py
import signal as signal_module
import asyncio

class GracefulShutdown:
    def __init__(self):
        self.shutting_down = False
        signal_module.signal(signal_module.SIGINT, self._handle)
        signal_module.signal(signal_module.SIGTERM, self._handle)

    def _handle(self, signum, frame):
        self.shutting_down = True
```

- [ ] **Step 2: Implement module initialization** (spec Startup & Launch Sequence lines 1278-1291)

```python
async def initialize():
    config = Config()
    db = Database("crypto_beast.db")
    db.initialize()
    rate_limiter = BinanceRateLimiter()
    system_guard = SystemGuard()
    data_feed = DataFeed(symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"], rate_limiter=rate_limiter)
    await data_feed.connect()
    # ... initialize all 21 modules, passing shared dependencies
    # Verify Binance connectivity and permissions
    # Check account balance
    # Reconcile open positions from previous session
    return all_modules
```

- [ ] **Step 3: Implement async main loop** (spec Appendix B1)

```python
trading_lock = asyncio.Lock()

async def main_loop(modules, shutdown):
    while not shutdown.shutting_down:
        if not modules.system_guard.should_trade():
            await asyncio.sleep(5)
            continue

        # Check for Evolver pending config swap
        modules.evolver.apply_if_pending()

        async with trading_lock:
            # Layer 1: Fetch data (intelligence modules return cached data)
            await modules.data_feed.fetch()
            biases = await asyncio.gather(
                modules.whale_tracker.update(),
                modules.sentiment_radar.update(),
                modules.liquidation_hunter.update(),
                modules.orderbook_sniper.update(),
            )

            # Layer 2-3: Analysis + Strategy for each symbol
            for symbol in modules.data_feed.symbols:
                klines = modules.data_feed.get_klines(symbol, "5m")
                signals = modules.strategy_engine.generate_signals(symbol, klines)

                # Layer 4: Filter + Risk
                for signal in signals:
                    filtered = modules.anti_trap.filter_signal(signal)
                    if not filtered:
                        continue
                    order = modules.risk_manager.validate(filtered, modules.portfolio)
                    if not order:
                        continue
                    order.order_type = modules.fee_optimizer.optimize_order_type(filtered, "normal")

                    # Layer 5: Execute
                    plan = modules.smart_order.plan_execution(order)
                    result = await modules.executor.execute(plan)

            # Update compound sizing
            modules.compound_engine.update_position_sizing(modules.portfolio)

            # Emergency check
            action = modules.emergency_shield.check(modules.portfolio)
            if action != ShieldAction.CONTINUE:
                async with trading_lock:
                    await modules.executor.cancel_all_pending()
                    for pos in await modules.executor.get_positions():
                        await modules.executor.close_position(pos, OrderType.MARKET)
                    modules.notifier.send(Notification("EMERGENCY", f"Shield triggered: {action}"))

        modules.monitor.update(modules.get_system_state())
        await asyncio.sleep(modules.config.main_loop_interval)

    # Shutdown sequence
    await shutdown_sequence(modules)
```

- [ ] **Step 4: Implement scheduled tasks** using asyncio tasks (not `schedule` library — keeps everything in one event loop)

```python
async def scheduler(modules):
    """Background task for scheduled activities."""
    while True:
        now = datetime.utcnow()
        if now.hour == 0 and now.minute == 5:
            await modules.trade_reviewer.run_daily_review()
        if now.hour == 0 and now.minute == 10:
            report = await modules.evolver.run_daily_evolution(
                recommendations=modules.trade_reviewer.get_recommendations())
        if now.weekday() == 6 and now.hour == 0 and now.minute == 30:
            await modules.trade_reviewer.run_weekly_review()
        if now.day == 1 and now.hour == 1 and now.minute == 0:
            await modules.trade_reviewer.run_monthly_review()
        if now.hour == 0 and now.minute == 30:
            modules.db.backup(f"backups/crypto_beast_{now.date()}.db")
        await asyncio.sleep(60)  # Check every minute
```

- [ ] **Step 5: Implement shutdown_sequence** (spec Appendix D)

- [ ] **Step 6: Implement arg parsing and entry point**

```python
if __name__ == "__main__":
    import argparse, subprocess
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper", action="store_true", default=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dashboard", action="store_true", default=True)
    args = parser.parse_args()

    # macOS sleep prevention
    caffeinate = subprocess.Popen(["caffeinate", "-dims"])

    try:
        asyncio.run(main(args))
    finally:
        caffeinate.terminate()
```

- [ ] **Step 7: Commit**

```bash
git commit -m "feat: add main loop with async pipeline, shutdown handler, and scheduling"
```

---

### Task 31: Pre-Launch Validation

- [ ] **Step 1: Run full test suite**

```bash
cd crypto-beast && python -m pytest tests/ -v --tb=short
```

- [ ] **Step 2: Paper trading smoke test**

```bash
cd crypto-beast && python main.py --paper
# Verify: connects to Binance, fetches data, generates signals, executes paper trades
# Run for at least 5 minutes, check logs and dashboard
```

- [ ] **Step 3: Verify all pre-launch checklist items** from spec

- [ ] **Step 4: Final commit**

```bash
git commit -m "feat: complete Crypto Beast v1.0 - ready for paper trading"
```

---

## Implementation Order Summary

| Phase | Tasks | What You Get |
|-------|-------|-------------|
| **Chunk 1: Foundation** | 1-5 | Project structure, models, config, database, rate limiter |
| **Chunk 2: Data + First Strategy** | 6-9 | Market data, TrendFollower, RiskManager, PaperExecutor |
| **Chunk 3: Safety** | 10-12 | EmergencyShield, RecoveryMode, SystemGuard |
| **Chunk 4: Analysis + Strategies** | 13-18 | Regime detection, multi-timeframe, 5 strategies, AntiTrap |
| **Chunk 5: Intelligence + Evolution** | 19a-24 | Whale/sentiment data, backtesting, Evolver, TradeReviewer |
| **Chunk 6: Integration** | 25-31 | ExecutorProtocol, SmartOrder, live executor, dashboard, main loop, integration tests, validation |

**After Chunk 2:** You can paper trade with one strategy.
**After Chunk 4:** Full multi-strategy paper trading with safety.
**After Chunk 6:** Complete system ready for live $100.
