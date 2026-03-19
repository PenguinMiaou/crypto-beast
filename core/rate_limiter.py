import asyncio
import time
from collections import deque

from loguru import logger


class BinanceRateLimiter:
    def __init__(
        self,
        order_limit: int = 1200,
        data_limit: int = 2400,
        window_seconds: int = 60,
    ):
        self.order_limit = order_limit
        self.data_limit = data_limit
        self.window_seconds = window_seconds
        self._order_timestamps: deque[float] = deque()
        self._data_timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    def _clean_old(self, timestamps: deque[float]) -> None:
        cutoff = time.monotonic() - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

    async def acquire_data_slot(self) -> bool:
        async with self._lock:
            self._clean_old(self._data_timestamps)
            if len(self._data_timestamps) >= self.data_limit:
                wait = self._data_timestamps[0] + self.window_seconds - time.monotonic()
                if wait > 0:
                    logger.warning(f"Data rate limit hit, waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    self._clean_old(self._data_timestamps)
            self._data_timestamps.append(time.monotonic())
            return True

    async def acquire_order_slot(self) -> bool:
        async with self._lock:
            self._clean_old(self._order_timestamps)
            if len(self._order_timestamps) >= self.order_limit:
                wait = self._order_timestamps[0] + self.window_seconds - time.monotonic()
                if wait > 0:
                    logger.warning(f"Order rate limit hit, waiting {wait:.1f}s")
                    await asyncio.sleep(wait)
                    self._clean_old(self._order_timestamps)
            self._order_timestamps.append(time.monotonic())
            return True

    def get_usage(self) -> dict:
        self._clean_old(self._data_timestamps)
        self._clean_old(self._order_timestamps)
        return {
            "data_used": len(self._data_timestamps),
            "data_limit": self.data_limit,
            "order_used": len(self._order_timestamps),
            "order_limit": self.order_limit,
        }
