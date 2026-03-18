#!/bin/bash
# Monthly review: strategic assessment + long-term optimization
set +e

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

TIMEOUT=600
LOG="$DIR/logs/claude_calls.log"
MONTH=$(date -u +%Y-%m)
REVIEW_DIR="$DIR/logs/reviews"

mkdir -p "$REVIEW_DIR"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | monthly-review | START" >> "$LOG"

source "$DIR/.venv/bin/activate" 2>/dev/null || true

PROMPT_FILE="/tmp/claude_monthly_$(date +%s).md"
cat > "$PROMPT_FILE" << 'PROMPT_END'
You are the monthly strategic reviewer for Crypto Beast trading bot.

## Monthly Review

Perform a comprehensive monthly review:
1. Full month performance: total PnL, equity curve, max drawdown
2. Strategy evolution: version history, what changed, impact
3. Risk analysis: largest losses, near-liquidation events
4. Recommendation scorecard: how many past recommendations improved performance
5. Market regime analysis: was our regime detection accurate?
6. Capital efficiency: average utilization, idle time
7. Code health: accumulated technical debt, test coverage trends
8. Strategic recommendations for next month

Read crypto_beast.db for all trade data.
Read logs/reviews/ for past daily and weekly reports.
Read config.py for current parameters.
Read watchdog.state for user directives.

Save full report to logs/reviews/monthly-MONTH.md (replace MONTH with actual month).
Write a Telegram summary (max 500 chars, Chinese) to review_data/telegram_summary.txt.
PROMPT_END

# Replace MONTH placeholder
sed -i '' "s/MONTH/$MONTH/g" "$PROMPT_FILE" 2>/dev/null || sed -i "s/MONTH/$MONTH/g" "$PROMPT_FILE"

export PATH="/Users/brian/.local/bin:$PATH"
claude -p "$(cat "$PROMPT_FILE")" --allowedTools 'Read,Write,Bash,Glob,Grep,Edit' > /tmp/claude_monthly_output.log 2>&1 &
CLAUDE_PID=$!
( sleep "$TIMEOUT" && kill "$CLAUDE_PID" 2>/dev/null ) &
TIMER_PID=$!
wait "$CLAUDE_PID" 2>/dev/null
kill "$TIMER_PID" 2>/dev/null
wait "$TIMER_PID" 2>/dev/null
rm -f "$PROMPT_FILE"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | monthly-review | DONE" >> "$LOG"
