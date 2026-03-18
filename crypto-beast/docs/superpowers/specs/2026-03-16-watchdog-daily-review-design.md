# Watchdog + Daily Review System Design

**Goal:** A two-layer monitoring system that keeps Crypto Beast alive and evolving — lightweight watchdog for real-time protection (zero tokens), Claude Code for intelligent repair and daily deep review (tokens only when needed).

**Architecture:** Python multi-threaded watchdog daemon + Claude CLI integration + independent Telegram polling.

**Tech Stack:** Python 3.9 (threading, subprocess, pathlib), Claude CLI (`claude -p`), Telegram Bot API (requests), existing SQLite DB.

---

## 1. Overall Architecture

```
┌───────────────────────────────────────────────────┐
│              watchdog.py (persistent daemon)        │
│                                                    │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐  │
│  │ Main Thread │  │ Log Monitor│  │ Repair Thread│  │
│  │ Heartbeat   │  │ tail -f    │  │ claude -p    │  │
│  │ 30s cycle   │  │ real-time  │  │ on-demand    │  │
│  └─────┬──────┘  └─────┬──────┘  └──────┬──────┘  │
│        │               │                │          │
│        └───────┬───────┘                │          │
│                ▼                        │          │
│       ┌──────────────┐                  │          │
│       │ Event Router │──── L2/L3 ──────▶│          │
│       │ L1 / L2 / L3 │                  │          │
│       └──────┬───────┘                  │          │
│              │                          ▼          │
│              ▼                 ┌──────────────┐    │
│     ┌──────────────┐          │ Claude Code   │    │
│     │ Telegram     │          │ Emergency Fix │    │
│     │ (watchdog's  │          │ Daily Review  │    │
│     │  own polling)│          └──────────────┘    │
│     └──────────────┘                              │
└───────────────────────────────────────────────────┘

           ▼ monitors
┌───────────────────────┐
│  crypto_system.py     │
│  (trading bot)        │
└───────────────────────┘
```

### Launch & Lifecycle

- `watchdog.py` replaces `start.sh` as the primary entry point
- watchdog starts `crypto_system.py` as a subprocess and keeps it alive
- watchdog itself runs via `nohup python watchdog.py &` + `disown`
- `start.sh` updated to launch watchdog instead of bot directly
- `start.sh` modes: `live` (watchdog + live bot), `paper` (watchdog + paper bot), `dashboard` (streamlit only), `stop` (kill watchdog + bot)

### Telegram Ownership

