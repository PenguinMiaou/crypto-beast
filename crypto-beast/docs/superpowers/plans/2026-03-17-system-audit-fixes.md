# System Audit Fixes: Over-engineering, Under-engineering, Bugs & Redundancy

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 10 critical bugs, remove over-engineering, fill under-engineering gaps, and eliminate redundancy — all to maximize profitability for a $99 account.

**Architecture:** Surgical fixes across 15+ files. One new module (DefenseManager). Merge RecoveryMode + EmergencyShield into unified DefenseManager. Integrate Layer 1 intel signals into strategy engine. Clean 7 unused config params. Close evolution feedback loop.

**Tech Stack:** Python 3.9.6, asyncio, ccxt, Binance Futures API, SQLite, loguru

---

## Chunk 1: Critical Bug Fixes

### Task 1: Fix datetime.utcnow() → datetime.now(timezone.utc)

`datetime.utcnow()` returns naive datetime, causes timezone comparison bugs. CLAUDE.md explicitly says "always `datetime.now(timezone.utc)`".

**Files:**
- Modify: `crypto-beast/execution/emergency_shield.py:37,63`
- Modify: `crypto-beast/execution/position_manager.py:127,154,163`
- Modify: `crypto-beast/defense/fee_optimizer.py:18,55`
- Modify: `crypto-beast/core/models.py:55,71,162`
- Modify: `crypto-beast/evolution/trade_reviewer.py` (any utcnow)
- Modify: `crypto-beast/evolution/evolver.py` (any utcnow)
- Modify: `crypto-beast/monitoring/monitor.py` (any utcnow)
- Modify: `crypto-beast/monitoring/notifier.py` (any utcnow)
- Modify: `crypto-beast/execution/paper_executor.py` (any utcnow)
- Modify: `crypto-beast/execution/executor.py` (any utcnow)
- Test: `crypto-beast/tests/test_datetime_consistency.py`

- [ ] **Step 1: Write test for datetime consistency**

```python
# tests/test_datetime_consistency.py
"""Verify no naive datetime.utcnow() usage in production code."""
import ast
import os

def test_no_utcnow_in_production_code():
    """Scan all .py files for datetime.utcnow() usage."""
    root = os.path.dirname(os.path.dirname(__file__))
    violations = []
    for dirpath, _, filenames in os.walk(root):
        if "tests" in dirpath or ".venv" in dirpath or "__pycache__" in dirpath:
            continue
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            with open(path) as f:
                source = f.read()
            if "utcnow()" in source:
                violations.append(path)
    assert violations == [], f"datetime.utcnow() found in: {violations}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest tests/test_datetime_consistency.py -v`
Expected: FAIL listing emergency_shield.py, position_manager.py, fee_optimizer.py, models.py

- [ ] **Step 3: Fix emergency_shield.py**

Replace all `datetime.utcnow()` with `datetime.now(timezone.utc)`. Add `timezone` import.

```python
# Line 1: add timezone to import
from datetime import datetime, timedelta, timezone

# Line 37: in check() method
now = datetime.now(timezone.utc)

# Line 63: in is_in_cooldown()
if datetime.now(timezone.utc) < self._cooldown_until:
```

- [ ] **Step 4: Fix position_manager.py**

```python
# Line 6: add timezone import
from datetime import datetime, timezone

# Line 127: in close_trade()
(trade["exit_price"], datetime.now(timezone.utc).isoformat(), trade["pnl"], trade["fees"], trade["trade_id"])

# Line 154: in close_trade_live() Position constructor
entry_time=datetime.now(timezone.utc),

# Line 163: in close_trade_live() DB update
(result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
```

- [ ] **Step 5: Fix fee_optimizer.py**

```python
# Line 5: add timezone import
from datetime import datetime, timezone

# Line 18: in __init__
self._last_reset = datetime.now(timezone.utc).date()

# Line 55: in _maybe_reset()
today = datetime.now(timezone.utc).date()
```

- [ ] **Step 6: Fix all remaining files flagged by the test**

After steps 3-5, run the test again. For any remaining files (`evolution/trade_reviewer.py`, `evolution/evolver.py`, `monitoring/monitor.py`, `monitoring/notifier.py`, `execution/paper_executor.py`, `execution/executor.py`), apply the same pattern: add `from datetime import datetime, timezone` and replace `datetime.utcnow()` with `datetime.now(timezone.utc)`.

- [ ] **Step 7: Fix models.py default_factory**

```python
# Line 55: DirectionalBias timestamp
timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# Line 71: TradeSignal timestamp
timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# Line 162: Pattern detected_at
detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# Add timezone to import at top
from datetime import datetime, timezone
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest tests/test_datetime_consistency.py -v`
Expected: PASS

