"""Monitor bot log file for errors and activity."""
import os
import time
from datetime import datetime, timezone
from threading import Thread, Event
from typing import Callable, Optional
from loguru import logger


class LogMonitor:
    """Tail a log file and invoke callback on new lines."""

    POLL_INTERVAL = 0.5  # seconds

    def __init__(self, log_path: str, callback: Callable[[str], None]):
        self._log_path = log_path
        self._callback = callback
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self.last_line_time: Optional[datetime] = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        """Tail the log file, detect rotation by size change."""
        while not self._stop_event.is_set():
            try:
                if not os.path.exists(self._log_path):
                    self._stop_event.wait(self.POLL_INTERVAL)
                    continue

                with open(self._log_path, "r") as f:
                    f.seek(0, 2)
                    file_size = f.tell()

                    while not self._stop_event.is_set():
                        line = f.readline()
                        if line:
                            line = line.strip()
                            if line:
                                self.last_line_time = datetime.now(timezone.utc)
                                self._callback(line)
                        else:
                            try:
                                current_size = os.path.getsize(self._log_path)
                                if current_size < file_size:
                                    break
                                file_size = current_size
                            except OSError:
                                break
                            self._stop_event.wait(self.POLL_INTERVAL)

            except Exception as e:
                logger.debug(f"Log monitor error: {e}")
                self._stop_event.wait(2)
