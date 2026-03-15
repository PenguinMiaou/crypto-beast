#!/bin/bash
# Crypto Beast v1.0 — Start Script
set -e

SRC="/Volumes/ORICO Media/Crypto Trading System/crypto-beast"
DST="$HOME/briantiong/crypto-beast-runtime"
PIDFILE="$DST/bot.pid"

echo "=== Crypto Beast v1.0 ==="

# Kill existing bot by PID file
if [ -f "$PIDFILE" ]; then
    OLDPID=$(cat "$PIDFILE")
    echo "Killing old bot (PID $OLDPID)..."
    kill -9 "$OLDPID" 2>/dev/null || true
    rm -f "$PIDFILE"
fi

# Also kill any stray processes
for pid in $(ps aux | grep "[p]ython.*main.py" | awk '{print $2}'); do
    echo "Killing stray process $pid"
    kill -9 "$pid" 2>/dev/null || true
done
pkill -9 caffeinate 2>/dev/null || true
sleep 2

# Sync code to local disk
echo "Syncing code..."
mkdir -p "$DST"
rsync -a --delete --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='crypto_beast.db*' --exclude='logs' --exclude='backups' \
    --exclude='bot.pid' \
    "$SRC/" "$DST/"

# Copy .env
[ -f "$SRC/.env" ] && cp "$SRC/.env" "$DST/.env"

# Create local venv if not exists
if [ ! -d "$DST/.venv/bin" ]; then
    echo "Creating local venv..."
    python3 -m venv "$DST/.venv"
    "$DST/.venv/bin/pip" install -r "$DST/requirements.txt" -q
fi

mkdir -p "$DST/logs" "$DST/backups"

# Clean pycache
find "$DST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cd "$DST"
source .venv/bin/activate

MODE=${1:-paper}

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading..."
    echo $$ > "$PIDFILE"
    exec python main.py --live
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    exec streamlit run monitoring/dashboard_app.py --server.port 8080
else
    echo "Starting PAPER trading..."
    echo $$ > "$PIDFILE"
    exec python main.py
fi
