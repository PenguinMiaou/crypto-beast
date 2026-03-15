# data/data_feed.py
import asyncio
from collections import defaultdict
from datetime import datetime

import pandas as pd
from loguru import logger


class DataFeed:
    def __init__(self, symbols: list[str] = None, intervals: list[str] = None, rate_limiter=None):
        self.symbols = symbols or ["BTCUSDT"]
        self.intervals = intervals or ["5m", "15m", "1h", "4h"]
        self.rate_limiter = rate_limiter
        self._cache: dict[str, dict[str, pd.DataFrame]] = defaultdict(lambda: defaultdict(pd.DataFrame))
        self._connected = False

    async def connect(self) -> None:
        """Establish WebSocket connections for real-time data."""
        # Will be implemented with python-binance WebSocket
        # For now, use REST polling
        logger.info(f"DataFeed connecting for {self.symbols} on {self.intervals}")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("DataFeed disconnected")

    async def fetch_historical(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """Fetch historical klines via REST API."""
        if self.rate_limiter:
            await self.rate_limiter.acquire_data_slot()
        try:
            import ccxt.async_support as ccxt

            exchange = ccxt.binance({"options": {"defaultType": "future"}})
            timeframe_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h"}
            ohlcv = await exchange.fetch_ohlcv(
                symbol.replace("USDT", "/USDT"), timeframe_map[interval], limit=limit
            )
            await exchange.close()

            df = pd.DataFrame(ohlcv, columns=["open_time", "open", "high", "low", "close", "volume"])
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            self._cache[symbol][interval] = df
            return df
        except Exception as e:
            logger.error(f"Failed to fetch {symbol} {interval}: {e}")
            return pd.DataFrame()

    async def fetch(self) -> dict[str, dict[str, pd.DataFrame]]:
        """Fetch latest data for all symbols and intervals."""
        for symbol in self.symbols:
            for interval in self.intervals:
                await self.fetch_historical(symbol, interval)
        return dict(self._cache)

    def get_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """Get cached OHLCV data."""
        if symbol not in self._cache or interval not in self._cache[symbol]:
            return pd.DataFrame()
        df = self._cache[symbol][interval]
        if len(df) == 0:
            return df
        return df.tail(limit).reset_index(drop=True)

    def get_current_price(self, symbol: str) -> float:
        """Get latest close price from cache."""
        df = self.get_klines(symbol, self.intervals[0], limit=1)
        if len(df) == 0:
            return 0.0
        return float(df.iloc[-1]["close"])

    def update_cache(self, symbol: str, interval: str, df: pd.DataFrame) -> None:
        """Manually update cache (used for testing and WebSocket updates)."""
        self._cache[symbol][interval] = df