- [ ] **Step 9: Run full test suite**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass

- [ ] **Step 10: Commit**

```bash
cd "crypto-beast" && git add -A && git commit -m "fix: replace all datetime.utcnow() with timezone-aware datetime.now(timezone.utc)"
```

---

### Task 2: Fix no-op leverage cap

**Files:**
- Modify: `crypto-beast/crypto_system.py:715-718`

- [ ] **Step 1: Fix the no-op**

Replace:
```python
# Cap leverage per recovery mode
max_lev = recovery_params.get("max_leverage", 10)
if order.leverage > max_lev:
    order = order  # RiskManager already handles this
```

With:
```python
# Cap leverage per recovery mode
max_lev = recovery_params.get("max_leverage", 10)
if order.leverage > max_lev:
    order = ValidatedOrder(
        signal=order.signal,
        quantity=order.quantity,
        leverage=max_lev,
        order_type=order.order_type,
        risk_amount=order.risk_amount,
        max_slippage=order.max_slippage,
    )
```

Note: `ValidatedOrder` import is already available from line 475.

- [ ] **Step 2: Run tests**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
cd "crypto-beast" && git add crypto_system.py && git commit -m "fix: enforce recovery mode leverage cap (was no-op)"
```

---

### Task 3: Fix emergency_close missing exit fees

**Files:**
- Modify: `crypto-beast/crypto_system.py:806-822`

- [ ] **Step 1: Fix _emergency_close to include fees**

Replace:
```python
async def _emergency_close(self, positions) -> None:
    """Close all positions on exchange AND update DB status."""
    from core.models import OrderType
    executor = self.modules["executor"]
    await executor.cancel_all_pending()
    for pos in positions:
        result = await executor.close_position(pos, OrderType.MARKET)
        # Update DB: mark as CLOSED
        if result.success:
            pnl = pos.unrealized_pnl
            self.db.execute(
                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, pnl=? "
                "WHERE symbol=? AND status='OPEN'",
                (result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
                 round(pnl, 4), pos.symbol),
            )
            logger.info(f"Emergency closed {pos.symbol}: PnL={pnl:+.4f}")
