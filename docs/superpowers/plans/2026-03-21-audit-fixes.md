# Crypto Beast v1.6.0 Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 18 issues found during system audit to unlock trading capability and achieve stable high-profit operation.

**Architecture:** Two-phase approach — Phase 1 (Tasks 1-12) fixes critical bugs and optimizes parameters in existing modules; Phase 2 (Tasks 13-18) adds new WebSocket data sources, IPC, and enhanced algorithms. All changes follow existing async patterns, Python 3.9.6 compatibility (Optional[X], Dict, List), and hedge-mode Binance Futures conventions.

**Tech Stack:** Python 3.9.6, asyncio, aiohttp, ccxt, pandas, ta, loguru, sqlite3, Binance Futures API, WebSocket (websockets library)

**Spec:** `docs/superpowers/specs/2026-03-21-audit-fixes-design.md`

---

## File Map

### Phase 1: Modified Files
| File | Changes |
|------|---------|
| `core/models.py` | Add `_strategy_weight` field to TradeSignal |
| `strategy/strategy_engine.py` | Fix confidence weighting, dedup logic |
| `crypto_system.py` | Remove LIMIT override, fix circuit breaker lock, merge API calls, lower intel adj |
| `risk/risk_manager.py` | Add directional exposure limit, continuous scaling, stronger correlation penalty |
| `execution/executor.py` | Persistent aiohttp session, cached API keys, new `get_positions_and_account()` |
| `execution/position_manager.py` | Timeout close, profit protection params, breakeven SL queue |
| `defense/defense_manager.py` | HALT 8h, CAUTIOUS 8%, relaxed RECOVERY_PARAMS |
| `config.py` | New config fields, adjusted defaults |
| `strategy/scalper.py` | SL 0.3 ATR, TP 1.5 ATR |
| `strategy/mean_reversion.py` | TP to opposite BB |
| `strategy/breakout.py` | SL to 2.0 ATR |
| `strategy/funding_rate_arb.py` | SL 1.5 ATR, TP 3.0 ATR |

### Phase 2: New + Modified Files
| File | Changes |
|------|---------|
| `data/ws_manager.py` | NEW — Binance WebSocket manager |
| `data/user_data_stream.py` | NEW — User Data Stream (account updates) |
| `ipc/__init__.py` | NEW — package init |
| `ipc/socket_ipc.py` | NEW — Unix domain socket IPC |
| `analysis/multi_timeframe.py` | Gradient voting, neutral zone |
| `strategy/trend_follower.py` | Dynamic confidence |
| `strategy/momentum.py` | Dynamic confidence |
| `strategy/breakout.py` | Dynamic confidence |
| `strategy/scalper.py` | Dynamic confidence |
| `strategy/mean_reversion.py` | Dynamic confidence |
| `execution/position_manager.py` | Breakeven SL movement |
| `data/whale_tracker.py` | WebSocket data input method |
| `data/liquidation_hunter.py` | WebSocket data input method |
| `data/orderbook_sniper.py` | WebSocket data input method |

---

## Phase 1: Critical Fixes (#1-#12)

