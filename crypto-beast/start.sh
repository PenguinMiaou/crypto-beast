#!/bin/bash
# Crypto Beast v1.0 — Start Script
set -e

SRC="/Volumes/ORICO Media/Crypto Trading System/crypto-beast"
DST="$HOME/briantiong/crypto-beast-runtime"

echo "=== Crypto Beast v1.0 ==="

# Kill any existing bot processes first
echo "Stopping existing processes..."
pkill -9 -f "python.*main.py" 2>/dev/null || true
pkill -9 -f caffeinate 2>/dev/null || true
pkill -9 -f streamlit 2>/dev/null || true
sleep 2

# Sync code to local disk
echo "Syncing code..."
mkdir -p "$DST"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='crypto_beast.db*' --exclude='logs/*.log' \
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
cd "$DST"
source .venv/bin/activate

MODE=${1:-paper}

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading..."
    exec python main.py --live
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    exec streamlit run monitoring/dashboard_app.py --server.port 8080
else
    echo "Starting PAPER trading..."
    exec python main.py
fi