```

With:
```python
async def _emergency_close(self, positions) -> None:
    """Close all positions on exchange AND update DB status."""
    from core.models import OrderType
    executor = self.modules["executor"]
    await executor.cancel_all_pending()
    for pos in positions:
        result = await executor.close_position(pos, OrderType.MARKET)
        if result.success:
            pnl = pos.unrealized_pnl - result.fees_paid
            self.db.execute(
                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, pnl=?, fees=fees+? "
                "WHERE symbol=? AND status='OPEN'",
                (result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
                 round(pnl, 4), round(result.fees_paid, 6), pos.symbol),
            )
            self._daily_pnl += pnl
            self._daily_fees += result.fees_paid
            logger.info(f"Emergency closed {pos.symbol}: PnL={pnl:+.4f} (fees={result.fees_paid:.4f})")
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: include exit fees in emergency close PnL calculation"
```

---

### Task 4: Fix watchdog.state race condition

**Files:**
- Modify: `crypto-beast/crypto_system.py:446-471`

- [ ] **Step 1: Add file locking to watchdog state read/write**

Replace the watchdog state block (lines 446-473) with:

```python
        # Check watchdog state for pause/commands
        _state_path = os.path.join(os.path.dirname(__file__), "watchdog.state")
        if os.path.exists(_state_path):
            try:
                import json as _json
                import fcntl
                with open(_state_path, "r+") as _f:
                    fcntl.flock(_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        _wstate = _json.load(_f)
                        if _wstate.get("paused"):
                            logger.info("Trading paused via watchdog")
                            return
                        _cmd = _wstate.get("command")
                        if _cmd and isinstance(_cmd, dict):
                            action = _cmd.get("action", "")
                            if action == "CLOSE":
                                symbol = _cmd.get("args", "")
                                if symbol:
                                    await self._close_symbol_by_watchdog(symbol)
                            elif action == "CLOSEALL":
                                positions = await m["executor"].get_positions()
                                await self._emergency_close(positions)
                            elif action == "SHUTDOWN":
                                logger.info("Shutdown command from watchdog")
                                return
                            # Clear the command after processing
                            _wstate["command"] = None
                            _f.seek(0)
                            _f.truncate()
                            _json.dump(_wstate, _f)
                    finally:
                        fcntl.flock(_f, fcntl.LOCK_UN)
            except BlockingIOError:
                # Non-blocking: if watchdog holds the lock, skip this cycle.
                # Next 5-second cycle will pick up the command. Acceptable tradeoff.
                logger.debug("Watchdog state locked by another process, skipping")
            except Exception as e:
                logger.debug(f"Failed to read watchdog.state: {e}")
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: add file locking to watchdog.state reads/writes"
```

---

### Task 5: Fix peak tracking not initialized on reconciliation

**Files:**
- Modify: `crypto-beast/crypto_system.py` (reconcile_with_exchange method)

- [ ] **Step 1: Initialize peak tracking after reconciliation**

At the end of `reconcile_with_exchange()`, after all positions are synced, add:

```python
        # Initialize peak tracking for reconciled positions
        position_manager = self.modules.get("position_manager")
        if position_manager:
            rows = self.db.execute(
                "SELECT id, symbol, side, entry_price FROM trades WHERE status = 'OPEN'"
            ).fetchall()
            for row in rows:
                trade_id = row[0]
                if trade_id not in position_manager._peak_profits:
                    position_manager._peak_profits[trade_id] = 0.0
                    position_manager._peak_prices[trade_id] = row[3]  # entry_price
            if rows:
                logger.info(f"Initialized peak tracking for {len(rows)} reconciled positions")
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: initialize peak tracking for reconciled positions on startup"
```

---

### ~~Task 6: Persist HALT state to disk~~ → Covered by Task 9 (DefenseManager includes disk persistence)

---

## Chunk 2: Remove Unused Config & Deduplicate Parameters

### Task 7: Remove dead config parameters

**Files:**
- Modify: `crypto-beast/config.py`

- [ ] **Step 1: Remove unused parameters from Config**

Remove these fields (verified unused by grep — **do NOT remove kelly_fraction or profit_lock_milestones, they are used by CompoundEngine**):
- `capital_allocation` — never consumed (always trades all symbols from DataFeed)
- `max_param_change_pct` — Evolver never reads from Config
- `evolution_time_utc` — scheduler uses hardcoded 00:10 UTC
- `backtest_train_days` — Evolver uses own defaults
- `backtest_test_days` — same
- `trailing_activation_pct` — merged into profit_protect (PositionManager uses profit_protect only)
- `trailing_distance_pct` — same

- [ ] **Step 2: Verify no references broken**

Run: `cd crypto-beast && grep -r "capital_allocation\|max_param_change_pct\|evolution_time_utc\|backtest_train_days\|backtest_test_days\|trailing_activation_pct\|trailing_distance_pct" --include="*.py" | grep -v "config.py" | grep -v "tests/" | grep -v ".venv/" | grep -v "__pycache__"`

If any file references these, update that file to use inline defaults or remove the reference.

- [ ] **Step 3: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add config.py && git commit -m "refactor: remove 7 unused config parameters"
```

---

### Task 8: Deduplicate FeeOptimizer hardcoded constants

**Files:**
- Modify: `crypto-beast/defense/fee_optimizer.py`

- [ ] **Step 1: Make FeeOptimizer use Config values**

```python
class FeeOptimizer:
    def __init__(self, config: "Config"):
        self._maker_fee = config.maker_fee
        self._taker_fee = config.taker_fee
        self.daily_fee_budget = config.starting_capital * config.daily_fee_budget
        self._fees_today = 0.0
        self._last_reset = datetime.now(timezone.utc).date()

    def estimate_fee(self, notional: float, order_type: OrderType) -> float:
        if order_type == OrderType.LIMIT:
            return notional * self._maker_fee
        return notional * self._taker_fee
```

- [ ] **Step 2: Update FeeOptimizer instantiation in crypto_system.py**

In `initialize()`, find the FeeOptimizer creation (likely `FeeOptimizer(daily_fee_budget=...)` or `FeeOptimizer(config.starting_capital * config.daily_fee_budget)`) and change to `FeeOptimizer(config)`. The new constructor accepts a Config object directly.

- [ ] **Step 3: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add defense/fee_optimizer.py crypto_system.py && git commit -m "refactor: FeeOptimizer uses Config values instead of hardcoded constants"
```

---

## Chunk 3: Merge RecoveryMode + EmergencyShield → DefenseManager

### Task 9: Create unified DefenseManager

The current system has RecoveryMode (4 states based on drawdown) and EmergencyShield (HALT/EMERGENCY) as separate modules with overlapping drawdown detection. Merge into one state machine:

`NORMAL → CAUTIOUS → RECOVERY → CRITICAL → HALT → EMERGENCY_CLOSE`

**Files:**
- Create: `crypto-beast/defense/defense_manager.py`
- Modify: `crypto-beast/crypto_system.py` (replace recovery_mode + emergency_shield usage)
- Delete after: `crypto-beast/execution/recovery_mode.py` (move logic into defense_manager)
- Keep: `crypto-beast/execution/emergency_shield.py` (will be imported by defense_manager initially, then merged)
- Test: `crypto-beast/tests/test_defense_manager.py`

- [ ] **Step 1: Write tests for DefenseManager**

```python
# tests/test_defense_manager.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

from config import Config
from core.models import Portfolio, Position, RecoveryState, ShieldAction


def _make_portfolio(equity=100, peak=100, daily_pnl=0):
    dd = (peak - equity) / peak if peak > 0 else 0
    return Portfolio(
        equity=equity, available_balance=equity, positions=[],
        peak_equity=peak, locked_capital=0, daily_pnl=daily_pnl,
        total_fees_today=0, drawdown_pct=dd,
    )


def test_normal_state():
    from defense.defense_manager import DefenseManager
    dm = DefenseManager(Config())
    result = dm.check(_make_portfolio(100, 100))
    assert result.action == ShieldAction.CONTINUE
    assert result.recovery_state == RecoveryState.NORMAL
    assert result.params["max_leverage"] == 10


def test_cautious_at_5pct_drawdown():
    from defense.defense_manager import DefenseManager
    dm = DefenseManager(Config())
    result = dm.check(_make_portfolio(94, 100))
    assert result.recovery_state == RecoveryState.CAUTIOUS
    assert result.params["max_leverage"] == 5  # relaxed from 3


def test_halt_at_10pct_daily_loss():
    from defense.defense_manager import DefenseManager
    dm = DefenseManager(Config())
    result = dm.check(_make_portfolio(90, 100, daily_pnl=-10))
    assert result.action == ShieldAction.HALT


def test_emergency_close_at_30pct_drawdown():
    from defense.defense_manager import DefenseManager
    dm = DefenseManager(Config())
    result = dm.check(_make_portfolio(70, 100))
    assert result.action == ShieldAction.EMERGENCY_CLOSE


def test_halt_persists_across_instances():
    from defense.defense_manager import DefenseManager
    import os
    dm1 = DefenseManager(Config())
    dm1.check(_make_portfolio(90, 100, daily_pnl=-10))
    # New instance should load halted state
    dm2 = DefenseManager(Config())
    assert dm2.is_halted()
    # Cleanup
    if os.path.exists(dm2._STATE_FILE):
        os.remove(dm2._STATE_FILE)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest tests/test_defense_manager.py -v`
Expected: FAIL (defense_manager module doesn't exist yet)

- [ ] **Step 3: Implement DefenseManager**

```python
# defense/defense_manager.py
"""Unified defense: combines recovery mode + emergency shield into single state machine.

States: NORMAL → CAUTIOUS → RECOVERY → CRITICAL → HALT → EMERGENCY_CLOSE
Persists HALT/EMERGENCY state to disk so restarts don't bypass safety limits.
"""
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from config import Config
from core.models import Portfolio, RecoveryState, ShieldAction


@dataclass
class DefenseResult:
    """Result of defense check — action to take + adjusted trading params."""
    action: ShieldAction
    recovery_state: RecoveryState
    params: dict  # {"max_leverage": int, "min_confidence": float, "mtf_min_score": int}


# Trading params per recovery state — relaxed for small accounts
RECOVERY_PARAMS = {
    RecoveryState.NORMAL:   {"max_leverage": 10, "min_confidence": 0.3, "mtf_min_score": 5},
    RecoveryState.CAUTIOUS: {"max_leverage": 5,  "min_confidence": 0.5, "mtf_min_score": 6},
    RecoveryState.RECOVERY: {"max_leverage": 3,  "min_confidence": 0.6, "mtf_min_score": 7},
    RecoveryState.CRITICAL: {"max_leverage": 2,  "min_confidence": 0.7, "mtf_min_score": 8},
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
        """Single entry point: assess drawdown, daily loss, and return action + params."""
        now = datetime.now(timezone.utc)

        # 1. Total drawdown → EMERGENCY_CLOSE (most severe)
        if portfolio.drawdown_pct >= self.config.max_total_drawdown:
            self._halted = True
            self._cooldown_until = None  # requires manual reset
            self._save_state()
            logger.critical(
                f"EMERGENCY CLOSE: drawdown {portfolio.drawdown_pct:.1%} >= {self.config.max_total_drawdown:.1%}"
            )
            if self._last_action != ShieldAction.EMERGENCY_CLOSE:
                self._last_action = ShieldAction.EMERGENCY_CLOSE
                return DefenseResult(ShieldAction.EMERGENCY_CLOSE, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL])
            return DefenseResult(ShieldAction.ALREADY_NOTIFIED, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL])

        # 2. Daily loss → HALT 24h
        daily_loss_pct = abs(portfolio.daily_pnl) / max(portfolio.peak_equity, 1.0)
        if portfolio.daily_pnl < 0 and daily_loss_pct >= self.config.max_daily_loss:
            if not self._halted:
                self._halted = True
                self._cooldown_until = now + timedelta(hours=24)
                self._save_state()
            if self._last_log_time is None or (now - self._last_log_time).total_seconds() >= self.LOG_INTERVAL_HOURS * 3600:
                self._last_log_time = now
                resume_str = self._cooldown_until.strftime("%H:%M UTC") if self._cooldown_until else "manual reset"
                logger.warning(f"HALT: daily loss {daily_loss_pct:.1%}. Resumes at {resume_str}")
            if self._last_action != ShieldAction.HALT:
                self._last_action = ShieldAction.HALT
                return DefenseResult(ShieldAction.HALT, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL])
            return DefenseResult(ShieldAction.ALREADY_NOTIFIED, RecoveryState.CRITICAL, RECOVERY_PARAMS[RecoveryState.CRITICAL])

        # 3. Recovery state assessment (drawdown-based)
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
        return self._halted

    def is_in_cooldown(self) -> bool:
        if not self._halted:
            return False
        if self._cooldown_until is None:
            return True  # requires manual reset
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
        if self._just_resumed:
            self._just_resumed = False
            return True
        return False

    def reset(self) -> None:
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
        state = {
            "halted": self._halted,
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "last_action": self._last_action.value if self._last_action else None,
        }
        try:
            with open(self._STATE_FILE, "w") as f:
                json.dump(state, f)
        except Exception:
            pass

    def _load_state(self) -> None:
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
```

- [ ] **Step 4: Run tests to verify DefenseManager passes**

Run: `cd crypto-beast && source .venv/bin/activate && python -m pytest tests/test_defense_manager.py -v`
Expected: PASS

- [ ] **Step 5: Wire DefenseManager into crypto_system.py**

In `initialize()`: Replace `EmergencyShield` + `RecoveryMode` with `DefenseManager`:
```python
from defense.defense_manager import DefenseManager
m["defense"] = DefenseManager(config)
```

In `run_trading_cycle()`: Replace sections 4-6 (emergency check + cooldown + recovery) with:
```python
        # 4. Defense check (unified recovery + emergency)
        defense_result = m["defense"].check(portfolio)
        if defense_result.action == ShieldAction.EMERGENCY_CLOSE:
            logger.warning("Defense: EMERGENCY_CLOSE")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", "Shield: drawdown limit reached — all positions closed", level="critical")
            return
        elif defense_result.action == ShieldAction.HALT:
            logger.warning("Defense: HALT")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", "Shield: HALT — daily loss limit reached, pausing 24h", level="critical")
            return
        elif defense_result.action == ShieldAction.ALREADY_NOTIFIED:
            return

        # 5. Check cooldown
        if m["defense"].is_in_cooldown():
            logger.info("In cooldown, skipping trading")
            return

        if m["defense"].pop_just_resumed():
            m["notifier"].send("Resume", "Shield cooldown expired, resuming trading", level="info")

        recovery_params = defense_result.params