**Execution order follows spec Section 7 dependencies:**
Tasks 1(#1) → 2(#9) → 3(#3) → 4(#11) → 5(#2) → 6(#4) → 7(#5) → 8(#12) → 9(#6) → 10(#8) → 11(#7) → 12(#10)

Rationale: #9 (continuous scaling) depends on #1 (correct confidence); #3 (exposure limit) depends on #9 (correct position sizing).

### Task 1: Fix confidence weight multiplication (#1)

**Files:**
- Modify: `core/models.py:59-71`
- Modify: `strategy/strategy_engine.py:41-80`
- Test: `tests/strategy/test_strategy_engine.py`

- [ ] **Step 1: Write failing test — confidence not crushed by weight**

```python
# tests/strategy/test_strategy_engine.py — add at end of file
def test_confidence_not_crushed_by_strategy_weight(engine, uptrend_data):
    """Fix #1: strategy_weight must NOT multiply into confidence."""
    signals = engine.generate_signals("BTCUSDT", uptrend_data)
    if signals:
        # With old code, confidence would be ~0.05-0.2 (crushed by 0.2 weight)
        # With fix, confidence should be >= 0.25 (only session_weight applied)
        assert signals[0].confidence >= 0.25, (
            f"Confidence {signals[0].confidence} still crushed by strategy weight"
        )


def test_dedup_uses_weighted_score(engine, uptrend_data):
    """Fix #1: dedup should use confidence * strategy_weight for selection."""
    # Generate signals — dedup should pick best weighted_score per symbol
    signals = engine.generate_signals("BTCUSDT", uptrend_data)
    # All signals for same symbol should be deduped to one
    symbols = [s.symbol for s in signals]
    assert len(symbols) == len(set(symbols)), "Dedup failed: duplicate symbols"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/strategy/test_strategy_engine.py::test_confidence_not_crushed_by_strategy_weight tests/strategy/test_strategy_engine.py::test_dedup_uses_weighted_score -v`
Expected: FAIL on first test (confidence < 0.25)

- [ ] **Step 3: Add `_strategy_weight` field to TradeSignal**

In `core/models.py`, add to the `TradeSignal` dataclass after `timestamp`:
```python
    _strategy_weight: float = field(default=0.2, repr=False, compare=False)
```

- [ ] **Step 4: Fix strategy_engine.py generate_signals**

Replace `strategy/strategy_engine.py` lines 60-80 with:
```python
        signals: List[TradeSignal] = []

        for name, strategy in self._strategies.items():
            raw_signals = strategy.generate(klines, symbol, regime)
            for sig in raw_signals:
                # Session weight as mild time-of-day adjustment (0.5-1.3 range)
                # Strategy weight NOT applied to confidence — only used for dedup ranking
                session_w = session_weights.get(name, 1.0)
                sig.confidence = round(sig.confidence * session_w, 4)
                sig._strategy_weight = self._weights.get(name, 0.2)
                if confluence is not None:
                    sig.timeframe_score = confluence.score
                signals.append(sig)

        # Deduplicate: per symbol, keep highest weighted_score signal
        # weighted_score = confidence * strategy_weight ensures regime-appropriate
        # strategies win selection, while raw confidence drives position sizing
        best_per_symbol: Dict[str, tuple] = {}
        for sig in signals:
            key = sig.symbol
            weighted_score = sig.confidence * sig._strategy_weight
            if key not in best_per_symbol or weighted_score > best_per_symbol[key][0]:
                best_per_symbol[key] = (weighted_score, sig)

        return sorted(
            [v[1] for v in best_per_symbol.values()],
            key=lambda s: s.confidence, reverse=True,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/strategy/test_strategy_engine.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite to check regressions**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: 409 tests pass (some may need TradeSignal fixture updates if they check exact field count)

---

### Task 2: Continuous position scaling + base_risk (#9)

> **EXECUTE AFTER Task 1.** Depends on #1's correct confidence for meaningful scaling.

**Files:**
- Modify: `risk/risk_manager.py:112-119`
- Modify: `config.py:20`
- Test: `tests/defense/test_risk_manager.py`

- [ ] **Step 1: Write failing test**

```python
# tests/defense/test_risk_manager.py — add
def test_continuous_risk_scaling(risk_manager, empty_portfolio):
    """Fix #9: risk_multiplier should be continuous, not 3-step."""
    sig_low = TradeSignal(symbol="BTCUSDT", direction=Direction.LONG, confidence=0.35,
                          entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
                          strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8)
    sig_high = TradeSignal(symbol="BTCUSDT", direction=Direction.LONG, confidence=0.90,
                           entry_price=65000.0, stop_loss=64000.0, take_profit=67000.0,
                           strategy="test", regime=MarketRegime.TRENDING_UP, timeframe_score=8)

    result_low = risk_manager.validate(sig_low, empty_portfolio)
    result_high = risk_manager.validate(sig_high, empty_portfolio)
    if result_low and result_high:
        # High confidence should get significantly larger position
        assert result_high.quantity > result_low.quantity * 1.5, (
            "High confidence should get >1.5x the position of low confidence"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/defense/test_risk_manager.py::test_continuous_risk_scaling -v`
Expected: FAIL (3-step gives equal positions for 0.35 and some ranges)

- [ ] **Step 3: Update config**

In `config.py`: `max_risk_per_trade: float = 0.03`  (from 0.02)

- [ ] **Step 4: Implement continuous scaling**

Replace the 3-step if/elif/else in `risk_manager.py` with continuous formula:
```python
MIN_CONF = 0.3
MAX_MULTIPLIER = 3.5
risk_multiplier = 1.0 + (signal.confidence - MIN_CONF) / (1.0 - MIN_CONF) * (MAX_MULTIPLIER - 1.0)
risk_multiplier = max(1.0, min(MAX_MULTIPLIER, risk_multiplier))
```

- [ ] **Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/defense/test_risk_manager.py -v`
Expected: ALL PASS

---

### Task 3: Add directional exposure limit (#3)

> **EXECUTE AFTER Task 2.** Exposure limits depend on #9's correct position sizing.

**Files:**
- Modify: `risk/risk_manager.py`
- Modify: `config.py`
- Test: `tests/defense/test_risk_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/defense/test_risk_manager.py — add at end

def test_directional_exposure_limit(risk_manager, empty_portfolio, long_signal):
    """Fix #3: reject signal when same-dir exposure exceeds 15x equity."""
    # Add 2 large LONG positions (each 8x exposure = 16x total > 15x limit)
    pos1 = Position(symbol="ETHUSDT", direction=Direction.LONG, entry_price=3000.0,
                    quantity=0.27, leverage=10, unrealized_pnl=0.0, strategy="test",
                    entry_time=None, current_stop=2900.0)
    pos2 = Position(symbol="SOLUSDT", direction=Direction.LONG, entry_price=150.0,
                    quantity=5.0, leverage=10, unrealized_pnl=0.0, strategy="test",
                    entry_time=None, current_stop=145.0)
    portfolio = Portfolio(
        equity=100.0, available_balance=20.0,
        positions=[pos1, pos2],  # ~800+750 = ~1550 notional, 15.5x
        peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
        total_fees_today=0.0, drawdown_pct=0.0,
    )
    result = risk_manager.validate(long_signal, portfolio)
    assert result is None, "Should reject: directional exposure exceeds 15x"


def test_correlated_same_dir_limit(risk_manager, empty_portfolio):
    """Fix #3: max 2 correlated assets same direction."""
    # Already 2 LONG in correlated group (BTC + ETH)
    pos1 = Position(symbol="BTCUSDT", direction=Direction.LONG, entry_price=65000.0,
                    quantity=0.001, leverage=5, unrealized_pnl=0.0, strategy="test",
                    entry_time=None, current_stop=63000.0)
    pos2 = Position(symbol="ETHUSDT", direction=Direction.LONG, entry_price=3000.0,
                    quantity=0.01, leverage=5, unrealized_pnl=0.0, strategy="test",
                    entry_time=None, current_stop=2900.0)
    portfolio = Portfolio(
        equity=100.0, available_balance=80.0,
        positions=[pos1, pos2],
        peak_equity=100.0, locked_capital=0.0, daily_pnl=0.0,
        total_fees_today=0.0, drawdown_pct=0.0,
    )
    # SOL LONG should be rejected (3rd correlated asset same direction)
    sol_signal = TradeSignal(
        symbol="SOLUSDT", direction=Direction.LONG, confidence=0.7,
        entry_price=150.0, stop_loss=145.0, take_profit=160.0,
        strategy="trend_follower", regime=MarketRegime.TRENDING_UP,
        timeframe_score=8,
    )
    result = risk_manager.validate(sol_signal, portfolio)
    assert result is None, "Should reject: 3rd correlated asset same direction"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/defense/test_risk_manager.py::test_directional_exposure_limit tests/defense/test_risk_manager.py::test_correlated_same_dir_limit -v`
Expected: FAIL (no directional exposure check exists yet)

- [ ] **Step 3: Add config fields**

In `config.py`, add after `circuit_breaker_pct`:
```python
    max_directional_leverage: float = 15.0
    max_correlated_same_dir: int = 2
    correlation_penalty: float = 0.6
```

- [ ] **Step 4: Implement directional exposure check in risk_manager.py**

Add the `_check_directional_exposure` method and call it in `validate()` after the existing correlation penalty. Also change the correlation penalty from `0.8` to `config.correlation_penalty`.

See spec Section 3.3 for full implementation.

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/defense/test_risk_manager.py -v`
Expected: ALL PASS

---

### Task 4: Fix aiohttp session leak (#4)

**Files:**
- Modify: `execution/executor.py:1-33, 250-287, 446-527, 543-654`
- Test: `tests/execution/test_executor.py`

- [ ] **Step 1: Write failing test**

```python
# tests/execution/test_executor.py — add
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_http_session_reused():
    """Fix #4: aiohttp session should be created once and reused."""
    from execution.executor import LiveExecutor
    from core.database import Database
    from core.rate_limiter import BinanceRateLimiter

    db = MagicMock(spec=Database)
    exchange = MagicMock()
    rl = MagicMock(spec=BinanceRateLimiter)
    rl.acquire_order_slot = AsyncMock()

    executor = LiveExecutor(exchange, db, rl)
    # Should have cached API keys from .env
    assert hasattr(executor, '_api_key')
    assert hasattr(executor, '_api_secret')
    # Session should be None initially (lazy init)
    assert executor._http_session is None

    await executor.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_executor.py::test_http_session_reused -v`
Expected: FAIL (no `_api_key` attribute)

- [ ] **Step 3: Implement persistent session and cached keys**

Modify `LiveExecutor.__init__` to cache API keys and add `_http_session`. Add `_get_http_session()` and `close()`. Replace all `async with aiohttp.ClientSession()` in `_place_algo_order`, `cancel_algo_orders`, and `ensure_sl_orders` with `session = await self._get_http_session()`. Remove all `dotenv_values()` calls from those methods.

See spec Section 3.4 for full implementation.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_executor.py -v`
Expected: ALL PASS

---

### Task 5: Fix circuit breaker file lock (#5)

**Files:**
- Modify: `crypto_system.py:~700-708`

- [ ] **Step 1: Locate circuit breaker watchdog.state writes**

In `crypto_system.py` around line 700-708, find the raw `json.load`/`json.dump` for watchdog.state.

- [ ] **Step 2: Replace with locked write**

```python
import fcntl

def _write_watchdog_state_safe(state_path, updates):
    """Atomic write to watchdog.state with file lock."""
    if not os.path.exists(state_path):
        with open(state_path, "w") as f:
            json.dump({}, f)
    with open(state_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.load(f)
            data.update(updates)
            f.seek(0)
            f.truncate()
            json.dump(data, f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

Replace the raw writes with calls to this function.

- [ ] **Step 3: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: All pass

- [ ] **Step 4: Commit Phase 1 P0 fixes (Tasks 1-8)**

```bash
git add core/models.py strategy/strategy_engine.py crypto_system.py risk/risk_manager.py execution/executor.py defense/defense_manager.py config.py tests/
git commit -m "fix(P0): confidence weight, scaling, exposure limit, HALT, session leak, file lock

Fixes #1,#9,#3,#11,#2,#4,#5,#12 from system audit:
- #1: strategy_weight no longer multiplied into confidence (was crushing 0.8→0.096)
- #9: Continuous position scaling 3%→10.5% (replaces 3-step)
- #3: Added 15x directional exposure limit and correlated asset cap
- #11: HALT 24h→8h, CAUTIOUS 5%→8%, relaxed RECOVERY_PARAMS
- #2: Removed LIMIT entry override for small accounts (SL protection gap)
- #4: Persistent aiohttp session + cached API keys (was leaking connections)
- #5: Circuit breaker uses fcntl file lock for watchdog.state
- #12: Merged double fapiPrivateV2GetAccount call"
```

---

### Task 6: SL/TP ratio optimization (#6)

**Files:**
- Modify: `strategy/scalper.py`
- Modify: `strategy/mean_reversion.py`
- Modify: `strategy/breakout.py`
- Modify: `strategy/funding_rate_arb.py`
- Test: `tests/strategy/test_scalper.py`, `test_mean_reversion.py`, `test_breakout.py`, `test_funding_rate_arb.py`

- [ ] **Step 1: Write failing tests for new R:R ratios**

```python
# tests/strategy/test_scalper.py — add
def test_scalper_rr_ratio(sample_klines):
    """Fix #6: Scalper R:R should be >= 1:4 (SL 0.3 ATR, TP 1.5 ATR)."""
    from strategy.scalper import Scalper
    scalper = Scalper()
    signals = scalper.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING)
    for sig in signals:
        sl_dist = abs(sig.entry_price - sig.stop_loss)
        tp_dist = abs(sig.take_profit - sig.entry_price)
        if sl_dist > 0:
            rr = tp_dist / sl_dist
            assert rr >= 4.0, f"Scalper R:R {rr:.1f} < 4.0"

# tests/strategy/test_funding_rate_arb.py — add
def test_funding_rate_arb_rr_not_inverted(sample_klines):
    """Fix #6: FundingRateArb R:R must be >= 1.5 (was inverted at 0.75)."""
    from strategy.funding_rate_arb import FundingRateArb
    from core.models import MarketRegime
    arb = FundingRateArb()
    # Simulate extreme funding rate by calling generate with high funding
    signals = arb.generate(sample_klines, "BTCUSDT", MarketRegime.RANGING,
                           funding_rate=0.002)  # extreme funding
    for sig in signals:
        sl_dist = abs(sig.entry_price - sig.stop_loss)
        tp_dist = abs(sig.take_profit - sig.entry_price)
        if sl_dist > 0:
            rr = tp_dist / sl_dist
            assert rr >= 1.5, f"FundingRateArb R:R {rr:.2f} < 1.5 (inverted!)"
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Update SL/TP in each strategy**

See spec Section 3.6 for exact changes per strategy file.

- [ ] **Step 4: Run strategy tests**

Run: `source .venv/bin/activate && python -m pytest tests/strategy/ -v`
Expected: ALL PASS

---

### Task 7: Add 48h timeout close (#7)

**Files:**
- Modify: `execution/position_manager.py:45-52, 100-117`
- Modify: `config.py`
- Test: `tests/execution/test_position_manager.py`

- [ ] **Step 1: Write failing test**

```python
# tests/execution/test_position_manager.py — add
from datetime import datetime, timezone, timedelta

def test_timeout_closes_stale_position(db):
    """Fix #7: positions held > 48h with small PnL should be closed."""
    # Insert a trade with entry_time 50 hours ago
    entry_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    db.execute(
        "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, "
        "strategy, entry_time, fees, status, stop_loss, take_profit, peak_profit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "LONG", 65000.0, 0.001, 5, "test", entry_time,
         0.01, "OPEN", 63000.0, 67000.0, 0.0)
    )
    from config import Config
    config = Config()
    # Current price near entry (small PnL within timeout range)
    pm = PositionManager(db, lambda s: 65100.0, config)
    to_close = pm.check_positions()
    reasons = [t["reason"] for t in to_close]
    assert "TIMEOUT" in reasons, f"Expected TIMEOUT, got {reasons}"


def test_no_timeout_if_profitable(db):
    """Fix #7: don't timeout positions with >2% leveraged PnL."""
    entry_time = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat()
    db.execute(
        "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, "
        "strategy, entry_time, fees, status, stop_loss, take_profit, peak_profit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "LONG", 65000.0, 0.001, 10, "test", entry_time,
         0.01, "OPEN", 63000.0, 67000.0, 0.0)
    )
    from config import Config
    config = Config()
    # Price at 65500 = 0.77% move * 10x leverage = 7.7% leveraged PnL (>2%)
    pm = PositionManager(db, lambda s: 65500.0, config)
    to_close = pm.check_positions()
    reasons = [t["reason"] for t in to_close]
    assert "TIMEOUT" not in reasons, "Should NOT timeout profitable position"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_position_manager.py::test_timeout_closes_stale_position tests/execution/test_position_manager.py::test_no_timeout_if_profitable -v`

- [ ] **Step 3: Add config fields**

In `config.py`:
```python
    position_timeout_hours: int = 48
    timeout_pnl_min: float = -0.01
    timeout_pnl_max: float = 0.02
```

- [ ] **Step 4: Implement timeout in position_manager.py**

Add `entry_time` to the SQL SELECT query. After profit protection check, add timeout logic per spec Section 3.7. Read timeout params from `config`.

- [ ] **Step 5: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_position_manager.py -v`
Expected: ALL PASS

---

### Task 8: Profit protection parameter optimization (#8)

**Files:**
- Modify: `config.py:57-59`
- Modify: `execution/position_manager.py:101-117`
- Test: `tests/execution/test_position_manager.py`

- [ ] **Step 1: Write failing test**

```python
def test_profit_protection_tighter_drawback(db):
    """Fix #8: max drawback should be 0.35 (not 0.50) for <10% peak."""
    db.execute(
        "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, "
        "strategy, entry_time, fees, status, stop_loss, take_profit, peak_profit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "LONG", 65000.0, 0.001, 10, "test",
         datetime.now(timezone.utc).isoformat(), 0.01, "OPEN", 63000.0, 70000.0, 0.09)
    )
    from config import Config
    config = Config()
    # peak_profit=9%, current should trigger at 35% drawback (not 50%)
    # 9% * 0.35 = 3.15% drawback threshold → profit must drop to 5.85%
    # 9% * 0.65 = 5.85% remaining
    # Need price that gives ~5.8% leveraged PnL
    # 5.8% / 10x = 0.58% price move → 65000 * 1.0058 = 65377
    pm = PositionManager(db, lambda s: 65377.0, config)
    to_close = pm.check_positions()
    # With old 50% drawback, this wouldn't trigger (need drop to 4.5%)
    # With new 35% drawback, should trigger
    reasons = [t["reason"] for t in to_close]
    assert "PROFIT_PROTECT" in reasons
