#!/bin/bash
# Weekly review: 3-phase deep analysis + conditional optimization
set +e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

TIMEOUT=900  # 15 minutes
LOG="$DIR/logs/claude_calls.log"
DATE=$(date -u +%Y-%m-%d)
WEEK=$(date -u +%Y-W%V)
REVIEW_DIR="$DIR/logs/reviews"

mkdir -p "$REVIEW_DIR"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | weekly-review | START" >> "$LOG"

source "$DIR/.venv/bin/activate" 2>/dev/null || true

# Phase 1: Analysis (read-only)
PROMPT_FILE="/tmp/claude_weekly1_$(date +%s).md"
cat > "$PROMPT_FILE" << 'PHASE1_END'
You are the weekly reviewer for Crypto Beast trading bot.

## Phase 1: Analysis Only (NO code changes)

Read the trading database and logs. Analyze:
1. Week's performance: total PnL, win rate, Sharpe estimate
2. Per-strategy breakdown: which strategies contributed, which degraded
3. SL/TP effectiveness: too tight? too loose?
4. Capital utilization: idle time, position count trends
5. Recommendation effectiveness: check past recommendations' impact
6. System health: errors, restarts, API latency trends

Write your analysis to /tmp/weekly_review_analysis.txt
End with either:
- "Actionable Items: none" (if no changes needed)
- "Actionable Items:" followed by numbered list of specific changes

Read crypto_beast.db for trade data. Read logs/bot.log for system health.
Read watchdog.state for directives and recent events.
PHASE1_END

export PATH="/Users/brian/.local/bin:$PATH"
claude -p "$(cat "$PROMPT_FILE")" --allowedTools 'Read,Bash,Glob,Grep,Write' > /tmp/claude_weekly1_output.log 2>&1 &
CLAUDE_PID=$!
( sleep "$TIMEOUT" && kill "$CLAUDE_PID" 2>/dev/null ) &
TIMER_PID=$!
wait "$CLAUDE_PID" 2>/dev/null
kill "$TIMER_PID" 2>/dev/null
wait "$TIMER_PID" 2>/dev/null
rm -f "$PROMPT_FILE"

# Phase 2: Action (only if Phase 1 found actionable items)
if [ -s /tmp/weekly_review_analysis.txt ]; then
    if ! grep -q "Actionable Items: none" /tmp/weekly_review_analysis.txt 2>/dev/null; then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | weekly-review | PHASE2_START" >> "$LOG"

        PROMPT_FILE="/tmp/claude_weekly2_$(date +%s).md"
        cat > "$PROMPT_FILE" << 'PHASE2_END'
You are implementing weekly review changes for Crypto Beast.

## Phase 2: Apply Changes

Read /tmp/weekly_review_analysis.txt for the analysis and action items.
For each actionable item:
1. Make the specific code/config change
2. Run `python -m pytest -q` to verify
3. If tests fail, revert with `git checkout .`
4. Commit with message "[weekly-review] <description>"

## Rules
- NEVER modify .env, watchdog.py, or watchdog_state.py
- Only make changes listed in the analysis
- If unsure, skip the change and note it
PHASE2_END

        export PATH="/Users/brian/.local/bin:$PATH"
        claude -p "$(cat "$PROMPT_FILE")" --allowedTools 'Read,Write,Bash,Glob,Grep,Edit' > /tmp/claude_weekly2_output.log 2>&1 &
        CLAUDE_PID=$!
        ( sleep "$TIMEOUT" && kill "$CLAUDE_PID" 2>/dev/null ) &
        TIMER_PID=$!
        wait "$CLAUDE_PID" 2>/dev/null
        kill "$TIMER_PID" 2>/dev/null
        wait "$TIMER_PID" 2>/dev/null
        rm -f "$PROMPT_FILE"
    fi
fi

# Save report
if [ -f /tmp/weekly_review_analysis.txt ]; then
    cp /tmp/weekly_review_analysis.txt "$REVIEW_DIR/weekly-$WEEK.md"
fi

rm -f /tmp/weekly_review_analysis.txt

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | weekly-review | DONE" >> "$LOG"