```

Remove the old recovery mode lines (600-601) and the old emergency shield lines (574-597).

Also update where `recovery_params` is used later — it should now come from `defense_result.params`.

Remove `m["emergency_shield"]` and `m["recovery_mode"]` from initialize().

- [ ] **Step 6: Update tests that reference old modules**

Grep for tests importing `EmergencyShield` or `RecoveryMode` and update them.

- [ ] **Step 7: Run full test suite & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add defense/defense_manager.py crypto_system.py tests/test_defense_manager.py && git commit -m "refactor: merge RecoveryMode + EmergencyShield into unified DefenseManager with disk persistence"
```

---

## Chunk 4: Signal Pipeline — Activate MTF, Remove Double Dedup, Integrate Intel

### Task 10: Activate MTF filter_signal() in trading loop

**Files:**
- Modify: `crypto-beast/crypto_system.py:669-681` (signal filtering section)

- [ ] **Step 1: Add MTF filter after AntiTrap check**

After the AntiTrap check (line 681), add:

```python
                # MTF confluence filter — signal must align with higher timeframes
                from core.models import SignalType
                mtf_direction = SignalType.BULLISH if signal.direction == Direction.LONG else SignalType.BEARISH
                mtf_min = recovery_params.get("mtf_min_score", 5)
                confluence = m["multi_timeframe"].get_confluence(signal.symbol)
                if confluence and abs(confluence.score) >= mtf_min:
                    if confluence.direction != mtf_direction:
                        logger.debug(f"MTF filter: {signal.symbol} signal {signal.direction.value} conflicts with MTF {confluence.direction.value}")
                        try:
                            self.db.execute(
                                "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                                (signal.symbol, signal.direction.value, signal.strategy,
                                 f"mtf_filter: signal conflicts with MTF direction (score={confluence.score})",
                                 signal.entry_price, datetime.now(timezone.utc).isoformat())
                            )
                        except Exception:
                            pass
                        continue
                # If MTF score is weak (below threshold), let signal through — don't block on insufficient data
```

