"""Streamlit dashboard - run with: streamlit run monitoring/dashboard_app.py"""
import streamlit as st

st.set_page_config(page_title="Crypto Beast", page_icon="robot", layout="wide")

st.title("Crypto Beast v1.0 Dashboard")
st.info("Dashboard data will be available when the trading bot is running.")

# Placeholder pages
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Trades", "Strategies", "System"])

with tab1:
    st.header("Portfolio Overview")
    st.metric("Equity", "$100.00", "0%")
    st.metric("Daily P&L", "$0.00")

with tab2:
    st.header("Trade History")
    st.write("No trades yet.")

with tab3:
    st.header("Strategy Performance")
    st.write("No data yet.")

with tab4:
    st.header("System Status")
    st.write("System not yet initialized.")
