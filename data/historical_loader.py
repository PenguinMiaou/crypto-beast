"""Fetch and cache historical klines from Binance for backtesting."""
import asyncio
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from core.database import Database


class HistoricalDataLoader:
    """Fetch historical klines from Binance and cache in SQLite."""

    def __init__(self, exchange, db: Database):
        self._exchange = exchange
        self._db = db
        self._ensure_table()

    def _ensure_table(self):
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS klines_cache (
                symbol TEXT, interval TEXT, open_time INTEGER,
                open REAL, high REAL, low REAL, close REAL, volume REAL,
                PRIMARY KEY (symbol, interval, open_time)
            )
        """)

    async def fetch_range(self, symbol: str, interval: str,
                          start_date: str, end_date: str) -> pd.DataFrame:
        """Fetch klines from Binance, cache locally, return DataFrame.

        Paginates with max 1500 bars per request. Only fetches data not in cache.
        """
        # Convert dates to timestamps
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        # Check what we already have cached
        cached = self._db.execute(
            "SELECT MIN(open_time), MAX(open_time) FROM klines_cache WHERE symbol=? AND interval=?",
            (symbol, interval)
        ).fetchone()

        all_bars = []
        since = start_ts

        while since < end_ts:
            try:
                bars = await self._exchange.fetch_ohlcv(
                    symbol, interval, since=since, limit=1500
                )
                if not bars:
                    break
                all_bars.extend(bars)
                since = bars[-1][0] + 1  # Next bar after last
                if len(bars) < 1500:
                    break  # No more data
            except Exception as e:
                logger.warning(f"fetch_ohlcv error: {e}")
                break

        # Cache to DB
        for bar in all_bars:
            try:
                self._db.execute(
                    "INSERT OR REPLACE INTO klines_cache "
                    "(symbol, interval, open_time, open, high, low, close, volume) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (symbol, interval, bar[0], bar[1], bar[2], bar[3], bar[4], bar[5])
                )
            except Exception:
                pass

        return self.load_cached(symbol, interval, start_date, end_date)

    def load_cached(self, symbol: str, interval: str,
                    start_date: str, end_date: str) -> pd.DataFrame:
        """Load from local cache only."""
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        rows = self._db.execute(
            "SELECT open_time, open, high, low, close, volume "
            "FROM klines_cache WHERE symbol=? AND interval=? "
            "AND open_time >= ? AND open_time <= ? ORDER BY open_time",
            (symbol, interval, start_ts, end_ts)
        ).fetchall()

        if not rows:
            return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        return df