```

- [ ] **Step 2: Update config defaults**

```python
    profit_protect_activation_pct: float = 0.08   # from 0.05
    profit_protect_drawback_pct: float = 0.35      # from 0.50
```

- [ ] **Step 3: Update tiered drawback in position_manager.py**

Update lines 105-112 per spec Section 3.8.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_position_manager.py -v`

---

### Task 9: Remove LIMIT order entry override (#2)

**Files:**
- Modify: `crypto_system.py:~1008-1013`
- Test: `tests/integration/test_pipeline.py` (regression test)

- [ ] **Step 1: Write regression test**

```python
# tests/integration/test_pipeline.py — add
def test_small_account_uses_market_orders():
    """Fix #2: small accounts should always use MARKET, never LIMIT override."""
    # Verify no LIMIT override exists in signal processing path
    import inspect
    import crypto_system
    source = inspect.getsource(crypto_system)
    # The old pattern: confidence <= 0.8 → LIMIT
    assert "confidence" not in source.split("LIMIT")[0][-200:] if "LIMIT" in source else True
```

- [ ] **Step 2: Locate and remove LIMIT override logic**

In `crypto_system.py`, find the block around line 1008-1013 that overrides MARKET to LIMIT when `confidence <= 0.8`. Remove it and add a comment:

