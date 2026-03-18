#!/bin/bash
# Emergency fix: Claude Code analyzes and fixes unknown errors
set +e  # Don't exit on error — we need to log EXIT_CODE

DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

TIMEOUT=540  # 9 minutes (parent has 10min timeout, leave 1min buffer)
LOG="$DIR/logs/claude_calls.log"
CONTEXT_FILE="/tmp/crypto_beast_error_context.txt"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | emergency-fix | START" >> "$LOG"

if [ ! -f "$CONTEXT_FILE" ]; then
    echo "No error context file found"
    exit 1
fi

# Build prompt with error context + recent logs
PROMPT_FILE="/tmp/claude_fix_$(date +%s).md"
cat > "$PROMPT_FILE" << 'PROMPT_END'
You are the emergency fixer for Crypto Beast trading bot.

## Error Context
PROMPT_END

cat "$CONTEXT_FILE" >> "$PROMPT_FILE"

cat >> "$PROMPT_FILE" << 'PROMPT_END'

## Recent Logs (last 50 lines)
PROMPT_END

tail -50 "$DIR/logs/bot.log" >> "$PROMPT_FILE" 2>/dev/null || echo "No bot.log found" >> "$PROMPT_FILE"

cat >> "$PROMPT_FILE" << 'PROMPT_END'

## Instructions
1. Analyze the error above
2. Read relevant source files to understand the bug
3. Fix the code if possible
4. Run `python -m pytest -q` to verify the fix
5. If tests fail, revert with `git checkout .`
6. NEVER modify .env, watchdog.py, or watchdog_state.py
7. Keep fixes surgical — only fix the specific error

## Rules
- If you cannot fix the error, exit without changes
- Chinese language for any comments added
PROMPT_END

# Invoke Claude Code
source "$DIR/.venv/bin/activate" 2>/dev/null || true
export PATH="/Users/brian/.local/bin:$PATH"
claude -p "$(cat "$PROMPT_FILE")" --allowedTools 'Read,Bash,Glob,Grep,Edit,Write' > /tmp/claude_fix_output.log 2>&1 &
CLAUDE_PID=$!
( sleep "$TIMEOUT" && kill "$CLAUDE_PID" 2>/dev/null ) &
TIMER_PID=$!
wait "$CLAUDE_PID" 2>/dev/null
EXIT_CODE=$?
kill "$TIMER_PID" 2>/dev/null
wait "$TIMER_PID" 2>/dev/null

rm -f "$PROMPT_FILE" "$CONTEXT_FILE"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | emergency-fix | EXIT_CODE=$EXIT_CODE" >> "$LOG"

exit $EXIT_CODE
