#!/usr/bin/env python3
"""Extract review data from DB for Claude daily review."""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone


def extract(db_path: str, date: str, output_dir: str) -> None:
    """Extract all review data for a given date."""
    os.makedirs(output_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Trades today
    rows = conn.execute(
        "SELECT * FROM trades WHERE entry_time >= ? OR exit_time >= ?",
        (date, date)
    ).fetchall()
    _save(output_dir, "trades_today.json", [dict(r) for r in rows])

    # Trades last 7 days
    d7 = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM trades WHERE entry_time >= ?", (d7,)
    ).fetchall()
    _save(output_dir, "trades_7d.json", [dict(r) for r in rows])

    # Equity snapshots
    rows = conn.execute(
        "SELECT * FROM equity_snapshots ORDER BY timestamp DESC LIMIT 168"
    ).fetchall()
    _save(output_dir, "equity_snapshots.json", [dict(r) for r in rows])

    # Evolution log
    rows = conn.execute(
        "SELECT * FROM evolution_log ORDER BY timestamp DESC LIMIT 30"
    ).fetchall()
    _save(output_dir, "evolution_log.json", [dict(r) for r in rows])

    # Strategy performance
    rows = conn.execute(
        "SELECT * FROM strategy_performance ORDER BY date DESC LIMIT 30"
    ).fetchall()
    _save(output_dir, "strategy_performance.json", [dict(r) for r in rows])

    # System health
    try:
        rows = conn.execute(
            "SELECT * FROM system_health ORDER BY timestamp DESC LIMIT 50"
        ).fetchall()
        _save(output_dir, "system_health.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "system_health.json", [])

    # Rejected signals (if table exists)
    try:
        rows = conn.execute(
            "SELECT * FROM rejected_signals WHERE timestamp >= ?", (date,)
        ).fetchall()
        _save(output_dir, "rejected_signals.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "rejected_signals.json", [])

    # BTC daily klines for benchmark
    try:
        rows = conn.execute(
            "SELECT * FROM klines WHERE symbol='BTCUSDT' AND interval='1d' ORDER BY open_time DESC LIMIT 30"
        ).fetchall()
        _save(output_dir, "btc_daily.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "btc_daily.json", [])

    # Watchdog state (directives, events)
    state_path = os.path.join(os.path.dirname(db_path), "watchdog.state")
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)
        _save(output_dir, "directives.json", state.get("directives", []))
        _save(output_dir, "watchdog_events.json", state.get("recent_events", []))
    else:
        _save(output_dir, "directives.json", [])
        _save(output_dir, "watchdog_events.json", [])

    # Change registry (if table exists)
    try:
        rows = conn.execute(
            "SELECT * FROM change_registry ORDER BY timestamp DESC LIMIT 30"
        ).fetchall()
        _save(output_dir, "change_registry_7d.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "change_registry_7d.json", [])

    # Recommendation history (if table exists)
    try:
        rows = conn.execute(
            "SELECT * FROM recommendation_history ORDER BY date DESC LIMIT 30"
        ).fetchall()
        _save(output_dir, "recommendation_history.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "recommendation_history.json", [])

    # Strategy version (if table exists)
    try:
        rows = conn.execute(
            "SELECT * FROM strategy_versions ORDER BY date DESC LIMIT 10"
        ).fetchall()
        _save(output_dir, "strategy_version.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "strategy_version.json", [])

    # Watchdog interventions (if table exists)
    try:
        rows = conn.execute(
            "SELECT * FROM watchdog_interventions WHERE timestamp >= ? ORDER BY timestamp DESC",
            (date,)
        ).fetchall()
        _save(output_dir, "watchdog_interventions.json", [dict(r) for r in rows])
    except Exception:
        _save(output_dir, "watchdog_interventions.json", [])

    conn.close()


def _save(output_dir: str, filename: str, data) -> None:
    path = os.path.join(output_dir, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--output", default="review_data")
    parser.add_argument("--db", default="crypto_beast.db")
    args = parser.parse_args()
    extract(args.db, args.date, args.output)
