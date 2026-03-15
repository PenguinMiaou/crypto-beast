"""Crypto Beast v1.0 Dashboard — run with: streamlit run monitoring/dashboard_app.py"""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Crypto Beast", page_icon="robot", layout="wide")

DB_PATH = Path(__file__).parent.parent / "crypto_beast.db"


def get_db():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def load_trades(db, status=None, limit=200):
    query = "SELECT id, symbol, side, entry_price, exit_price, quantity, leverage, pnl, fees, strategy, entry_time, exit_time, status FROM trades"
    if status:
        query += f" WHERE status = '{status}'"
    query += " ORDER BY entry_time DESC LIMIT ?"
    rows = db.execute(query, (limit,)).fetchall()
    cols = ["ID", "Symbol", "Side", "Entry", "Exit", "Qty", "Leverage", "PnL", "Fees", "Strategy", "Entry Time", "Exit Time", "Status"]
    return pd.DataFrame(rows, columns=cols)


def load_equity(db):
    rows = db.execute("SELECT timestamp, equity FROM equity_snapshots ORDER BY timestamp DESC LIMIT 500").fetchall()
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows, columns=["Time", "Equity"])


# === Header ===
st.title("Crypto Beast v1.0")

db = get_db()
if db is None:
    st.warning("Database not found. Start the bot first: `python main.py`")
    st.stop()

# === Tabs ===
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Trades", "Strategies", "System"])

# === Overview ===
with tab1:
    trades_df = load_trades(db)
    closed = trades_df[trades_df["Status"] == "CLOSED"] if len(trades_df) > 0 else pd.DataFrame()
    open_trades = trades_df[trades_df["Status"] == "OPEN"] if len(trades_df) > 0 else pd.DataFrame()

    col1, col2, col3, col4 = st.columns(4)

    total_pnl = closed["PnL"].sum() if len(closed) > 0 and closed["PnL"].notna().any() else 0
    wins = len(closed[closed["PnL"] > 0]) if len(closed) > 0 else 0
    losses = len(closed[closed["PnL"] <= 0]) if len(closed) > 0 else 0
    win_rate = wins / len(closed) * 100 if len(closed) > 0 else 0

    col1.metric("Total PnL", f"${total_pnl:+.2f}")
    col2.metric("Open Positions", len(open_trades))
    col3.metric("Win Rate", f"{win_rate:.0f}%", f"{wins}W / {losses}L")
    col4.metric("Total Trades", len(trades_df))

    # Equity chart
    equity_df = load_equity(db)
    if len(equity_df) > 0:
        st.subheader("Equity Curve")
        st.line_chart(equity_df.set_index("Time")["Equity"])

    # Open positions
    if len(open_trades) > 0:
        st.subheader("Open Positions")
        st.dataframe(open_trades[["Symbol", "Side", "Entry", "Qty", "Leverage", "Strategy", "Entry Time"]], use_container_width=True)

# === Trades ===
with tab2:
    st.subheader("Trade History")
    if len(trades_df) > 0:
        st.dataframe(trades_df, use_container_width=True)
    else:
        st.info("No trades yet. Bot is waiting for signals.")

    # PnL chart
    if len(closed) > 0 and closed["PnL"].notna().any():
        st.subheader("PnL per Trade")
        pnl_series = closed["PnL"].reset_index(drop=True)
        st.bar_chart(pnl_series)

        st.subheader("Cumulative PnL")
        st.line_chart(pnl_series.cumsum())

# === Strategies ===
with tab3:
    st.subheader("Strategy Performance")
    if len(closed) > 0:
        perf = closed.groupby("Strategy").agg(
            Trades=("ID", "count"),
            Wins=("PnL", lambda x: (x > 0).sum()),
            TotalPnL=("PnL", "sum"),
            AvgPnL=("PnL", "mean"),
        ).reset_index()
        perf["Win Rate"] = (perf["Wins"] / perf["Trades"] * 100).round(1)
        st.dataframe(perf, use_container_width=True)

        st.subheader("PnL by Strategy")
        st.bar_chart(perf.set_index("Strategy")["TotalPnL"])
    else:
        st.info("No closed trades yet.")

# === System ===
with tab4:
    st.subheader("System Info")

    col1, col2 = st.columns(2)
    col1.metric("Database", "Connected" if db else "Not found")
    col1.metric("DB Size", f"{DB_PATH.stat().st_size / 1024:.1f} KB" if DB_PATH.exists() else "N/A")

    # Recent system health
    try:
        health = db.execute("SELECT timestamp, status, details FROM system_health ORDER BY timestamp DESC LIMIT 5").fetchall()
        if health:
            col2.write("Recent Health:")
            for h in health:
                col2.write(f"  {h[0]}: {h[1]}")
    except Exception:
        col2.info("Health data not available yet")

    # Evolution log
    try:
        evo = db.execute("SELECT timestamp, sharpe_before, sharpe_after FROM evolution_log ORDER BY timestamp DESC LIMIT 5").fetchall()
        if evo:
            st.subheader("Recent Evolution")
            st.dataframe(pd.DataFrame(evo, columns=["Time", "Sharpe Before", "Sharpe After"]))
    except Exception:
        pass

    st.subheader("How to Run")
    st.code("python main.py          # Paper trading\npython main.py --live   # Live trading", language="bash")

db.close()

# Auto-refresh every 10 seconds
st.markdown(
    '<meta http-equiv="refresh" content="10">',
    unsafe_allow_html=True,
)
