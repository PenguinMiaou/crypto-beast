#!/bin/bash
# Crypto Beast v1.0 — Start Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/bot.pid"

echo "=== Crypto Beast v1.0 ==="

MODE=${1:-paper}

# Dashboard doesn't need to kill trading processes
if [ "$MODE" != "dashboard" ]; then
    # Kill existing watchdog and bot processes
    for pid in $(ps aux | grep "[c]rypto_system" | awk '{print $2}'); do
        echo "Killing old bot process $pid"
        kill -9 "$pid" 2>/dev/null || true
    done
    for pid in $(ps aux | grep "[c]rypto_guardian" | awk '{print $2}'); do
        echo "Killing old watchdog process $pid"
        kill -9 "$pid" 2>/dev/null || true
    done
    pkill -9 caffeinate 2>/dev/null || true
    sleep 2
fi

cd "$DIR"
source .venv/bin/activate

# Clean pycache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading (via watchdog)..."
    nohup python crypto_guardian.py live >> logs/watchdog_out.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "Watchdog PID: $! | Log: $DIR/logs/watchdog.log"
elif [ "$MODE" = "paper" ]; then
    echo "Starting PAPER trading (via watchdog)..."
    nohup python crypto_guardian.py paper >> logs/watchdog_out.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "Watchdog PID: $! | Log: $DIR/logs/watchdog.log"
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    exec streamlit run monitoring/dashboard_app.py --server.port 8080
elif [ "$MODE" = "stop" ]; then
    echo "Stopped."
elif [ "$MODE" = "direct-live" ]; then
    # Bypass watchdog, run bot directly (for debugging)
    echo "Starting LIVE trading (direct, no watchdog)..."
    nohup python crypto_system.py --live >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
elif [ "$MODE" = "direct-paper" ]; then
    echo "Starting PAPER trading (direct, no watchdog)..."
    nohup python crypto_system.py >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
else
    echo "Usage: start.sh [live|paper|dashboard|stop|direct-live|direct-paper]"
fi
