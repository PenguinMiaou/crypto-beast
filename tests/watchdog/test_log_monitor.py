"""Tests for log file monitor."""
import os
import time
from threading import Event
import pytest
from watchdog_log_monitor import LogMonitor

class TestLogMonitor:
    def test_detects_new_log_lines(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("initial line\n")
        collected = []
        monitor = LogMonitor(log_path, callback=lambda line: collected.append(line))
        monitor.start()
        time.sleep(0.2)
        with open(log_path, "a") as f:
            f.write("07:50:45 | ERROR    | Something went wrong\n")
        time.sleep(0.5)
        monitor.stop()
        assert any("ERROR" in line for line in collected)

    def test_tracks_last_line_time(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("07:50:45 | INFO     | startup\n")
        monitor = LogMonitor(log_path, callback=lambda line: None)
        monitor.start()
        time.sleep(0.2)
        with open(log_path, "a") as f:
            f.write("08:00:00 | INFO     | cycle complete\n")
        time.sleep(0.5)
        monitor.stop()
        assert monitor.last_line_time is not None

    def test_handles_missing_log_file(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "nonexistent.log")
        monitor = LogMonitor(log_path, callback=lambda line: None)
        monitor.start()
        time.sleep(0.3)
        monitor.stop()
        # Should not crash

    def test_handles_log_rotation(self, tmp_dir):
        log_path = os.path.join(tmp_dir, "test.log")
        with open(log_path, "w") as f:
            f.write("line 1\n")
        collected = []
        monitor = LogMonitor(log_path, callback=lambda line: collected.append(line))
        monitor.start()
        time.sleep(0.2)
        with open(log_path, "w") as f:
            f.write("new line after rotation\n")
        time.sleep(0.5)
        monitor.stop()
        assert any("rotation" in line for line in collected)
