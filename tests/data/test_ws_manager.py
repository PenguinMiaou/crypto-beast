import pytest
from data.ws_manager import BinanceWSManager


def test_ws_manager_init():
    ws = BinanceWSManager(symbols=["BTCUSDT", "ETHUSDT"])
    assert len(ws._symbols) == 2
    assert not ws._running


def test_ws_manager_callback_registration():
    ws = BinanceWSManager(symbols=["BTCUSDT"])
    cb = lambda data: None
    ws.on("aggTrade", cb)
    assert len(ws._callbacks.get("aggTrade", [])) == 1


def test_ws_manager_multiple_callbacks():
    ws = BinanceWSManager(symbols=["BTCUSDT"])
    ws.on("aggTrade", lambda d: None)
    ws.on("aggTrade", lambda d: None)
    ws.on("depth", lambda d: None)
    assert len(ws._callbacks["aggTrade"]) == 2
    assert len(ws._callbacks["depth"]) == 1