Note: This only blocks signals that CONFLICT with strong MTF direction. Weak/neutral MTF lets signals through (avoids over-filtering).

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "feat: activate MTF confluence filter to block signals conflicting with higher timeframes"
```

---

### Task 11: Remove double signal dedup

**Files:**
- Modify: `crypto-beast/crypto_system.py:661-663`

- [ ] **Step 1: Remove redundant dedup in main loop**

StrategyEngine already deduplicates to 1 best signal per symbol. Remove:
```python
            # Deduplicate: keep only highest confidence per symbol
            best_signal = max(signals, key=lambda s: s.confidence)
            signals = [best_signal]
```

The pattern scanner signals should still be appended before this point, so instead just sort by confidence:
```python
            # Sort by confidence (strategy engine already deduped per symbol, pattern signals added)
            signals.sort(key=lambda s: s.confidence, reverse=True)
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "refactor: remove redundant signal dedup (already done in StrategyEngine)"
```

---

### Task 12: Integrate Layer 1 intel modules into signal confidence

Currently: whale_signal, sentiment_signal, liquidation_signal, orderbook_signal are fetched but discarded (lines 535-537).

**Files:**
- Modify: `crypto-beast/crypto_system.py` (signal generation section)
- Modify: `crypto-beast/strategy/strategy_engine.py` (accept intel biases)

- [ ] **Step 1: Collect intel biases per symbol in main loop**

Replace the intel signal collection block (lines 534-537, currently inside the per-symbol data loop) to store results:

After line 537, the signals are just assigned to local vars that go out of scope. Instead, store them in a dict:

Before the main data feeding loop (before line 489), add:
```python
        intel_biases = {}  # symbol -> list of DirectionalBias
