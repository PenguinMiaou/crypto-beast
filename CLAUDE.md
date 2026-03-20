# Crypto Beast Trading Bot

## Environment
- Python 3.9.6 — use `Optional[X]` not `X | None`, `Dict`/`List` not `dict`/`list`
- Venv at `.venv/`
- Tests: `source .venv/bin/activate && python -m pytest -q` (409 tests)
- Entry point: `crypto_system.py` (NOT main.py — renamed to avoid conflict with other projects)

## Running
- Start: `bash start.sh live` / `bash start.sh` (paper) / `bash start.sh dashboard` / `bash start.sh stop`
- Debug modes (bypass watchdog): `bash start.sh direct-live` / `direct-paper`
- Runs directly from ORICO external drive (I/O errors were from zombie processes, not drive)
- DB at `crypto_beast.db`
- Logs at `logs/bot.log` (bot), `logs/watchdog.log` (watchdog)

## Watchdog System (Guardian Daemon)
- `crypto_guardian.py` monitors + auto-restarts `crypto_system.py`
- start.sh now launches watchdog, which spawns the bot as subprocess
- State file: `watchdog.state` (JSON, thread-safe with threading.Lock + atomic write)
- L1 auto-fix: crash restart, zombie kill, frozen detection (log stale + CPU < 1%)
- L2 Claude fix: `scripts/emergency-fix.sh` → `claude -p` with 10min timeout, 3 calls/day max
- L3 reviews: daily 00:30 UTC, weekly Mon 00:45, monthly 1st 01:00 — via `scripts/{daily,weekly,monthly}-review.sh`
- Review data extracted by `watchdog_review_data.py` → `review_data/` JSON files → `review_prompt.md` template
- All Telegram commands now handled by watchdog (not bot): /help /status /positions /pnl /balance /trades /close /closeall /pause /resume /health /watchdog /stopall /restart /review /directive /directives /deldirective /cost /version
- `/stopall` requires `/confirm` within 60s
- `/directive <text>` sets strategic guidance for Claude reviews
- Concurrency lock: only one Claude session at a time (15min stale timeout)
- launchd: `com.cryptobeast.watchdog.plist` for auto-restart on crash
- Self-check thread: kills watchdog if main thread hung >2min → launchd restarts
- KNOWN_PATTERNS in `watchdog_event_router.py`: disk I/O, network, margin, HALT, rate limit, API latency, trading cycle error, known bugs
- L2 cooldown key: strip timestamp prefix from error message, use first 80 chars as dedup key (1h cooldown per unique error)
- L2 daily budget (3 calls) is watchdog-internal limit, NOT Claude Code account quota
- All restart/escalation methods check `_shutting_down` flag to prevent actions after /stopall
- `/approve`, `/reject`, `/rollback` commands for review recommendation workflow

## Process Management (CRITICAL)
- Process name is `crypto_system.py` — other projects may use `main.py`, don't `pkill main.py`
- Kill command: `ps aux | grep crypto_system | grep -v grep` then `kill -9 <pid>`
- Watchdog also needs killing: `ps aux | grep crypto_guardian.py | grep -v grep`
- start.sh auto-kills old watchdog + crypto_system processes before starting
- Zombie processes holding SQLite DB lock cause "disk I/O error" — always verify 1 process
- `nohup` + `disown` required for background execution (plain `&` dies with shell)
- `caffeinate` subprocess is normal (1 per bot instance)

