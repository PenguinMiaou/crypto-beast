"""Binance WebSocket manager for real-time market data streams."""
import asyncio
import json
from typing import Dict, List, Callable, Optional
from loguru import logger


class BinanceWSManager:
    """Manages Binance Futures WebSocket connections for market data.

    Subscribes to aggTrade (for WhaleTracker), forceOrder (for LiquidationHunter),
    and depth (for OrderBookSniper) streams.
    """

    RECONNECT_DELAYS = [1, 2, 5, 10, 30, 60]  # Exponential backoff

    def __init__(self, symbols: List[str]):
        self._symbols = symbols
        self._callbacks: Dict[str, List[Callable]] = {}
        self._ws = None
        self._running = False
        self._reconnect_count = 0

    def on(self, event: str, callback: Callable):
        """Register callback for event type (aggTrade, forceOrder, depth)."""
        self._callbacks.setdefault(event, []).append(callback)

    async def start(self):
        """Start WebSocket connection in background task."""
        self._running = True
        asyncio.ensure_future(self._connect_loop())
        logger.info(f"WSManager started for {len(self._symbols)} symbols")

    async def _connect_loop(self):
        """Connection loop with auto-reconnect."""
        while self._running:
            try:
                await self._connect()
            except Exception as e:
                if not self._running:
                    break
                delay = self.RECONNECT_DELAYS[min(self._reconnect_count, len(self.RECONNECT_DELAYS) - 1)]
                logger.warning(f"WebSocket disconnected: {e}. Reconnecting in {delay}s...")
                self._reconnect_count += 1
                await asyncio.sleep(delay)

    async def _connect(self):
        """Establish WebSocket connection and process messages."""
        import websockets

        streams = []
        for sym in self._symbols:
            s = sym.lower()
            streams.append(f"{s}@aggTrade")
            streams.append(f"{s}@depth20@100ms")
        streams.append("!forceOrder@arr")

        url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
            self._ws = ws
            self._reconnect_count = 0
            logger.info(f"WebSocket connected: {len(streams)} streams")

            async for raw_msg in ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw_msg)
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"WSManager message error: {e}")

    async def _handle_message(self, msg: dict):
        """Parse and dispatch message to registered callbacks."""
        stream = msg.get("stream", "")
        data = msg.get("data", {})

        if "aggTrade" in stream:
            await self._dispatch("aggTrade", data)
        elif "forceOrder" in stream:
            await self._dispatch("forceOrder", data)
        elif "depth" in stream:
            await self._dispatch("depth", data)

    async def _dispatch(self, event: str, data: dict):
        """Call all registered callbacks for event."""
        for cb in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.debug(f"WSManager callback error ({event}): {e}")

    async def close(self):
        """Gracefully close WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
        logger.info("WSManager closed")
