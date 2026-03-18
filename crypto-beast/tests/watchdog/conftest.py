"""Shared fixtures for watchdog tests."""
import json
import os
import tempfile
from pathlib import Path
import pytest

@pytest.fixture
def tmp_state_file(tmp_path):
    """Provides a temporary state file path."""
    return str(tmp_path / "watchdog.state")

@pytest.fixture
def tmp_dir(tmp_path):
    """Provides a temporary directory."""
    return str(tmp_path)