## Binance API
- Account uses **hedge mode (dual position)** — all orders need `positionSide: LONG/SHORT`
- Entry orders: use `fapiPrivatePostOrder` direct API (ccxt doesn't handle hedge mode)
- SL/TP: use Algo Order API `/fapi/v1/algoOrder` with `algoType=CONDITIONAL` (mandatory since 2025-12-09)
- Old `/fapi/v1/order` rejects STOP_MARKET/TAKE_PROFIT_MARKET with error -4120
- `reduceOnly` NOT supported in hedge mode
- BTC min notional: $100, ETH/SOL/others: $20
- Qty round UP (`math.ceil`) to meet min notional
- Small accounts (<$500): single entry in live (urgency=1.0); paper mode allows DCA testing
- `fetch_positions()` — use `fapiPrivateV2GetAccount` (ccxt wrapper has NoneType issues)
- close_position() returning -2022 = position already closed by exchange SL/TP → treat as success, not error
- `cancel_all_orders()` requires symbol argument on Binance Futures — must iterate per symbol
- Algo Orders have per-account limit (200) — -4045 "Reach max stop order limit" means too many SL/TP orders
- Algo Order cleanup: `close_position()` cancels algo orders for same symbol+positionSide after closing
- Algo Order query: GET `/fapi/v1/openAlgoOrders` (NOT `/fapi/v1/algoOrders/openOrders`); returns list directly
- Algo Order cancel: DELETE `/fapi/v1/algoOrder` with `algoId` param
- `cancel_algo_orders(symbol, position_side)` — filters by positionSide to avoid cancelling other direction in hedge mode
- `ensure_sl_orders()` on startup: checks all positions have exchange SL, places missing ones (default 3% if DB has sl=0)
- `fetch_market_data()` uses `asyncio.gather` for parallel kline fetches (3 symbols × 4 TFs = 12 calls); serial was ~5s → parallel ~1.3s
- Duplicate position guard: skip signal generation for symbol if already holding ANY position (no stacking, no hedging same symbol)
- Periodic SL check: `ensure_sl_orders()` runs every 60 cycles (~5min) to catch LIMIT fills missing SL
- Flip when full: positions full still generates signals for held symbols; opposite-direction signal triggers flip (close+reopen)
- LIMIT orders may return `executedQty=0` (pending) → `_place_exit_orders` skips SL → periodic check fixes this
- In hedge mode, SELL with positionSide=LONG on empty position = -2022 (not -2019)

## Reconciliation
- On startup: `reconcile_with_exchange()` syncs DB with Binance
- Preserves SL/TP/strategy if position already in DB — only updates qty/entry
- NEVER delete crypto_beast.db on restart — reconciliation handles sync
- datetime: always `datetime.now(timezone.utc)` (aware), never `datetime.utcnow()` (naive)
- Equity calculation: use `fapiPrivateV2GetAccount` → `totalMarginBalance` (= wallet + unrealized PnL, matches Binance web UI)
- Do NOT calculate equity from DB (starting_capital + closed_pnl - fees) — it drifts due to PnL reconciliation gaps
- Dashboard, Telegram /balance, and bot internal equity all read from same Binance API → always consistent

## Telegram Bot (via Watchdog)
- ALL commands now handled by `watchdog_commands.py` (not bot's TelegramBot)
- Commands: /help /status /positions /pnl /balance /trades /close /closeall /pause /resume /health /watchdog /stopall /restart /review /directive /directives /deldirective /cost /version
- `/pause` stops new trades but SL/TP + profit protection monitoring continues
- Markdown fallback to plain text ($ chars break Telegram Markdown)
- Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env
- `/close` and `/closeall` delegate to bot via watchdog.state command field

## Position Management
- Static SL/TP: checked every 5 seconds by PositionManager
- Profit protection: activates at 2% profit, closes when 50% of peak profit given back
- Exchange-level SL/TP via Algo Order API (survive bot crash)
- Config: `profit_protect_activation_pct` (0.02), `profit_protect_drawback_pct` (0.50)

## DefenseManager (unified defense — replaced old EmergencyShield + RecoveryMode)
- Single module: `defense/defense_manager.py` — replaces `execution/emergency_shield.py` + `execution/recovery_mode.py` (both deleted)
- Unified state machine: NORMAL → CAUTIOUS → RECOVERY → CRITICAL → HALT → EMERGENCY_CLOSE
- Triggers: daily loss >= 10% → HALT 24h; total drawdown >= 30% → EMERGENCY_CLOSE
- **HALT state persisted to disk** (`shield.state`) — survives restarts (old bug: was in-memory only)
- Relaxed params for small accounts:
  - NORMAL: 10x leverage, 0.3 min confidence, MTF 5
  - CAUTIOUS (5% dd): 5x, 0.5, MTF 6
  - RECOVERY (10% dd): 3x, 0.6, MTF 7
  - CRITICAL (20% dd): 2x, 0.7, MTF 8 (old was 1x/0.9 which killed all trading)
- `ShieldAction.ALREADY_NOTIFIED` = already halted, skip silently in main loop
- Resume notification sent via `pop_just_resumed()` (one-shot flag)
- Notifications: sent once on trigger, once on resume — NOT every cycle
- `shield.state` persistence: never use bare `except: pass` — always log errors (silent failure = invisible bugs)
- HALT cooldown_until serialized with isoformat() — fromisoformat() correctly restores timezone info

## DB Tables (new for watchdog)
- `rejected_signals` — signals filtered by risk/anti_trap (for missed opportunity review)
- `recommendation_history` — past review recommendations + effectiveness tracking
- `strategy_versions` — version history with config snapshots (v1.0 seeded on first run)
- `change_registry` — all code/config changes with source (daily_review/weekly_review/L2_fix)
- `watchdog_interventions` — watchdog event log (level, action, outcome, claude_used)

## Signal Pipeline (2026-03-17 audit improvements)
- Layer 1 intel modules (whale/sentiment/liquidation/orderbook) now feed into signal confidence (+0.03 per agreeing module, -0.05 per conflicting)
- MTF filter activated: blocks signals that CONFLICT with strong higher-timeframe direction; weak/neutral MTF lets signals through
- No double dedup: StrategyEngine deduplicates; main loop no longer re-deduplicates (allows pattern scanner signals)
- Paper mode uses same confidence thresholds as live (was 0.15, now matches live 0.3)
- Slippage monitoring: logs warning if actual vs expected entry > 0.1%
- Inner signal loop (`for signal in signals:`) MUST break after first successful trade — otherwise multiple execute() calls per symbol per cycle → margin insufficient spam
- When removing dedup/filters, always verify loops have proper exit conditions
- watchdog.state access uses fcntl file locking (was unprotected read/write)
- Peak tracking persisted to DB (`peak_profit` column) — survives restarts (was in-memory only, 12 restarts/day = 12 peak losses)
- Position monitoring (SL/TP/profit protection) runs EVERY cycle even when API latency is high — only new trade opening is gated by health check
- Skip signal generation entirely when positions full (`max_concurrent_positions`) — saves API calls
- RiskManager rejects signals where TP distance < 3x round-trip fees (prevents 6-second TP trades that net negative)
- FeeOptimizer recommends LIMIT orders when confidence ≤ 0.8 (maker 0.02% vs taker 0.04%)
- L3 review sends Telegram summary BEFORE updating state counter (state error was silently killing send in daemon thread)
- macOS scripts: no `timeout` command (use background+kill), no `set -e` (kills EXIT_CODE logging), `claude` needs explicit PATH export
- Data modules (WhaleTracker/SentimentRadar/LiquidationHunter/OrderBookSniper) accept config params in constructor — never hardcode thresholds
- SQL: never `SELECT *` with index access — always explicit column names (prevents silent breakage when schema changes)
- SQL: use `datetime('now', '-1 day')` not `date()` when comparing ISO timestamp strings
- Symbol conversion: use `symbol[:-4] + "/USDT"` with `endswith("USDT")` guard, never `.replace("USDT", "/USDT")`
- Binance Futures ccxt ticker format: `ETH/USDT:USDT` (not `ETH/USDT`) — use `endswith(":USDT")` to match
- Reconciliation INSERT must include stop_loss/take_profit columns (default 0)
- After completing work: always update CLAUDE.md, 策略详解.md, and git tag+release

## Versioning
- Semantic versioning: vMAJOR.MINOR.PATCH (e.g., v1.1.0)
- MAJOR: breaking changes or major architecture rework
- MINOR: new features, significant improvements (e.g., DefenseManager, signal pipeline)
- PATCH: bug fixes, small tweaks (e.g., fix -2022 handling, fix timeout)
- Tag + GitHub release for every MINOR/MAJOR bump; PATCH optional
- Current: v1.5.7 — repo at `https://github.com/PenguinMiaou/crypto-beast` (private)

## Architecture
- 7-layer async trading system for Binance USDT-M Futures
- Design spec: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`
- Watchdog spec: `docs/superpowers/specs/2026-03-16-watchdog-daily-review-design.md`
- Audit plan: `docs/superpowers/plans/2026-03-17-system-audit-fixes.md`
- All source under ``

## Code Patterns
- Strategies: `BaseStrategy.generate(klines, symbol, regime) -> list[TradeSignal]`
- Data modules: `process_event(data)` to feed, `get_signal(symbol)` to read
- Defense: `DefenseManager.check(portfolio) -> DefenseResult` (unified state machine)
- LiveExecutor: `_place_order()` wraps `fapiPrivatePostOrder`, `_place_algo_order()` for SL/TP
- PositionManager: accepts `config` object (not individual params)
- FeeOptimizer: accepts `config` object (reads maker_fee/taker_fee/daily_fee_budget from Config)
- Dashboard: Positions/Orders/Trade History read live from Binance API; Strategies tab reads from local DB (only shows CLOSED trades)
- Config: `config.py` dataclass, `.env` for credentials
- Removed config params: capital_allocation, max_param_change_pct, evolution_time_utc, backtest_train/test_days, trailing_activation/distance_pct

## User
- Prefers Chinese communication
- Non-programmer, uses AI to write all code
- ~$99 USDT capital, risk-tolerant, max loss = account balance (no negative on Binance)