```python
# LIMIT entry override removed (v1.6.0 fix #2):
# Small accounts ($200) save ~$0.004/trade with LIMIT vs MARKET,
# but risk LIMIT not filling + no SL placement (5min unprotected window).
# All entries now use MARKET for reliable fills.
```

- [ ] **Step 3: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: All pass

---

### Task 10: Lower intel adjustment (#10)

**Files:**
- Modify: `crypto_system.py:~897-907`

- [ ] **Step 1: Locate intel adjustment constants**

Find `0.03` and `0.05` in the intel agreement/conflict section.

- [ ] **Step 2: Replace with reduced values**

```python
INTEL_AGREE_ADJ = 0.01    # from 0.03
INTEL_CONFLICT_ADJ = 0.02  # from 0.05
```

- [ ] **Step 3: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`

---

### Task 11: HALT duration + CAUTIOUS threshold (#11)

**Files:**
- Modify: `defense/defense_manager.py:23-28, 68`
- Modify: `config.py:28`
- Test: `tests/defense/test_defense_manager.py`

- [ ] **Step 1: Write failing test**

```python
# tests/defense/test_defense_manager.py — add
def test_halt_duration_8h():
    """Fix #11: HALT should be 8h, not 24h."""
    from config import Config
    from defense.defense_manager import DefenseManager
    config = Config()
    dm = DefenseManager(config)
    portfolio = Portfolio(
        equity=90.0, available_balance=90.0, positions=[],
        peak_equity=100.0, locked_capital=0.0, daily_pnl=-11.0,
        total_fees_today=0.0, drawdown_pct=0.10,
    )
    result = dm.check(portfolio)
    assert dm._cooldown_until is not None
    hours = (dm._cooldown_until - datetime.now(timezone.utc)).total_seconds() / 3600
    assert 7.5 < hours < 8.5, f"HALT should be ~8h, got {hours:.1f}h"
