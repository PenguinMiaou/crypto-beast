# monitoring/dashboard_app.py
"""Crypto Beast v1.0 Dashboard"""
import sqlite3
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Crypto Beast", page_icon="robot", layout="wide")

DB_PATH = Path(__file__).parent.parent / "crypto_beast.db"
ENV_PATH = Path(__file__).parent.parent / ".env"


def get_db():
    if not DB_PATH.exists():
        return None
    return sqlite3.connect(str(DB_PATH))


def get_exchange():
    """Get ccxt exchange instance for live data."""
    try:
        from dotenv import dotenv_values
        import ccxt
        env = dotenv_values(str(ENV_PATH))
        return ccxt.binance({
            'apiKey': env.get('BINANCE_API_KEY', ''),
            'secret': env.get('BINANCE_API_SECRET', ''),
            'options': {'defaultType': 'future'},
            'enableRateLimit': True,
        })
    except Exception:
        return None


# === Header ===
st.title("Crypto Beast v1.0")

exchange = get_exchange()
db = get_db()

# === Sidebar ===
st.sidebar.title("Account")
if exchange:
    try:
        account = exchange.fapiPrivateV2GetAccount()
        wallet = float(account.get("totalWalletBalance", 0))
        unrealized = float(account.get("totalUnrealizedProfit", 0))
        available = float(account.get("availableBalance", 0))
        margin_balance = wallet + unrealized

        st.sidebar.metric("Margin Balance", f"${margin_balance:.2f} USDT")
        st.sidebar.metric("Wallet", f"${wallet:.2f}")
        st.sidebar.metric("Unrealized PnL", f"${unrealized:+.2f}")
        st.sidebar.metric("Available", f"${available:.2f}")
    except Exception as e:
        st.sidebar.error(f"API Error: {e}")

st.sidebar.button("Refresh")

# === Tabs ===
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Positions", "Orders", "Trade History", "Strategies", "System"])

# === Tab 1: Live Positions (from Binance) ===
with tab1:
    st.subheader("Open Positions")
    if exchange:
        try:
            account = exchange.fapiPrivateV2GetAccount()
            positions = [p for p in account.get("positions", []) if float(p.get("positionAmt", 0)) != 0]

            if positions:
                pos_data = []
                for p in positions:
                    amt = float(p["positionAmt"])
                    entry = float(p.get("entryPrice", 0))
                    mark = float(p.get("markPrice", 0)) if p.get("markPrice") else 0
                    unrealized = float(p.get("unrealizedProfit", 0))
                    notional = abs(float(p.get("notional", 0)))
                    leverage = p.get("leverage", "1")
                    side = "LONG" if amt > 0 else "SHORT"
                    roi = (unrealized / (notional / int(leverage)) * 100) if notional > 0 else 0

                    pos_data.append({
                        "Symbol": p["symbol"],
                        "Side": side,
                        "Size": f"{abs(amt)}",
                        "Notional": f"${notional:.2f}",
                        "Entry Price": f"${entry:,.2f}",
                        "Mark Price": f"${mark:,.2f}" if mark else "-",
                        "PnL (USDT)": f"${unrealized:+.2f}",
                        "ROI": f"{roi:+.1f}%",
                        "Leverage": f"{leverage}x",
                    })

                df = pd.DataFrame(pos_data)
                st.dataframe(df, use_container_width=True)

                # Summary
                total_pnl = sum(float(p.get("unrealizedProfit", 0)) for p in positions)
                total_notional = sum(abs(float(p.get("notional", 0))) for p in positions)
                st.metric("Total Unrealized PnL", f"${total_pnl:+.2f}")
            else:
                st.info("No open positions")
        except Exception as e:
            st.error(f"Failed to load positions: {e}")

# === Tab 2: Open Orders ===
with tab2:
    st.subheader("Open Orders")
    if exchange:
        try:
            orders = exchange.fetch_open_orders()
            if orders:
                order_data = []
                for o in orders:
                    order_data.append({
                        "Time": o.get("datetime", ""),
                        "Symbol": o.get("symbol", ""),
                        "Type": o.get("type", ""),
                        "Side": o.get("side", ""),
                        "Price": f"${float(o.get('price', 0)):,.2f}",
                        "Amount": o.get("amount", ""),
                        "Status": o.get("status", ""),
                    })
                st.dataframe(pd.DataFrame(order_data), use_container_width=True)
            else:
                st.info("No open orders")
        except Exception as e:
            st.error(f"Failed to load orders: {e}")

# === Tab 3: Trade History (from Binance) ===
with tab3:
    st.subheader("Recent Trades")
    if exchange:
        try:
            # Get recent trades from Binance for main symbols
            all_trades = []
            for symbol in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
                try:
                    trades = exchange.fetch_my_trades(symbol, limit=20)
                    all_trades.extend(trades)
                except Exception:
                    pass

            if all_trades:
                # Sort by time descending
                all_trades.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

                trade_data = []
                for t in all_trades[:30]:
                    trade_data.append({
                        "Time": t.get("datetime", "")[:19],
                        "Symbol": t.get("symbol", ""),
                        "Side": t.get("side", "").upper(),
                        "Price": f"${float(t.get('price', 0)):,.2f}",
                        "Amount": t.get("amount", ""),
                        "Fee": f"${float(t.get('fee', {}).get('cost', 0)):.4f}",
                        "PnL": f"${float(t.get('info', {}).get('realizedPnl', 0)):+.4f}",
                    })
                st.dataframe(pd.DataFrame(trade_data), use_container_width=True)
            else:
                st.info("No trades yet")
        except Exception as e:
            st.error(f"Failed to load trades: {e}")

# === Tab 4: Strategy Performance (from local DB) ===
with tab4:
    st.subheader("Strategy Performance")
    if db:
        try:
            closed = pd.read_sql_query(
                "SELECT strategy, COUNT(*) as trades, "
                "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, "
                "COALESCE(SUM(pnl), 0) as total_pnl, "
                "COALESCE(AVG(pnl), 0) as avg_pnl "
                "FROM trades WHERE status='CLOSED' GROUP BY strategy",
                db
            )
            if len(closed) > 0:
                closed["Win Rate"] = (closed["wins"] / closed["trades"] * 100).round(1)
                st.dataframe(closed, use_container_width=True)
            else:
                st.info("No closed trades yet")
        except Exception as e:
            st.info("No strategy data yet")

# === Tab 5: System ===
with tab5:
    st.subheader("System")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Connections**")
        if exchange:
            try:
                ticker = exchange.fetch_ticker("BTC/USDT")
                st.write(f"Exchange: Connected | BTC=${ticker['last']:,.2f}")
            except Exception:
                st.write("Exchange: Error")

        if db:
            try:
                db.execute("SELECT 1").fetchone()
                st.write("Database: Connected")
            except Exception:
                st.write("Database: Error")

    with col2:
        st.write("**Bot Config**")
        st.write("Mode: LIVE" if os.path.exists(str(DB_PATH)) else "Not running")
        st.write("Symbols: BTC, ETH, SOL")
        st.write("Max Leverage: 5x")
        st.write("Max Positions: 3")

    # Recent activity from DB
    if db:
        try:
            recent = pd.read_sql_query(
                "SELECT symbol, side, entry_price, exit_price, pnl, strategy, status, entry_time "
                "FROM trades ORDER BY entry_time DESC LIMIT 10",
                db
            )
            if len(recent) > 0:
                st.subheader("Recent Bot Activity")
                st.dataframe(recent, use_container_width=True)
        except Exception:
            pass

if db:
    db.close()