```

In the per-symbol loop (after line 537), collect them:
```python
            # Collect intel biases for signal enhancement
            biases = []
            if whale_signal and whale_signal.confidence > 0.3:
                biases.append(whale_signal)
            if sentiment_signal and sentiment_signal.confidence > 0.3:
                biases.append(sentiment_signal)
            if liquidation_signal and liquidation_signal.confidence > 0.3:
                biases.append(liquidation_signal)
            try:
                if orderbook_signal and orderbook_signal.confidence > 0.3:
                    biases.append(orderbook_signal)
            except Exception:
                pass
            if biases:
                intel_biases[symbol] = biases
```

- [ ] **Step 2: Apply intel biases to signal confidence**

In the signal processing section (after generating signals, before anti-trap filter), add intel adjustment:

```python
                # Apply intelligence module biases
                symbol_biases = intel_biases.get(signal.symbol, [])
                if symbol_biases:
                    from core.models import SignalType
                    signal_type = SignalType.BULLISH if signal.direction == Direction.LONG else SignalType.BEARISH
                    agreement_count = sum(1 for b in symbol_biases if b.direction == signal_type)
                    conflict_count = sum(1 for b in symbol_biases if b.direction != signal_type and b.direction != SignalType.NEUTRAL)
                    # Each agreeing intel source adds +0.03, each conflicting subtracts -0.05
                    intel_adj = agreement_count * 0.03 - conflict_count * 0.05
                    signal.confidence = max(0.05, min(1.0, signal.confidence + intel_adj))
                    if intel_adj != 0:
                        logger.debug(f"Intel adjustment for {signal.symbol}: {intel_adj:+.2f} ({agreement_count} agree, {conflict_count} conflict)")
```

- [ ] **Step 3: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "feat: integrate Layer 1 intel modules (whale/sentiment/liquidation/orderbook) into signal confidence"
```

---

### Task 13: Fix paper mode confidence floor

**Files:**
- Modify: `crypto-beast/crypto_system.py:685-686`

- [ ] **Step 1: Remove the paper mode override that drops min_confidence to 0.15**

Replace:
```python
                min_conf_recovery = recovery_params.get("min_confidence", 0.5)
                if self.paper_mode:
                    min_conf_recovery = min(0.15, min_conf_recovery)
```

With:
```python
                min_conf_recovery = recovery_params.get("min_confidence", 0.3)
```

Paper mode should use the same thresholds as live to produce realistic test results.

Also replace line 701:
```python
                min_conf = 0.1 if self.paper_mode else 0.3
```
With:
```python
                min_conf = 0.3
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: paper mode uses same confidence thresholds as live for realistic testing"
```

---