```

- [ ] **Step 2: Update defense_manager.py**

Change `timedelta(hours=24)` to `timedelta(hours=8)`.
Update `RECOVERY_PARAMS` per spec Section 3.11.

- [ ] **Step 3: Update config**

In `config.py`, add/modify:
```python
recovery_cautious: float = 0.08          # from 0.05
halt_cooldown_hours: int = 8             # NEW — from hardcoded 24
```

In `defense_manager.py`, read from config instead of hardcoding:
```python
self._cooldown_until = now + timedelta(hours=self.config.halt_cooldown_hours)
```

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/defense/ -v`

---

### Task 12: Merge double API call (#12)

**Files:**
- Modify: `execution/executor.py:331-381`
- Modify: `crypto_system.py:~657-663`

- [ ] **Step 1: Add `get_positions_and_account()` to executor.py**

```python
async def get_positions_and_account(self):
    """Fetch positions + account data in single API call.

    Returns:
        Tuple of (positions list, equity float, available_balance float).
    """
    try:
        await self.rate_limiter.acquire_data_slot()
        account = await self.exchange.fapiPrivateV2GetAccount()
        positions = []
        for pos in account.get("positions", []):
            amt = float(pos.get("positionAmt", 0))
            if amt == 0:
                continue
            # NOTE: strategy and entry_time are placeholders here.
            # Reconciliation (reconcile_with_exchange) enriches these from DB.
            # Do NOT rely on these fields from exchange data.
            positions.append(Position(
                symbol=pos["symbol"],
                direction=Direction.LONG if amt > 0 else Direction.SHORT,
                entry_price=float(pos.get("entryPrice", 0)),
                quantity=abs(amt),
                leverage=int(pos.get("leverage", 1)),
                unrealized_pnl=float(pos.get("unrealizedProfit", 0)),
                strategy="exchange",  # placeholder, reconciliation overrides
                entry_time=datetime.now(timezone.utc),  # placeholder
                current_stop=0.0,
            ))
        equity = float(account.get("totalMarginBalance", 0))
        available = float(account.get("availableBalance", 0))
        return positions, equity, available
    except Exception as e:
        logger.error(f"Failed to fetch account: {e}")
        return [], 0.0, 0.0
```

