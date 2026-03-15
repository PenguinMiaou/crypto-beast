#!/bin/bash
# Crypto Beast v1.0 — Start Script
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/bot.pid"

echo "=== Crypto Beast v1.0 ==="

# Kill existing bot by name (won't conflict with other main.py)
for pid in $(ps aux | grep "[p]ython.*crypto_system.py" | awk '{print $2}'); do
    echo "Killing old process $pid"
    kill -9 "$pid" 2>/dev/null || true
done
pkill -9 caffeinate 2>/dev/null || true
sleep 2

cd "$DIR"
source .venv/bin/activate

# Clean pycache
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

MODE=${1:-paper}

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading..."
    nohup python crypto_system.py --live >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    exec streamlit run monitoring/dashboard_app.py --server.port 8080
elif [ "$MODE" = "stop" ]; then
    echo "Stopped."
else
    echo "Starting PAPER trading..."
    nohup python crypto_system.py >> logs/bot.log 2>&1 &
    disown
    echo $! > "$PIDFILE"
    echo "PID: $! | Log: $DIR/logs/bot.log"
fi
