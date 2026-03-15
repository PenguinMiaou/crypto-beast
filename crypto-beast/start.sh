#!/bin/bash
# Crypto Beast v1.0 — Start Script
# Copies code to local disk and runs from there to avoid external drive I/O issues

set -e

SRC="/Volumes/ORICO Media/Crypto Trading System/crypto-beast"
DST="/tmp/crypto-beast"
VENV="$SRC/.venv"

echo "=== Crypto Beast v1.0 ==="

# Sync code to local disk
echo "Syncing code to local disk..."
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='crypto_beast.db*' --exclude='logs/*.log' \
    "$SRC/" "$DST/"

# Link venv (stays on external drive, that's fine)
rm -f "$DST/.venv"
ln -s "$VENV" "$DST/.venv"

# Copy .env if exists
[ -f "$SRC/.env" ] && cp "$SRC/.env" "$DST/.env"

# Create dirs
mkdir -p "$DST/logs" "$DST/backups"

cd "$DST"
source .venv/bin/activate

MODE=${1:-paper}

if [ "$MODE" = "live" ]; then
    echo "Starting LIVE trading..."
    python main.py --live
elif [ "$MODE" = "dashboard" ]; then
    echo "Starting dashboard on http://localhost:8080..."
    streamlit run monitoring/dashboard_app.py --server.port 8080
else
    echo "Starting PAPER trading..."
    python main.py
fi