- [ ] **Step 2: Update main loop in crypto_system.py**

Replace separate `get_positions()` + `get_equity()` calls with single `get_positions_and_account()`.

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest -q`

- [ ] **Step 4: Commit Phase 1 P1 fixes (Tasks 9-12)**

```bash
git add strategy/ execution/ config.py crypto_system.py tests/
git commit -m "feat(P1): SL/TP ratios, timeout close, profit protection, intel lowered

Fixes #6,#8,#7,#10 from system audit:
- #6: SL/TP R:R optimized (Scalper 1:5, FundingRateArb 1:2, MeanReversion TP→opposite BB)
- #8: Profit protection activation 5%→8%, drawback 50%→35%
- #7: 48h timeout close for zombie positions
- #10: Intel adjustment lowered (fake data sources)"
```

---

## Phase 2: Deep Optimization (#13-#18)

### Task 13: MTF gradient voting (#14)

**Files:**
- Modify: `analysis/multi_timeframe.py:95-103`
- Modify: `config.py:55`
- Test: `tests/analysis/test_multi_timeframe.py`

- [ ] **Step 1: Write failing test**

```python
# tests/analysis/test_multi_timeframe.py — add
def test_vote_returns_zero_for_flat_market():
    """Fix #14: _vote should return 0 when EMA spread < 0.1%."""
    # Create flat data where EMA9 ≈ EMA21
    n = 50
    close = pd.Series([65000.0] * n)  # Perfectly flat
    df = pd.DataFrame({"close": close})
    from analysis.multi_timeframe import MultiTimeframe
    result = MultiTimeframe._vote(df)
    assert result == 0, f"Flat market should give neutral vote, got {result}"
```

- [ ] **Step 2: Implement gradient voting**

Replace `_vote()` with neutral-aware version per spec Section 3.14.

- [ ] **Step 3: Update config**

`mtf_min_confluence: int = 4`

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/analysis/test_multi_timeframe.py -v`

- [ ] **Step 5: Commit**

```bash
git add analysis/multi_timeframe.py config.py tests/analysis/
git commit -m "feat: MTF gradient voting with neutral zone (#14)"
```

---

### Task 14: Dynamic confidence for all strategies (#15)

**Files:**
- Modify: `strategy/trend_follower.py`
- Modify: `strategy/momentum.py`
- Modify: `strategy/breakout.py`
- Modify: `strategy/scalper.py`
- Modify: `strategy/mean_reversion.py`
- Test: `tests/strategy/test_trend_follower.py`, etc.