## Chunk 5: Small Account Optimization & Slippage Monitoring

### Task 14: Add slippage monitoring

**Files:**
- Modify: `crypto-beast/crypto_system.py` (after successful execution)

- [ ] **Step 1: Log slippage after trade execution**

After `result = await m["executor"].execute(plan)` (line 742), enhance the success block:

```python
                if result.success:
                    opened_this_cycle += 1
                    m["fee_optimizer"].record_fee(result.fees_paid)
                    self._daily_fees += result.fees_paid
                    # Track slippage
                    expected_price = signal.entry_price
                    actual_price = result.avg_fill_price
                    slippage_pct = abs(actual_price - expected_price) / expected_price
                    if slippage_pct > 0.001:  # > 0.1% slippage
                        logger.warning(
                            f"HIGH SLIPPAGE: {symbol} expected ${expected_price:,.2f} got ${actual_price:,.2f} "
                            f"({slippage_pct:.3%})"
                        )
                    m["notifier"].send(
                        "Trade Opened",
                        f"{signal.direction.value} {symbol} @ ${result.avg_fill_price:,.2f} | "
                        f"qty={result.total_filled:.6f} | conf={signal.confidence:.2f} | "
                        f"slip={slippage_pct:.3%} | strategy={signal.strategy}",
                    )
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "feat: add slippage monitoring and high-slippage warnings"
```

---

### Task 15: Fix SmartOrder DCA bypass in paper mode

**Files:**
- Modify: `crypto-beast/crypto_system.py:738`

- [ ] **Step 1: Fix urgency calculation**

Replace:
```python
                urgency = 1.0 if portfolio.equity < 500 else signal.confidence
```

With:
```python
                # Small accounts (<$500) use single entry to meet min notional
                # But let DCA work in paper mode for testing (use 0.6 to trigger DCA splitting)
                if portfolio.equity < 500 and not self.paper_mode:
                    urgency = 1.0
                else:
                    urgency = signal.confidence
```

This means paper mode can test DCA splitting while live small accounts still use single entry (necessary to meet min notional).

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: allow DCA testing in paper mode (small account bypass only applies to live)"
```

---

### Task 16: Relax DefenseManager params for small accounts

**Files:**
- Modify: `crypto-beast/defense/defense_manager.py`

Already done in Task 9 — the new RECOVERY_PARAMS table is relaxed:
- NORMAL: min_confidence 0.3 (was 0.5), mtf_min 5 (was 6)
- CAUTIOUS: max_leverage 5 (was 3), min_confidence 0.5 (was 0.75)
- RECOVERY: max_leverage 3 (was 2), min_confidence 0.6 (was 0.8)
- CRITICAL: max_leverage 2 (was 1), min_confidence 0.7 (was 0.9)

This ensures CRITICAL state still allows trading (leverage 2x, confidence 0.7) instead of effectively disabling it (was 1x leverage, 0.9 confidence).

No additional changes needed — already covered in Task 9.

---

## Chunk 6: Close Evolution Feedback Loop & Cleanup

### Task 17: Connect TradeReviewer recommendations to Evolver

**Files:**
- Modify: `crypto-beast/crypto_system.py` (scheduler, daily evolution section)

- [ ] **Step 1: Feed actual trade data to TradeReviewer and pass results to Evolver**

In the scheduler's daily evolution block (lines 845-871), the TradeReviewer is called with empty list:
```python
recommendations=m["trade_reviewer"].get_recommendations([])
```

Fix to use actual yesterday's trades:

```python
            # Daily evolution at 00:10 UTC
            if now.hour == 0 and now.minute == 10:
                logger.info("Running daily evolution")
                try:
                    # Get yesterday's closed trades for recommendations
                    yesterday_trades = self.db.execute(
                        "SELECT * FROM trades WHERE status = 'CLOSED' AND exit_time >= date('now', '-1 day')"
                    ).fetchall()
                    trade_dicts = []
                    for t in yesterday_trades:
                        trade_dicts.append({
                            "id": t[0], "pnl": t[7], "fees": t[8],
                            "side": t[2], "regime": "RANGING", "strategy": t[9]
                        })

                    # Generate recommendations from actual data
                    recommendations = []
                    if trade_dicts:
                        report = m["trade_reviewer"].generate_report(trade_dicts)
                        recommendations = report.recommendations

                    # Gather klines for evolution
                    data_feed = m["data_feed"]
                    evolution_data = {}
                    for symbol in data_feed.symbols:
                        klines = data_feed.get_klines(symbol, "5m")
                        if len(klines) >= 200:
                            evolution_data[symbol] = klines

                    if evolution_data:
                        report = await m["evolver"].run_daily_evolution(
                            data=evolution_data,
                            recommendations=recommendations
                        )
                        if report:
                            m["strategy_engine"].update_weights(report.strategy_weights)
                            m["notifier"].send(
                                "Evolution Complete",
                                f"Sharpe: {report.backtest_sharpe_before:.3f} -> {report.backtest_sharpe_after:.3f}",
                                level="info"
                            )
                except Exception as e:
                    logger.error(f"Daily evolution failed: {e}")
