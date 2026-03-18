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
            if symbol.endswith("USDT") and "/" not in symbol:
                ccxt_symbol = symbol[:-4] + "/USDT"
            else:
                ccxt_symbol = symbol
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

    def save_to_db(self, db) -> None:
        """Persist cached klines to database for backtesting."""
        for symbol, intervals in self._cache.items():
            for interval, df in intervals.items():
                if len(df) == 0:
                    continue
                for _, row in df.tail(50).iterrows():  # Save last 50 candles
                    try:
                        db.execute(
                            """INSERT OR REPLACE INTO klines
                               (symbol, interval, open_time, open, high, low, close, volume)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (symbol, interval, str(row["open_time"]),
                             float(row["open"]), float(row["high"]),
                             float(row["low"]), float(row["close"]), float(row["volume"]))
                        )
                    except Exception:
                        pass

    def load_from_db(self, db) -> None:
        """Load cached klines from database on startup."""
        for symbol in self.symbols:
            for interval in self.intervals:
                try:
                    rows = db.execute(
                        "SELECT open_time, open, high, low, close, volume FROM klines WHERE symbol=? AND interval=? ORDER BY open_time DESC LIMIT 500",
                        (symbol, interval)
                    ).fetchall()
                    if rows:
                        df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume"])
                        df["open_time"] = pd.to_datetime(df["open_time"])
                        df = df.sort_values("open_time").reset_index(drop=True)
                        self._cache[symbol][interval] = df
                except Exception:
                    pass
