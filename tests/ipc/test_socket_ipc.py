import pytest
import asyncio
from ipc.socket_ipc import IPCServer, IPCClient
import ipc.socket_ipc as ipc_mod


@pytest.mark.asyncio
async def test_ipc_heartbeat():
    import tempfile
    import os
    # macOS AF_UNIX path limit is 104 chars; use /tmp directly with a short name
    sock_path = f"/tmp/cb_test_{os.getpid()}.sock"
    ipc_mod.SOCKET_PATH = sock_path

    server = IPCServer()
    await server.start()
    try:
        client = IPCClient()
        result = await client.send_heartbeat({"cycle": 42, "symbol": "BTCUSDT"})
        assert result is not None
        assert result.get("ok") is True

        state = await client.query_state()
        assert state.get("cycle") == 42
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_ipc_client_no_server():
    """Client should return None/empty when server is down."""
    ipc_mod.SOCKET_PATH = "/tmp/nonexistent_test.sock"
    client = IPCClient()
    result = await client.send_heartbeat({"test": True})
    assert result is None
    state = await client.query_state()
    assert state == {}