**watchdog runs its own lightweight Telegram polling** (separate from the bot's TelegramBot):
- Uses a **different Telegram bot token** (`WATCHDOG_BOT_TOKEN` in `.env`) to avoid update conflicts
- OR: the existing TelegramBot in `crypto_system.py` is removed and ALL Telegram commands are handled by watchdog
- **Recommended: single bot token, owned by watchdog.** The trading bot stops running its own Telegram polling. Watchdog polls Telegram and handles all commands. For commands that need bot state (e.g., `/positions`, `/balance`), watchdog queries the DB or Binance API directly using the same lightweight `requests` approach.

This solves the "bot crashes → Telegram unreachable" problem: watchdog is always up, so Telegram commands always work.

### Heartbeat File (replaces signal file)

`watchdog.state` — JSON file updated by watchdog every heartbeat cycle:
```json
{
  "watchdog_pid": 12345,
  "bot_pid": 12346,
  "status": "running",
  "paused": false,
  "uptime_seconds": 3600,
  "restarts_today": 1,
  "claude_calls_today": 0,
  "last_heartbeat": "2026-03-16T12:00:00Z",
  "last_log_line_time": "2026-03-16T11:59:55Z",
  "recent_events": [
    {"time": "2026-03-16T10:30:00Z", "level": "L1", "event": "Process crashed — auto-restarted"}
  ],
  "pending_approvals": [],
  "command": null
}
```

- Telegram commands write to `"command"` field (e.g., `"STOP"`, `"RESTART"`)
- Watchdog reads and clears `"command"` each heartbeat cycle
- File locking via `fcntl.flock()` for safe concurrent access
- All state persisted — survives watchdog restart

---

## 2. Event Classification & Handling

### L1: Auto-fix (Zero Tokens)

| Event | Detection | Action |
|-------|-----------|--------|
| Process crashed | PID gone / exit code != 0 | Auto-restart, Telegram notify |
| DB lock (zombie) | grep `crypto_system` finds >1 PID | Kill extras → restart, Telegram notify |
| Network timeout | Log pattern: `ConnectionError\|Timeout\|ECONNRESET` count > 3 in 5 min | Wait 30s, retry 3x, then escalate to L2 |
| Process frozen | No new log line for 5 min AND heartbeat file stale | Force kill → restart, Telegram notify |
| Disk I/O error | Log pattern: `disk I/O error` | Kill zombies → restart, Telegram notify |
| Margin insufficient | Log pattern: `Margin is insufficient` | Telegram notify (info only, bot handles internally) |
| Emergency HALT | Log pattern: `HALT.*daily loss` | Telegram notify (info only, bot handles internally) |
| Rate limit | Log pattern: `Rate limit\|429` | Telegram notify (info only, bot backs off internally) |

**Frozen detection detail:** watchdog checks BOTH "last log line timestamp > 5 min ago" AND "the bot process is consuming < 1% CPU" (via `ps`). This avoids false positives during quiet market periods — if the bot is actively polling (CPU > 0%), it's not frozen even without log output.

### L2: Claude Emergency Fix (Tokens on Demand)

| Event | Detection | Action |
|-------|-----------|--------|
| Restart loop | restart_count >= 3 in 10 min | `claude -p` analyze + fix, then restart |
| Unknown ERROR | ERROR/CRITICAL log line not in KNOWN_PATTERNS | `claude -p` analyze + fix |
| Position mismatch | DB OPEN count != Binance position count (checked hourly via simple API call) | `claude -p` reconcile + fix root cause |
| API change / new error code | Binance error code not in KNOWN_BINANCE_ERRORS | `claude -p` read error + update code |
| Env/dependency failure | ImportError, ModuleNotFoundError, SSL in logs | `claude -p` diagnose + fix |
| Consecutive losses | >5 consecutive CLOSED trades with pnl < 0 | `claude -p` strategy analysis |
| Abnormal trading pattern | >10 trades/hour OR same symbol opened/closed >3x in 1h | `claude -p` pattern analysis |

**L2 Safety Net:**
1. Before restarting with a fix, Claude MUST run `python -m pytest -q` — if tests fail, revert changes (`git checkout .`) and alert user via Telegram
2. All L2 fixes are committed with message `[watchdog-L2] <description>` for easy tracking/reverting
3. If L2 fix fails (bot still crashes after fix), escalate to **L2-TERMINAL**: stop the bot, send urgent Telegram alert, wait for human intervention
4. L2-TERMINAL message: "Bot stopped — Claude attempted fix but failed. Manual intervention needed. Last error: <error>"

### L3: Scheduled Review (Predictable Tokens)

| Event | Schedule | Action |
|-------|----------|--------|
| Daily deep review | UTC 00:30 daily | `claude -p` full review (see Section 4) |

### Token Protection

- **Cooldown**: Same error type → max 1 Claude call per hour
- **Daily budget**: Max 3 emergency (L2) calls + 1 daily review (L3) per day
- **Budget counter** persisted in `watchdog.state` file, resets at UTC 00:00
- **All events logged** to `logs/watchdog.log` regardless of level
- **Claude call log**: each invocation logged with timestamp, prompt summary, duration, and exit code to `logs/claude_calls.log`

### L2 Failure Terminal State

```
L1 auto-fix fails (3 restarts)
    → L2 Claude fix attempt
        → Tests pass? → Restart bot → Monitor
        → Tests fail? → git checkout . → L2-TERMINAL
            → Stop bot
            → Urgent Telegram: "Manual intervention needed"
            → Watchdog stays running (Telegram still responsive)
            → Wait for user /restart command
```

### Concurrent Event Handling

- Repair thread processes one event at a time from a `queue.Queue`
- New L2 events while Claude is running are queued (max 5, oldest dropped)
- L2-TERMINAL state pauses the queue until user intervenes

---

## 3. Telegram Integration

### Command Ownership

**All Telegram commands move to watchdog.** The TelegramBot class in `crypto_system.py` is removed. Watchdog handles everything:

| Command | Description | Data Source |
|---------|-------------|-------------|
| `/help` | List all commands | Static |
| `/status` | System overview (equity, positions, uptime) | DB + watchdog.state |
| `/positions` | Open positions with SL/TP | DB |
| `/pnl` | Today's PnL | DB |
| `/balance` | Wallet balance | Binance API (lightweight requests call) |
| `/trades` | Recent trade history | DB |
| `/close SYMBOL` | Close a position | Binance API |
| `/closeall` | Emergency close all | Binance API |
| `/pause` | Pause new trades (write flag to DB/file) | watchdog.state |
| `/resume` | Resume trading | watchdog.state |
| `/health` | System + watchdog health | DB + watchdog.state + logs |
| `/watchdog` | Watchdog status: uptime, events, restarts, Claude calls | watchdog.state |
| `/stopall` | Stop bot + watchdog (requires `/confirm` within 60s) | watchdog.state command |
| `/restart` | Restart bot (useful after L2-TERMINAL) | watchdog.state command |
| `/approve` | Approve ALL pending parameter changes | watchdog.state pending_approvals |
| `/approve N` | Approve specific recommendation by number | watchdog.state pending_approvals |
| `/reject` | Reject all pending changes | watchdog.state pending_approvals |
| `/review` | Trigger an ad-hoc daily review now | Spawns claude -p |
| `/review YYYY-MM-DD` | View a past day's review summary | Read from logs/reviews/ |
| `/directive <text>` | Set strategic guidance for Claude reviews | watchdog.state directives |
| `/directives` | List active directives | watchdog.state directives |
| `/deldirective N` | Remove a directive by number | watchdog.state directives |
| `/cost` | Token usage today/this week/this month | claude_calls.log |
| `/version` | Current strategy version and changelog | strategy_versions table |
| `/rollback` | Rollback to previous strategy version | Spawns claude -p |

### Pause/Resume Mechanism

Pause state stored in `watchdog.state` → `"paused": true/false`:
- `/pause` → watchdog sets `"paused": true` in `watchdog.state`
- `crypto_system.py` reads `watchdog.state` on each cycle, checks `"paused"` field
- `/resume` → watchdog sets `"paused": false`
- Same `fcntl.flock()` locking as all other state file access

### Close Position Implementation

`/close` and `/closeall` require hedge-mode order placement. Rather than duplicating `LiveExecutor` logic, watchdog signals the bot to close:
- `/close BTCUSDT` → watchdog writes `{"command": "CLOSE", "args": "BTCUSDT"}` to `watchdog.state`
- `crypto_system.py` reads command on next cycle → calls `executor.close_position()` with existing hedge-mode logic
- `/closeall` → same mechanism with `{"command": "CLOSEALL"}`
- If bot is in L2-TERMINAL (not running), `/close` falls back to a simple direct API call via `requests` with hedge-mode params hardcoded (MARKET order, correct positionSide), reading position info from DB

This avoids duplicating the complex `LiveExecutor` while still providing emergency close when the bot is down.

### Notification Format

All watchdog events sent to Telegram with level prefix:
```
[L1] Process crashed — auto-restarted (3rd time today)
[L2] Unknown error detected — calling Claude Code to analyze...
[L2] Fix applied and tests passed — bot restarted
[L2-TERMINAL] Fix failed — bot stopped, manual intervention needed
[L3] Daily review complete — 3 action items pending /approve
```

---

## 4. Daily Review Design

### Data Extraction Pipeline

Claude cannot read SQLite binary files directly. Watchdog prepares data before invoking Claude:

1. **Extract script** (`watchdog_review_data.py`): queries DB and writes results to temporary JSON/text files:
   - `review_data/trades_today.json` — all trades from today
   - `review_data/trades_7d.json` — trades from last 7 days (for trend analysis)
   - `review_data/equity_snapshots.json` — equity curve
   - `review_data/evolution_log.json` — parameter changes
   - `review_data/strategy_performance.json` — per-strategy metrics
   - `review_data/rejected_signals.json` — signals filtered by risk/anti_trap (requires logging these — see Section 9)
   - `review_data/system_health.json` — health table entries

2. **Log extraction**: `tail -n 2000 logs/bot.log > review_data/bot_log_24h.txt`

3. **Git diff**: `git log --since='24 hours ago' --oneline > review_data/git_changes.txt` + `git diff HEAD~5 > review_data/code_diff.txt`

4. **Market data**: BTC daily OHLCV from DB klines table → `review_data/btc_daily.json`

5. **Config snapshot**: `cp config.py review_data/config_snapshot.py`

### Claude Invocation

```bash
cd /Volumes/ORICO\ Media/Crypto\ Trading\ System/crypto-beast && \
claude -p "$(cat review_prompt.md)" \
  --allowedTools Read,Write,Bash,Edit,Grep,Glob
```

### Review Prompt Template (`review_prompt.md`)

```markdown
You are the daily reviewer for Crypto Beast trading bot. Today is {date}.

## Your Data (pre-extracted in review_data/)
- review_data/trades_today.json — all trades opened/closed today
- review_data/trades_7d.json — last 7 days for trend analysis
- review_data/equity_snapshots.json — equity curve
- review_data/evolution_log.json — Evolver parameter changes
- review_data/strategy_performance.json — per-strategy metrics
- review_data/rejected_signals.json — signals filtered by risk/anti_trap
- review_data/system_health.json — health table entries
- review_data/bot_log_24h.txt — last 2000 lines of bot log
- review_data/git_changes.txt — git log last 24h
- review_data/code_diff.txt — git diff of recent changes
- review_data/btc_daily.json — BTC OHLCV for benchmark
- review_data/config_snapshot.py — current config

## Additional Context (auto-injected by watchdog)
- review_data/change_registry_7d.json — all code/config changes in last 7 days with source
- review_data/recommendation_history.json — past recommendations and their outcomes
- review_data/directives.json — active user strategic directives
- review_data/strategy_version.json — current version + recent version history
- review_data/watchdog_interventions.json — watchdog events today

## Instructions
1. Read ALL files in review_data/
2. Generate a review covering these 19 modules: [Trade Recap, Strategy Comparison,
   SL/TP Analysis, Missed Opportunities, Abnormal Patterns, Capital Utilization,
   Market Benchmark, Execution Quality, Session/Time Analysis, Hold Time Optimization,
   Drawdown Analysis, System Health, Evolution Log, Code Self-Audit,
   Recommendation Effectiveness, User Directives Check, Risk Forecast,
   Action Items, Tomorrow Outlook]
3. For Module 14 (Code Self-Audit): run `python -m pytest -q` and report results
4. For Module 15 (Recommendation Effectiveness): check each past approved recommendation,
   compare metrics before/after, update recommendation_history table
5. For Module 16 (User Directives): evaluate compliance with each active directive
6. For Module 18 (Action Items): list specific parameter changes as numbered items.
   Tag each with current strategy version. Write to watchdog.state pending_approvals.
7. Save full report to logs/reviews/{date}.md
8. Write a concise Telegram summary (max 500 chars) to review_data/telegram_summary.txt

## Conflict Resolution Rules
- User directives override all automated recommendations
- Do NOT undo changes from weekly reviews unless >3 days of clear regression
- L2 fixes are surgical — only fix the specific error, don't touch unrelated params
- When unsure if a change conflicts with a higher-level decision, flag to user

## Rules
- Be specific with numbers, not vague ("won 3/5 trades" not "mostly won")
- Compare against 7d/30d trends, not just today
- Action items must include reasoning AND exact config change
- Chinese language for the report and Telegram summary
```

After Claude finishes, watchdog reads `review_data/telegram_summary.txt` and sends it to Telegram. If `pending_approvals` in `watchdog.state` is non-empty, appends "回复 /approve 执行建议" to the message.

### Review Report Structure (19 Modules)

#### Module 1: Trade Recap
- All trades opened/closed today
- Per-trade PnL, strategy, hold time
- Entry/exit price vs signal price (slippage)

#### Module 2: Strategy Comparison
- Per-strategy: win rate, avg PnL, Sharpe
- 7-day and 30-day trend comparison (improving or degrading?)
- Which strategy contributed most/least
- **Strategy correlation**: are multiple strategies generating correlated signals? If all 5 go LONG BTC at once, that's concentration risk, not diversification

#### Module 3: SL/TP Analysis
- Trades where SL was hit then price reversed within 1h (SL too tight?)
- Trades where TP was hit but price continued >2% (TP too early?)
- Profit protection trigger timing — was the 50% drawback threshold right?
- Data source: trades table + klines for post-exit price movement

#### Module 4: Missed Opportunities
- Signals rejected by risk_manager (why? position count? correlation?)
- Signals filtered by anti_trap (was it actually a trap or a real move?)
- Post-hoc validation using klines: if we had taken them, what would PnL be?
- Data source: `rejected_signals.json` (requires new logging — see Section 9)

#### Module 5: Abnormal Patterns
- Frequent open/close on same symbol (>3x/day)
- Same-direction repeated losses on same symbol
- Fee ratio: total fees / total PnL (healthy < 15%)

#### Module 6: Capital Utilization
- Time-weighted average position count (from equity_snapshots)
- Idle time percentage (periods with 0 positions)
- Could we have been more aggressive without exceeding risk limits?

#### Module 7: Market Benchmark
- BTC daily return vs our portfolio return
- Alpha = our return - BTC return
- If negative alpha, identify where (bad entries? early exits? wrong direction?)

#### Module 8: Execution Quality
- Signal-to-fill latency: time between signal generation and order execution
- Slippage analysis: expected entry vs actual fill price per trade
- Order rejection rate and reasons
- Were we getting worse fills at certain times of day?

#### Module 9: Session/Time Analysis
- PnL breakdown by market session: Asia (00-08 UTC) / Europe (08-16 UTC) / US (16-00 UTC)
- Which hours are most profitable? Which should we avoid?
- Is there a pattern (e.g., always lose in Asian session)?
- Recommendation: adjust session_trader weights or skip certain sessions

#### Module 10: Hold Time Optimization
- Average hold duration per strategy vs optimal duration (measured by when peak PnL occurred)
- Trades where holding longer would have been more profitable
- Trades where we held too long and gave back profits
- Recommendation: adjust TP timing or profit protection activation threshold

#### Module 11: Drawdown Analysis
- Max intraday drawdown (peak-to-trough within the day)
- Consecutive loss streaks: current streak length and historical max
- Recovery time from drawdowns (how many hours/trades to recover)
- Drawdown vs historical average — is today worse than normal?

#### Module 12: System Health
- Error count by type from logs (grep + count)
- Average API latency (from system_health table)
- Process restarts today (from watchdog.state)
- DB integrity: `PRAGMA integrity_check`

#### Module 13: Evolution Log
- What did Evolver change today? (from evolution_log table)
- Sharpe ratio before vs after
- Parameter diff (what moved, by how much)

#### Module 14: Code Self-Audit
- Review recent code changes (`git diff` from last 24h)
- Check for: temporary hacks, TODO comments, unused variables, debugging prints
- Verify recent L2 fixes didn't introduce side effects
- Run `python -m pytest -q`, report any failures
- Check for files that have grown too large or need cleanup

#### Module 15: Recommendation Effectiveness (复盘的复盘)
- **Track every past recommendation**: what was suggested, was it approved, what was the before/after performance?
- Compare strategy metrics N days before vs N days after each approved change
- Flag recommendations that made things worse → suggest rollback
- Maintain a running scorecard: "of 20 recommendations to date, 14 improved performance, 4 neutral, 2 degraded"
- This module's data comes from `recommendation_history` table (see Section 9)

#### Module 16: User Directives Check
- Read active user directives from `watchdog.state` → `directives` array
- Evaluate whether today's trading aligned with user's strategic guidance
- Example: user said "保守一点" → check if leverage/position sizes were reduced
- Flag if system contradicted a directive and explain why

#### Module 17: Risk Forecast
- Current funding rates per symbol (from DB) — spikes suggest volatility
- Regime assessment accuracy: compare yesterday's predicted regime vs actual price action
- Open interest changes (if available from data modules)

#### Module 18: Action Items (Closed-Loop)
- Specific parameter adjustment recommendations with reasoning
- Example: "Increase BTC SL from 3% to 3.5% — 3 of 5 BTC trades today hit SL then reversed"
- Each item tagged with current **strategy version** (see Section 11) for traceability
- Each item numbered and written to `watchdog.state` → `pending_approvals` array
- Telegram sends numbered list, user replies `/approve 1` or `/approve` (all)
- On approval: Claude is re-invoked with `claude -p "Apply these changes: ..."` → modifies config → watchdog restarts bot
- **All recommendations logged** to `recommendation_history` table for Module 15 tracking

#### Module 19: Tomorrow Outlook
- Current open positions assessment (risk exposure)
- Regime prediction based on current indicators
- Recommendation: aggressive / neutral / conservative
- Specific suggestions (reduce leverage? pause certain strategies? tighten SL?)

### Approval Pipeline

```
Daily Review generates recommendations
    → Saved to watchdog.state.pending_approvals as numbered list:
      [{"id": 1, "desc": "Increase BTC SL to 3.5%", "change": "config.py:sl_pct=0.035"}]
    → Telegram message: "3 recommendations pending. /approve or /approve 1,2"
    → User sends /approve 1,3
    → Watchdog reads pending_approvals[0] and [2]
    → Spawns claude -p "Apply these specific changes to config.py: ..."
    → Claude modifies config.py, runs tests
    → If tests pass: commit + restart bot
    → If tests fail: revert, notify user
    → Clear approved items from pending_approvals
```

---

## 5. File Structure

```
crypto-beast/
├── watchdog.py               # NEW: daemon process (main entry)
├── watchdog_review_data.py   # NEW: data extraction for daily review
├── review_prompt.md          # NEW: structured prompt template for daily review
├── watchdog.state            # NEW: JSON state file (runtime, gitignored)
├── logs/
│   ├── watchdog.log          # NEW: watchdog event log
│   ├── claude_calls.log      # NEW: Claude invocation log
│   └── reviews/
│       ├── 2026-03-16.md     # NEW: daily review reports
│       ├── weekly-2026-W12.md # NEW: weekly reports
│       ├── monthly-2026-03.md # NEW: monthly reports
│       └── ...
├── review_data/              # NEW: temporary data for Claude review (gitignored)
│   ├── trades_today.json
│   ├── change_registry_7d.json
│   ├── directives.json
│   ├── ...
├── com.cryptobeast.watchdog.plist  # NEW: launchd config (installed to ~/Library/LaunchAgents/)
├── monitoring/
│   └── telegram_bot.py       # REMOVE: Telegram moves to watchdog
├── start.sh                  # MODIFY: launch watchdog instead of bot
├── crypto_system.py          # MODIFY: remove TelegramBot, add watchdog.state check
└── config.py                 # MODIFY: add watchdog config section
```

---

## 6. Configuration

New fields in `config.py`:
```python
# Watchdog
watchdog_heartbeat_interval: int = 30        # seconds between heartbeat checks
watchdog_frozen_threshold: int = 300         # 5 min no log + low CPU = frozen
watchdog_max_restarts: int = 3               # before escalating to L2 Claude fix
watchdog_restart_window: int = 600           # 10 min window for restart count
watchdog_claude_cooldown: int = 3600         # 1 hour between same-type Claude calls
watchdog_daily_claude_budget: int = 3        # max L2 emergency Claude calls per day
watchdog_review_hour: int = 0               # UTC hour for daily review
watchdog_review_minute: int = 30            # UTC minute for daily review
watchdog_event_queue_max: int = 5            # max queued L2 events
```

---

## 7. Known Error Patterns (L1 Auto-fix)

Pre-configured patterns that watchdog handles without Claude:
```python
KNOWN_PATTERNS = {
    r"disk I/O error": ("zombie_db_lock", "kill_zombies_restart"),
    r"ConnectionError|Timeout|ECONNRESET": ("network_transient", "wait_and_retry"),
    r"Margin is insufficient": ("margin_warning", "notify_only"),
    r"HALT.*daily loss": ("emergency_halt", "notify_only"),
    r"Rate limit|429": ("rate_limit", "notify_only"),
    r"cancelAllOrders.*requires a symbol": ("known_bug", "ignore"),
}

KNOWN_BINANCE_ERRORS = {-4120, -4061, -4164, -2019, -1015, -1021}
```

Unknown ERROR/CRITICAL lines not matching these patterns → escalate to L2.

---

## 8. Watchdog Self-Monitoring

### Problem: Who watches the watchdog?

**Two-layer solution:**

#### Layer 1: launchd (handles crashes)
- A `com.cryptobeast.watchdog.plist` installed in `~/Library/LaunchAgents/`
- launchd ensures `watchdog.py` is always running — restarts it if it **exits/crashes**
- `KeepAlive: true` + `RunAtLoad: true`
- This is the ONLY component that uses launchd; everything else is managed by watchdog

#### Layer 2: Internal watchdog thread (handles hangs)
- launchd can only detect process **exit**, NOT a hung process that's still alive
- Watchdog runs a dedicated **self-check thread** that:
  1. Monitors the main thread's `last_heartbeat` timestamp
  2. If main thread hasn't updated heartbeat for 2 minutes → sends Telegram "Watchdog hung, restarting" → calls `os._exit(1)`
  3. launchd detects the exit and restarts watchdog
- This self-check thread is intentionally simple (just a timestamp comparison loop) to minimize its own hang risk

### Watchdog startup recovery:

- On startup, watchdog checks if `watchdog.state` has a stale `last_heartbeat` (> 2 min old)
- If stale → sends Telegram "Watchdog recovered from crash/hang"
- Resumes monitoring from current state

---

## 9. Required Changes to Trading Bot

### New: Rejected Signal Logging

To support Module 4 (Missed Opportunities), add logging when signals are filtered:
```python
# In crypto_system.py run_trading_cycle(), when risk_manager or anti_trap rejects a signal:
self.db.execute(
    "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
    (signal.symbol, signal.direction.value, signal.strategy, reject_reason, signal.entry_price, now)
)
```

New DB table:
```sql
CREATE TABLE IF NOT EXISTS rejected_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT, side TEXT, strategy TEXT,
    reason TEXT, signal_price REAL, timestamp TEXT
);
```

### Modify: Pause State Check

In `crypto_system.py`, before opening new trades, read `watchdog.state` and check `"paused"` field:
```python
import json
state_path = os.path.join(runtime_dir, "watchdog.state")
if os.path.exists(state_path):
    with open(state_path) as f:
        state = json.load(f)
    if state.get("paused"):
        logger.info("Trading paused via watchdog")
        return
    # Also check for commands (CLOSE, CLOSEALL, etc.)
    cmd = state.get("command")
    if cmd:
        await self._handle_watchdog_command(cmd)
```

### New: Recommendation History Logging

To support Module 15 (Recommendation Effectiveness), track every recommendation:
```sql
CREATE TABLE IF NOT EXISTS recommendation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,                    -- review date
    module TEXT,                  -- which review module generated it
    description TEXT,             -- what was recommended
    approved INTEGER DEFAULT 0,  -- 1 if user /approve'd
    applied_at TEXT,              -- when it was applied
    strategy_version TEXT,        -- version at time of recommendation
    metric_before REAL,          -- key metric before change (e.g., win rate)
    metric_after REAL,           -- key metric N days after (filled by next review)
    effective INTEGER DEFAULT 0  -- 1=improved, 0=neutral, -1=degraded
);
```

### Remove: TelegramBot from crypto_system.py

- Remove `telegram_bot.start_polling()` task from main loop
- Remove TelegramBot import and initialization
- All Telegram handled by watchdog

---

## 10. Safety & Constraints

- Watchdog never modifies trading logic directly — only restarts processes
- Only Claude Code (via `claude -p`) modifies code, and only for L2 emergencies
- L2 fixes MUST pass `pytest -q` before bot restarts — fail → `git checkout .` + alert
- All L2 fixes committed as `[watchdog-L2] <description>` for easy revert
- Parameter changes from daily review require user `/approve` via Telegram
- **Config changes always take effect via bot restart** — no hot-reload. After `/approve`, watchdog modifies `config.py`, commits, then restarts the bot process. The bot loads config fresh on startup.
- Token budget enforced: cooldown per error type + daily cap
- All Claude invocations logged to `logs/claude_calls.log`
- **Watchdog Binance API access**: watchdog uses existing API keys from `.env` with **full access** (not read-only). This is needed for emergency `/close` when bot is down (L2-TERMINAL fallback). During normal operation, `/close` commands are delegated to the bot via `watchdog.state` command field.
- **Claude -p sandbox**: L2 emergency fixes restricted to files under `crypto-beast/` only. Claude prompt includes explicit instruction: "NEVER modify .env, watchdog.py, or any file outside the crypto-beast directory."
- L2-TERMINAL: if Claude fix fails, bot stops and waits for human — never loops indefinitely

---

## 11. Strategy Versioning

### Problem
Git commits track code changes, but there's no structured way to say "v1.1 added RSI filter, v1.2 adjusted SL". Reviews need clear version references for traceability and rollback.

### Solution: `strategy_versions` DB table + git tags

```sql
CREATE TABLE IF NOT EXISTS strategy_versions (
    version TEXT PRIMARY KEY,     -- e.g., "v1.0", "v1.1"
    date TEXT,                    -- when this version was created
    description TEXT,             -- human-readable changelog
    source TEXT,                  -- "manual", "daily_review", "weekly_review", "L2_fix"
    git_commit TEXT,              -- git commit hash for this version
    config_snapshot TEXT,         -- JSON dump of config at this point
    metrics_snapshot TEXT         -- JSON: {win_rate, sharpe, avg_pnl, ...} at version time
);
```

**Version lifecycle:**
- Every `/approve` that changes strategy parameters → bumps version (e.g., v1.1 → v1.2)
- Every L2 fix that modifies strategy code → bumps version
- Git tag created: `git tag strategy-v1.2`
- Config snapshot saved for easy rollback
- `/version` Telegram command shows current version + last 5 changelog entries
- `/rollback` → Claude reads previous version's `config_snapshot`, applies it, bumps to v1.X+1 with description "Rollback from vX.Y"

**Integration with reviews:**
- Module 15 (Recommendation Effectiveness) tracks performance per version
- Module 18 (Action Items) tags each recommendation with current version
- Weekly review compares version-over-version performance

---

## 12. Review Hierarchy & Conflict Resolution

### Problem
Multiple review layers (daily, weekly, L2 emergency) can make conflicting changes. A weekly review adjusts a strategy, then a daily review sees unfamiliar patterns from the change and "fixes" it back.

### Solution: Change Registry + Review Context

**Change Registry** — every modification is logged with its source:
```sql
CREATE TABLE IF NOT EXISTS change_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    source TEXT,           -- "daily_review", "weekly_review", "L2_fix", "user_approve"
    file_changed TEXT,     -- e.g., "config.py", "strategy/trend_follower.py"
    description TEXT,      -- what was changed and why
    strategy_version TEXT, -- version after this change
    git_commit TEXT        -- commit hash
);
```

**Review Context Injection** — before any review or L2 fix, Claude receives:
1. Last 7 days of `change_registry` entries
2. Active user directives
3. Current strategy version + recent version history

This ensures:
- Daily review knows "3 days ago, weekly review changed X because Y" → won't undo it
- L2 fix knows "this ERROR pattern appeared after weekly review's change" → can distinguish intentional changes from bugs
- Weekly review knows what daily reviews have been tweaking → can assess cumulative drift

**Conflict resolution rules (included in Claude prompts):**
1. **User directives override everything** — if user said "保守一点", don't increase leverage even if metrics suggest it
2. **Weekly review > Daily review** — daily review should not undo weekly review changes unless there's clear evidence of regression (>3 days of worse performance)
3. **L2 fixes are surgical** — only fix the specific error, don't touch unrelated strategy parameters
4. **When in doubt, flag to user** — if Claude is unsure whether a change conflicts with a higher-level decision, add it to Telegram as a question, not an auto-action

---

## 13. User Directives System

### Purpose
Give users a way to inject strategic guidance that Claude respects during reviews.

### Telegram Commands
- `/directive 这个月保守一点，减少杠杆` → saves to `watchdog.state` → `directives` array
- `/directive 多关注SOL，减少BTC仓位` → saved with timestamp
- `/directives` → lists all active directives with numbers
- `/deldirective 2` → removes directive #2

### Directive Structure in `watchdog.state`:
```json
{
  "directives": [
    {"id": 1, "text": "这个月保守一点，减少杠杆", "created": "2026-03-16T12:00:00Z"},
    {"id": 2, "text": "多关注SOL，减少BTC仓位", "created": "2026-03-16T14:00:00Z"}
  ]
}
```

### Integration
- Directives are included in the review prompt as "User Strategic Guidance"
- Module 16 evaluates compliance: did the system follow the directive?
- Directives have no auto-expiry — user must manually remove them via `/deldirective`
- Directives are advisory to Claude, not hard-coded rules. Claude interprets them in context.

---

## 14. Weekly/Monthly Reports

### Weekly Report (every Monday UTC 00:45, after daily review)
- Aggregated 7-day metrics: total PnL, win rate, Sharpe, max drawdown
- Strategy version changes this week and their impact
- Recommendation effectiveness scorecard (Module 15 data)
- Trend analysis: are we improving week-over-week?
- Saved to `logs/reviews/weekly-YYYY-WXX.md`

### Monthly Report (1st of month UTC 01:00)
- Full month performance summary
- Strategy evolution timeline (version history with metrics)
- Longest winning/losing streaks
- Capital growth curve
- Comparison to BTC buy-and-hold
- Recommendations for next month's strategy direction
- Saved to `logs/reviews/monthly-YYYY-MM.md`

Both sent as Telegram summaries with full reports saved locally.

---

## 15. Additional Safeguards

### Graceful Shutdown
- `/stopall` does NOT kill the bot immediately
- Writes `{"command": "SHUTDOWN"}` to `watchdog.state`
- Bot reads command on next cycle, finishes current cycle, then exits cleanly
- Watchdog waits up to 30 seconds for clean exit, then force-kills if needed
- Telegram: "Bot shutting down gracefully... done."

### Startup Pre-flight Checks
Watchdog verifies before starting the bot:
1. `.env` exists and has required keys (BINANCE_API_KEY, BINANCE_API_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
2. `.venv/` exists and python is accessible
3. Disk space > 100MB on external drive
4. DB integrity: `PRAGMA integrity_check` passes
5. No zombie `crypto_system` processes running
6. Binance API reachable (simple ping)
7. If any check fails → Telegram notify, do NOT start bot

### Claude CLI Unavailability
If `claude -p` fails (network error, API outage, billing):
- L2 events: fall back to L2-TERMINAL (stop bot, alert user)
- L3 daily review: skip today, log warning, retry tomorrow
- Telegram: "Claude CLI unavailable — L2/L3 services degraded, watchdog L1 protection still active"

### Watchdog Effectiveness Tracking
Log every watchdog intervention in `watchdog_interventions` table:
```sql
CREATE TABLE IF NOT EXISTS watchdog_interventions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    level TEXT,          -- L1, L2, L3
    event TEXT,          -- what happened
    action TEXT,         -- what watchdog did
    outcome TEXT,        -- "resolved", "escalated", "failed"
    claude_used INTEGER, -- 1 if Claude was invoked
    duration_seconds INTEGER  -- how long the fix took
);
```
Monthly report Module includes: "Watchdog resolved 45 L1 events, 3 L2 events (2 successful, 1 escalated). Average resolution time: 35 seconds."

### Token Cost Tracking
`/cost` command reads `logs/claude_calls.log` and reports:
```
Today: 2 calls, ~15k tokens
This week: 9 calls, ~85k tokens
This month: 32 calls, ~310k tokens
Budget remaining: 1 emergency call today
```

### Extended Downtime Recovery
If watchdog detects that `last_heartbeat` in `watchdog.state` is >1 hour stale on startup:
1. Send Telegram: "Extended downtime detected ({hours}h). Running recovery checks..."
2. Check Binance for any positions that may have been liquidated
3. Reconcile DB with exchange state
4. Check if any scheduled events were missed (evolution, review)
5. Run a mini-review of what happened during downtime
6. Resume normal operation

### Notification Language
All Telegram notifications and review reports in Chinese (中文), consistent with user preference.