- [ ] **Step 1: Write failing tests for continuous confidence**

```python
# tests/strategy/test_trend_follower.py — add
def test_confidence_varies_with_spread(uptrend_data):
    """Fix #15: confidence should scale with EMA spread, not be hardcoded."""
    from strategy.trend_follower import TrendFollower
    tf = TrendFollower()
    signals = tf.generate(uptrend_data, "BTCUSDT", MarketRegime.TRENDING_UP)
    if len(signals) >= 2:
        confs = [s.confidence for s in signals]
        # With dynamic confidence, values should vary (not all 0.5 or 0.6)
        assert max(confs) - min(confs) >= 0.05, (
            f"Confidence too uniform: {confs[:5]} — should vary with signal strength"
        )
```

Add similar tests for each strategy.

- [ ] **Step 2: Implement dynamic confidence per strategy**

Update each strategy's confidence calculation per spec Section 3.15. Key pattern:
```python
base_conf = 0.35 + min(0.45, signal_strength_metric)
# regime adjustment
# volume boost
confidence = min(0.95, max(0.3, base_conf))
```

- [ ] **Step 3: Run all strategy tests**

Run: `source .venv/bin/activate && python -m pytest tests/strategy/ -v`

- [ ] **Step 4: Commit**

```bash
git add strategy/ tests/strategy/
git commit -m "feat: dynamic confidence scaling for all strategies (#15)"
```

---

### Task 15: Breakeven SL movement (#16)

**Files:**
- Modify: `execution/position_manager.py`
- Modify: `config.py`
- Test: `tests/execution/test_position_manager.py`

- [ ] **Step 1: Write failing test**

```python
def test_breakeven_sl_scheduled(db):
    """Fix #16: SL should move to breakeven when profit > 5%."""
    entry = 65000.0
    db.execute(
        "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, "
        "strategy, entry_time, fees, status, stop_loss, take_profit, peak_profit) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BTCUSDT", "LONG", entry, 0.001, 10, "test",
         datetime.now(timezone.utc).isoformat(), 0.01, "OPEN", 63000.0, 70000.0, 0.08)
    )
    from config import Config
    config = Config()
    # Price gives 6% leveraged PnL (> 5% threshold)
    # 6% / 10x = 0.6% price move → 65000 * 1.006 = 65390
    pm = PositionManager(db, lambda s: 65390.0, config)
    pm.check_positions()
    # Check that SL was updated in DB to near entry price
    row = db.execute("SELECT stop_loss FROM trades WHERE status='OPEN'").fetchone()
    assert row[0] > 64000.0, f"SL should have moved up from 63000, got {row[0]}"
```

- [ ] **Step 2: Add config**

`breakeven_sl_threshold: float = 0.05`

- [ ] **Step 3: Implement breakeven SL with pending queue**

Add `_pending_sl_updates` list and `_schedule_sl_update()` / `process_pending_sl_updates()` per spec Section 3.16.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/execution/test_position_manager.py -v`

- [ ] **Step 5: Commit**

```bash
git add execution/position_manager.py config.py tests/execution/
git commit -m "feat: breakeven SL movement when profit > 5% (#16)"
```

---

### Task 16: WebSocket data manager (#13)

**Files:**
- Create: `data/ws_manager.py`
- Modify: `data/whale_tracker.py`
- Modify: `data/liquidation_hunter.py`
- Modify: `data/orderbook_sniper.py`
- Create: `tests/data/test_ws_manager.py`

- [ ] **Step 1: Write test for WSManager**

```python
# tests/data/test_ws_manager.py
import pytest
import asyncio
from data.ws_manager import BinanceWSManager

def test_ws_manager_init():
    """WebSocket manager should initialize with symbols."""
    ws = BinanceWSManager(symbols=["BTCUSDT", "ETHUSDT"])
    assert len(ws._symbols) == 2
    assert not ws._running

def test_ws_manager_callback_registration():
    """Should register and track callbacks."""
    ws = BinanceWSManager(symbols=["BTCUSDT"])
    callback = lambda data: None
    ws.on("aggTrade", callback)
    assert len(ws._callbacks.get("aggTrade", [])) == 1
```

- [ ] **Step 2: Implement ws_manager.py**

Create `data/ws_manager.py` with `BinanceWSManager` class per spec Section 3.13. Key features:
- Multi-stream subscription (aggTrade, forceOrder, depth20)
- Auto-reconnect with exponential backoff (max 60s)
- Callback dispatch by event type
- Graceful shutdown

- [ ] **Step 3: Add WebSocket input methods to data modules**

Add `process_ws_trade()` to WhaleTracker, `process_ws_liquidation()` to LiquidationHunter, `process_ws_depth()` to OrderBookSniper. These accept the raw WebSocket message format instead of the K-line simulation.

- [ ] **Step 4: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/data/ -v`

- [ ] **Step 5: Commit**

```bash
git add data/ws_manager.py data/whale_tracker.py data/liquidation_hunter.py data/orderbook_sniper.py tests/data/
git commit -m "feat: WebSocket data manager for real-time market data (#13)"
```

