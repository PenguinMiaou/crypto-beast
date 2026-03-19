#!/bin/bash
# Daily review: Claude Code performs comprehensive trading review
set +e  # Don't exit on error — we need to log EXIT_CODE

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

TIMEOUT=600  # 10 minutes
LOG="$DIR/logs/claude_calls.log"
DATE=$(date -u +%Y-%m-%d)
REVIEW_DIR="$DIR/logs/reviews"
REVIEW_DATA="$DIR/review_data"

mkdir -p "$REVIEW_DIR" "$REVIEW_DATA"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | daily-review | START" >> "$LOG"

# Step 1: Extract data from DB
source "$DIR/.venv/bin/activate" 2>/dev/null || true
python "$DIR/watchdog_review_data.py" --date "$DATE" --output "$REVIEW_DATA" 2>/dev/null || echo "Data extraction had errors"

# Step 2: Copy additional context
tail -2000 "$DIR/logs/bot.log" > "$REVIEW_DATA/bot_log_24h.txt" 2>/dev/null || true
cp "$DIR/config.py" "$REVIEW_DATA/config_snapshot.py" 2>/dev/null || true
git -C "$DIR" log --since='24 hours ago' --oneline > "$REVIEW_DATA/git_changes.txt" 2>/dev/null || true
git -C "$DIR" diff HEAD~5 > "$REVIEW_DATA/code_diff.txt" 2>/dev/null || true

# Step 3: Build prompt from review_prompt.md
if [ ! -f "$DIR/review_prompt.md" ]; then
    echo "review_prompt.md not found"
    exit 1
fi

PROMPT_FILE="/tmp/claude_review_daily_$(date +%s).md"
sed "s/{date}/$DATE/g" "$DIR/review_prompt.md" > "$PROMPT_FILE"

# Step 4: Invoke Claude Code (with macOS-compatible timeout)
export PATH="/Users/brian/.local/bin:$PATH"
claude -p "$(cat "$PROMPT_FILE")" --allowedTools 'Read,Write,Bash,Glob,Grep,Edit' > /tmp/claude_review_output.log 2>&1 &
CLAUDE_PID=$!
( sleep "$TIMEOUT" && kill "$CLAUDE_PID" 2>/dev/null && echo "Claude review timed out after ${TIMEOUT}s" >> /tmp/claude_review_output.log ) &
TIMER_PID=$!
wait "$CLAUDE_PID" 2>/dev/null
EXIT_CODE=$?
kill "$TIMER_PID" 2>/dev/null
wait "$TIMER_PID" 2>/dev/null

rm -f "$PROMPT_FILE"

# Step 5: Send Telegram summary if generated
if [ -f "$REVIEW_DATA/telegram_summary.txt" ]; then
    SUMMARY=$(cat "$REVIEW_DATA/telegram_summary.txt")
    # Watchdog will read this and send via Telegram
    echo "$SUMMARY" > "$REVIEW_DATA/telegram_summary.txt"
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | daily-review | EXIT_CODE=$EXIT_CODE" >> "$LOG"

exit $EXIT_CODE
