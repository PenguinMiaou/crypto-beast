# data/data_feed.py
from collections import defaultdict

import pandas as pd
from loguru import logger


class DataFeed:
    def __init__(self, symbols=None, intervals=None, rate_limiter=None, exchange=None):
        self.symbols = symbols or ["BTCUSDT"]
        self.intervals = intervals or ["5m", "15m", "1h", "4h"]
        self.rate_limiter = rate_limiter
        self._exchange = exchange
        self._cache: dict = defaultdict(lambda: defaultdict(pd.DataFrame))
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
        """Fetch historical klines via REST API using shared exchange."""
        if self._exchange is None:
            logger.warning(f"No exchange set, cannot fetch {symbol} {interval}")
            return pd.DataFrame()
        if self.rate_limiter:
            await self.rate_limiter.acquire_data_slot()
        try:
            ccxt_symbol = symbol.replace("USDT", "/USDT")
            ohlcv = await self._exchange.fetch_ohlcv(ccxt_symbol, interval, limit=limit)

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
