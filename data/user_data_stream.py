"""Binance User Data Stream for real-time account updates."""
import asyncio
import json
import hmac
import hashlib
import time
from typing import Dict, List, Callable, Optional
from loguru import logger


class UserDataStream:
    """Binance Futures User Data Stream.

    Provides real-time:
    - ACCOUNT_UPDATE: balance and position changes
    - ORDER_TRADE_UPDATE: order status changes (SL/TP triggers)

    listenKey must be renewed every 30 minutes.
    """

    def __init__(self, exchange, api_key: str, api_secret: str):
        self._exchange = exchange
        self._api_key = api_key
        self._api_secret = api_secret
        self._listen_key: Optional[str] = None
        self._ws = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._keepalive_task: Optional[asyncio.Task] = None
        self._running = False

    def on(self, event: str, callback: Callable):
        """Register callback: 'account_update' or 'order_update'."""
        self._callbacks.setdefault(event, []).append(callback)

    async def start(self):
        """Get listenKey and start WebSocket."""
        self._running = True
        self._listen_key = await self._create_listen_key()
        if not self._listen_key:
            logger.error("Failed to create listenKey for User Data Stream")
            return
        self._keepalive_task = asyncio.ensure_future(self._keepalive_loop())
        asyncio.ensure_future(self._connect_loop())
        logger.info("User Data Stream started")

    async def _create_listen_key(self) -> Optional[str]:
        """POST /fapi/v1/listenKey."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://fapi.binance.com/fapi/v1/listenKey",
                    headers={"X-MBX-APIKEY": self._api_key}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("listenKey")
                    logger.warning(f"listenKey create failed: {await resp.text()}")
        except Exception as e:
            logger.warning(f"listenKey create error: {e}")
        return None

    async def _extend_listen_key(self):
        """PUT /fapi/v1/listenKey to renew."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.put(
                    "https://fapi.binance.com/fapi/v1/listenKey",
                    headers={"X-MBX-APIKEY": self._api_key}
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"listenKey extend failed: {await resp.text()}")
                        self._listen_key = await self._create_listen_key()
        except Exception as e:
            logger.warning(f"listenKey extend error: {e}")

    async def _keepalive_loop(self):
        """Renew listenKey every 25 minutes."""
        while self._running:
            await asyncio.sleep(25 * 60)
            await self._extend_listen_key()

    async def _connect_loop(self):
        """WebSocket connection with auto-reconnect."""
        while self._running:
            try:
                import websockets
                url = f"wss://fstream.binance.com/ws/{self._listen_key}"
                async with websockets.connect(url, ping_interval=20) as ws:
                    self._ws = ws
                    logger.info("User Data Stream WebSocket connected")
                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw_msg)
                            await self._handle_message(msg)
                        except Exception as e:
                            logger.debug(f"UserDataStream message error: {e}")
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"UserDataStream disconnected: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _handle_message(self, msg: dict):
        """Dispatch account/order events."""
        event = msg.get("e")
        if event == "ACCOUNT_UPDATE":
            for cb in self._callbacks.get("account_update", []):
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(msg)
                    else:
                        cb(msg)
                except Exception as e:
                    logger.debug(f"account_update callback error: {e}")
        elif event == "ORDER_TRADE_UPDATE":
            for cb in self._callbacks.get("order_update", []):
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(msg)
                    else:
                        cb(msg)
                except Exception as e:
                    logger.debug(f"order_update callback error: {e}")

    async def close(self):
        """Shutdown stream."""
        self._running = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
        if self._ws:
            await self._ws.close()
        # DELETE listenKey
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                await session.delete(
                    "https://fapi.binance.com/fapi/v1/listenKey",
                    headers={"X-MBX-APIKEY": self._api_key}
                )
        except Exception:
            pass
        logger.info("User Data Stream closed")
