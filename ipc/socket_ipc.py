"""Unix domain socket IPC for watchdog ↔ bot communication."""
import asyncio
import json
import os
from typing import Dict, Optional
from loguru import logger

SOCKET_PATH = "/tmp/crypto_beast_ipc.sock"


class IPCServer:
    """Watchdog side: receive heartbeats and serve state queries."""

    def __init__(self):
        self._state: Dict = {}
        self._server = None

    async def start(self):
        """Start listening on Unix socket."""
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        self._server = await asyncio.start_unix_server(
            self._handle_client, SOCKET_PATH
        )
        logger.info(f"IPC server started at {SOCKET_PATH}")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            if not data:
                writer.close()
                return
            msg = json.loads(data.decode())
            msg_type = msg.get("type")

            if msg_type == "heartbeat":
                self._state.update(msg.get("data", {}))
                writer.write(json.dumps({"ok": True}).encode())
            elif msg_type == "query":
                writer.write(json.dumps(self._state).encode())
            elif msg_type == "command":
                self._state["pending_command"] = msg.get("command")
                writer.write(json.dumps({"ok": True}).encode())
            else:
                writer.write(json.dumps({"error": "unknown type"}).encode())

            await writer.drain()
        except Exception as e:
            logger.debug(f"IPC client error: {e}")
        finally:
            writer.close()

    @property
    def state(self) -> Dict:
        return self._state.copy()

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        logger.info("IPC server stopped")


class IPCClient:
    """Bot side: send heartbeats, query watchdog state."""

    async def send_heartbeat(self, data: dict) -> Optional[dict]:
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
            writer.write(json.dumps({"type": "heartbeat", "data": data}).encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            writer.close()
            return json.loads(resp.decode())
        except Exception:
            return None

    async def query_state(self) -> dict:
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
            writer.write(json.dumps({"type": "query"}).encode())
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            writer.close()
            return json.loads(resp.decode())
        except Exception:
            return {}
