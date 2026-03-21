import pytest
from unittest.mock import MagicMock
from data.user_data_stream import UserDataStream


def test_user_data_stream_init():
    uds = UserDataStream(MagicMock(), "test_key", "test_secret")
    assert uds._listen_key is None
    assert not uds._running


def test_user_data_stream_callback():
    uds = UserDataStream(MagicMock(), "test_key", "test_secret")
    cb = lambda data: None
    uds.on("account_update", cb)
    assert len(uds._callbacks.get("account_update", [])) == 1