---

### Task 17: User Data Stream (#18)

**Files:**
- Create: `data/user_data_stream.py`
- Create: `tests/data/test_user_data_stream.py`

- [ ] **Step 1: Write tests**

```python
# tests/data/test_user_data_stream.py
import pytest
from data.user_data_stream import UserDataStream

def test_user_data_stream_init():
    """User Data Stream should initialize without connecting."""
    from unittest.mock import MagicMock
    uds = UserDataStream(MagicMock(), "test_key", "test_secret")
    assert uds._listen_key is None
    assert not uds._ws

def test_user_data_stream_callback_registration():
    from unittest.mock import MagicMock
    uds = UserDataStream(MagicMock(), "test_key", "test_secret")
    cb = lambda data: None
    uds.on("account_update", cb)
    assert len(uds._callbacks.get("account_update", [])) == 1
```

- [ ] **Step 2: Implement user_data_stream.py**

Create per spec Section 3.18. Key features:
- listenKey management (create, extend every 25min, delete on close)
- ACCOUNT_UPDATE and ORDER_TRADE_UPDATE event dispatch
- Auto-reconnect on disconnect
- Fallback to REST polling when WebSocket unavailable

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/data/test_user_data_stream.py -v`

- [ ] **Step 4: Commit**

```bash
git add data/user_data_stream.py tests/data/test_user_data_stream.py
git commit -m "feat: Binance User Data Stream for account updates (#18)"
```

---

### Task 18: Unix socket IPC (#17)

**Files:**
- Create: `ipc/__init__.py`
- Create: `ipc/socket_ipc.py`
- Create: `tests/ipc/__init__.py`
- Create: `tests/ipc/test_socket_ipc.py`

- [ ] **Step 1: Write tests**

```python
# tests/ipc/test_socket_ipc.py
import pytest
import asyncio
import json
from ipc.socket_ipc import IPCServer, IPCClient

@pytest.mark.asyncio
async def test_ipc_heartbeat(tmp_path):
    """IPC server should receive heartbeat and store state."""
    import ipc.socket_ipc as ipc_mod
    sock_path = str(tmp_path / "test.sock")
    ipc_mod.SOCKET_PATH = sock_path

    server = IPCServer()
    await server.start()
    try:
        client = IPCClient()
        result = await client.send_heartbeat({"last_trade": "BTCUSDT", "cycle": 42})
        assert result is not None
        assert result.get("ok") is True

        state = await client.query_state()
        assert state.get("cycle") == 42
    finally:
        await server.stop()
```

- [ ] **Step 2: Implement socket_ipc.py**

Create per spec Section 3.17. Use `/tmp/crypto_beast_ipc.sock`.

- [ ] **Step 3: Run tests**

Run: `source .venv/bin/activate && python -m pytest tests/ipc/ -v`

- [ ] **Step 4: Commit**

```bash
git add ipc/ tests/ipc/
git commit -m "feat: Unix domain socket IPC for watchdog↔bot communication (#17)"
```

---

### Task 19: Integration + final commit

- [ ] **Step 1: Add executor.close() to shutdown path**

In `crypto_system.py`, find the shutdown/cleanup section and add:
```python
await executor.close()  # Close persistent aiohttp session (Task 6/fix #4)
```

- [ ] **Step 2: Wire process_pending_sl_updates() into main loop**

In `crypto_system.py`'s `run_trading_cycle()`, after `check_positions()` and closing trades:
```python
await position_manager.process_pending_sl_updates()  # Execute queued SL moves (Task 15/fix #16)
```

- [ ] **Step 3: Verify websockets dependency**

Run: `source .venv/bin/activate && pip show websockets || pip install websockets`
Add `websockets` to `requirements.txt` if not already present.

- [ ] **Step 4: Integrate WebSocket + User Data Stream into main loop**

In `crypto_system.py`, add startup code to initialize `BinanceWSManager` and `UserDataStream`, wire callbacks to data modules.

- [ ] **Step 5: Restore intel adjustment to full strength**

After WebSocket provides real data, change back:
```python
INTEL_AGREE_ADJ = 0.03
INTEL_CONFLICT_ADJ = 0.05
```

- [ ] **Step 6: Run full test suite**

Run: `source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass (should be ~430+ tests now with new ones)

- [ ] **Step 7: Update CLAUDE.md**

Update version to v1.6.0, update `profit_protect_activation_pct` docs (0.02→0.08), add new config fields, add WebSocket/IPC docs.

- [ ] **Step 8: Final commit + tag**

```bash
git add .
git commit -m "feat: v1.6.0 — integrate WebSocket + User Data Stream + IPC

Phase 2 integration:
- WebSocket manager connected to WhaleTracker/LiquidationHunter/OrderBookSniper
- User Data Stream replaces polling for account updates
- Intel adjustment restored to full strength (real data now)
- CLAUDE.md updated for v1.6.0"

git tag -a v1.6.0 -m "v1.6.0: System audit fixes — 18 items"
```