```

- [ ] **Step 2: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add crypto_system.py && git commit -m "fix: connect TradeReviewer recommendations to daily evolution (was passing empty list)"
```

---

### Task 18: Remove duplicate parameter definitions

**Files:**
- Modify: `crypto-beast/execution/position_manager.py:14-15,24`

- [ ] **Step 1: Remove defaults from PositionManager, require Config values**

Replace:
```python
DEFAULT_PROFIT_PROTECT_ACTIVATION_PCT = 0.02
DEFAULT_PROFIT_PROTECT_DRAWBACK_PCT = 0.50

class PositionManager:
    def __init__(self, db: Database, get_price_fn: Callable[[str], float],
                 executor=None,
                 profit_protect_activation_pct: float = DEFAULT_PROFIT_PROTECT_ACTIVATION_PCT,
                 profit_protect_drawback_pct: float = DEFAULT_PROFIT_PROTECT_DRAWBACK_PCT):
```

With:
```python
class PositionManager:
    def __init__(self, db: Database, get_price_fn: Callable[[str], float],
                 config: "Config", executor=None):
        self.db = db
        self._get_price = get_price_fn
        self._executor = executor
        self._profit_protect_activation_pct = config.profit_protect_activation_pct
        self._profit_protect_drawback_pct = config.profit_protect_drawback_pct
```

- [ ] **Step 2: Update PositionManager instantiation in crypto_system.py**

Find where PositionManager is created and pass `config` instead of individual params.

- [ ] **Step 3: Run tests & commit**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q && git add execution/position_manager.py crypto_system.py && git commit -m "refactor: PositionManager reads from Config (remove duplicate param definitions)"
```

---

### Task 19: Final cleanup — remove old modules

**Files:**
- Delete: `crypto-beast/execution/recovery_mode.py` (replaced by DefenseManager)
- Modify: `crypto-beast/crypto_system.py` (remove any remaining old imports)

- [ ] **Step 1: Remove recovery_mode.py**

Delete the file. Ensure no imports reference it.

```bash
cd "crypto-beast" && grep -r "recovery_mode" --include="*.py" | grep -v tests | grep -v .venv | grep -v __pycache__ | grep -v defense_manager
```

Update any remaining references.

- [ ] **Step 2: Run full test suite**

```bash
cd "crypto-beast" && source .venv/bin/activate && python -m pytest -q
```
Expected: All tests pass

- [ ] **Step 3: Final commit**

```bash
cd "crypto-beast" && git add -A && git commit -m "refactor: remove deprecated recovery_mode.py (replaced by DefenseManager)"
```

---

## Summary of Changes

| # | Type | Description | Impact |
|---|------|-------------|--------|
| 1 | Bug | Fix datetime.utcnow() everywhere | Prevent HALT timing bugs |
| 2 | Bug | Fix no-op leverage cap | Enforce recovery leverage limits |
| 3 | Bug | Fix emergency close missing fees | Accurate PnL tracking |
| 4 | Bug | Fix watchdog state race condition | Prevent missed close commands |
| 5 | Bug | Fix peak tracking on reconciliation | Profit protection works after restart |
| 6 | ~~Under-design~~ | ~~Persist HALT to disk~~ | Covered by Task 9 (DefenseManager) |
| 7 | Over-design | Remove 7 unused config params | Reduce config noise 15% |
| 8 | Over-design | FeeOptimizer uses Config values | Single source of truth |
| 9 | Redundancy | Merge Recovery + Shield → DefenseManager | One state machine, not two |
| 10 | Under-design | Activate MTF filter | Block signals conflicting with higher TF |
| 11 | Redundancy | Remove double signal dedup | Cleaner pipeline |
| 12 | Over-design | Integrate intel modules into signals | 4 modules no longer wasted |
| 13 | Under-design | Fix paper mode confidence | Realistic paper testing |
| 14 | Under-design | Add slippage monitoring | Track execution quality |
| 15 | Over-design | Fix DCA paper mode bypass | Can test DCA in paper |
| 16 | Under-design | Relax recovery params | Small account can trade in recovery |
| 17 | Over-design | Close evolution feedback loop | Recommendations actually used |
| 18 | Redundancy | Remove duplicate param definitions | Single source of truth |
| 19 | Cleanup | Delete deprecated recovery_mode.py | Remove dead code |
