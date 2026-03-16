#!/usr/bin/env python3
"""Crypto Beast Watchdog Daemon — monitors and auto-restarts the trading bot."""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Dict, List, Optional

from loguru import logger

from watchdog_event_router import EventRouter, EventLevel
from watchdog_log_monitor import LogMonitor
from watchdog_state import WatchdogState
from watchdog_telegram import WatchdogTelegram


class WatchdogDaemon:
    """Main watchdog daemon: monitors bot process, handles L1 events."""

    def __init__(self, mode: str = "paper", base_dir: Optional[str] = None):
        self._base_dir = base_dir or str(Path(__file__).parent)
        self._mode = mode
        self._shutting_down = Event()
        self._bot_process: Optional[subprocess.Popen] = None
        self._start_time = time.time()
        self._network_retry_count = 0

        # Load config
        sys.path.insert(0, self._base_dir)
        from config import Config
        config = Config(os.path.join(self._base_dir, ".env"))

        # Paths
        self._state_path = os.path.join(self._base_dir, "watchdog.state")
        self._log_path = os.path.join(self._base_dir, "logs", "bot.log")
        bot_args = ["python", os.path.join(self._base_dir, "crypto_system.py")]
        if mode == "live":
            bot_args.append("--live")
        self._bot_command = bot_args

        # Config values
        self._heartbeat_interval = config.watchdog_heartbeat_interval
        self._frozen_threshold = config.watchdog_frozen_threshold
        self._max_restarts = config.watchdog_max_restarts
        self._restart_window = config.watchdog_restart_window

        # Components
        self._telegram = WatchdogTelegram(
            config.telegram_bot_token, config.telegram_chat_id)
        self._state = WatchdogState(self._state_path)
        self._event_router = EventRouter(
            telegram=self._telegram,
            state=self._state,
            max_restarts=self._max_restarts,
            restart_window=self._restart_window,
        )
        self._log_monitor: Optional[LogMonitor] = None
        self._commands: Optional['WatchdogCommands'] = None

    # === Process Management ===

    def start_bot(self) -> None:
        """Start the trading bot as a subprocess."""
        logger.info(f"Starting bot: {' '.join(self._bot_command)}")
        os.makedirs(os.path.join(self._base_dir, "logs"), exist_ok=True)
        log_file = open(self._log_path, "a")
        self._bot_process = subprocess.Popen(
            self._bot_command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=self._base_dir,
        )
        self._state.update(
            bot_pid=self._bot_process.pid,
            status="running",
        )
        logger.info(f"Bot started with PID {self._bot_process.pid}")

    def stop_bot(self, timeout: int = 30) -> None:
        """Gracefully stop the bot (SIGTERM, then SIGKILL)."""
        if not self._bot_process:
            return
        pid = self._bot_process.pid
        logger.info(f"Stopping bot PID {pid}...")
        try:
            self._bot_process.terminate()
            self._bot_process.wait(timeout=timeout)
            logger.info(f"Bot PID {pid} stopped gracefully")
        except subprocess.TimeoutExpired:
            logger.warning(f"Bot PID {pid} didn't stop, force killing")
            self._bot_process.kill()
            self._bot_process.wait(timeout=5)
        self._bot_process = None
        self._state.update(bot_pid=None, status="stopped")

    def is_bot_running(self) -> bool:
        """Check if bot process is alive."""
        if self._bot_process is None:
            return False
        return self._bot_process.poll() is None

    def restart_bot(self, reason: str) -> None:
        """Stop and restart the bot."""
        logger.warning(f"Restarting bot: {reason}")
        self._event_router.record_restart()

        if self._event_router.restart_limit_exceeded():
            msg = f"Restart limit exceeded ({self._max_restarts} in {self._restart_window}s)"
            logger.error(msg)
            self._telegram.send(f"[L2] {msg} — need Claude Code intervention")
            self._state.add_event("L2", msg)
            self.stop_bot()
            self._state.update(status="L2-TERMINAL")
            return

        self.stop_bot()
        time.sleep(2)
        self.start_bot()
        self._state.update(
            restarts_today=self._state.read()["restarts_today"] + 1)
        self._telegram.send(f"[L1] Bot restarted: {reason}")
        self._state.add_event("L1", f"Bot restarted: {reason}")

    # === Log Event Handling ===

    def _on_log_line(self, line: str) -> None:
        """Callback for new log lines from the monitor."""
        level, action = self._event_router.classify(line)

        if level == EventLevel.IGNORE:
            return

        if level == EventLevel.L1:
            result = self._event_router.handle_l1(action, line[-200:])
            if result == "restart_needed":
                self.restart_bot("L1: " + line[-100:])
            elif result == "transient":
                self._network_retry_count += 1
                if self._network_retry_count > 3:
                    self._network_retry_count = 0
                    # Network retries exhausted — mark as L2 for Claude
                    self._telegram.send(
                        "[L2] Persistent network issues (3 retries exhausted) — "
                        "need Claude Code analysis")
                    self._state.add_event("L2", "Persistent network issues")
                else:
                    time.sleep(30)
            else:
                self._network_retry_count = 0

        elif level == EventLevel.L2:
            logger.warning(f"L2 event detected: {line[-200:]}")
            self._telegram.send(
                f"[L2] Unknown error detected:\n{line[-200:]}\n"
                "Claude Code intervention needed (Plan 3)")
            self._state.add_event("L2", line[-200:])

    # === Heartbeat (Main Loop) ===

    def _check_frozen(self) -> bool:
        """Check if bot is frozen (no log output + low CPU)."""
        if not self._log_monitor or not self._log_monitor.last_line_time:
            return False

        elapsed = (datetime.now(timezone.utc) -
                   self._log_monitor.last_line_time).total_seconds()
        if elapsed < self._frozen_threshold:
            return False

        # Check CPU usage before declaring frozen
        if self._bot_process:
            try:
                result = subprocess.run(
                    ["ps", "-p", str(self._bot_process.pid), "-o", "%cpu="],
                    capture_output=True, text=True, timeout=5,
                )
                cpu = float(result.stdout.strip())
                if cpu > 1.0:
                    return False  # Still doing work, not frozen
            except Exception:
                pass

        return True

    def run_heartbeat(self) -> None:
        """Single heartbeat cycle."""
        now = datetime.now(timezone.utc)

        # Update heartbeat timestamp
        self._state.update(
            last_heartbeat=now.isoformat(),
            uptime_seconds=int(time.time() - self._start_time),
            last_log_line_time=(
                self._log_monitor.last_line_time.isoformat()
                if self._log_monitor and self._log_monitor.last_line_time
                else None
            ),
        )

        # Check for commands from Telegram
        cmd = self._state.pop_command()
        if cmd:
            self._handle_command(cmd)

        # Check bot status
        if self._state.read().get("status") == "L2-TERMINAL":
            return  # Don't auto-restart in terminal state

        if not self.is_bot_running():
            self._telegram.send("[L1] Bot process crashed — auto-restarting")
            self.restart_bot("Process exited unexpectedly")
            return

        # Check frozen
        if self._check_frozen():
            self._telegram.send(
                f"[L1] Bot frozen (no log output for "
                f"{self._frozen_threshold}s) — restarting")
            self.restart_bot("Process frozen")
            return

        # Reset daily counters at midnight UTC
        if now.hour == 0 and now.minute == 0:
            self._state.reset_daily_counters()

    def _handle_command(self, cmd) -> None:
        """Process a command from watchdog.state."""
        if isinstance(cmd, str):
            action = cmd
        elif isinstance(cmd, dict):
            action = cmd.get("action", "")
        else:
            return

        if action == "STOP":
            logger.info("STOP command received")
            self._telegram.send("[CMD] Shutting down bot and watchdog...")
            self.stop_bot()
            self._shutting_down.set()

        elif action == "RESTART":
            logger.info("RESTART command received")
            self.restart_bot("Manual restart via Telegram")
            self._state.update(status="running")

        elif action == "SHUTDOWN":
            logger.info("SHUTDOWN command — graceful bot stop")
            self.stop_bot()
            self._state.update(status="stopped")
            self._telegram.send("[CMD] Bot stopped. Watchdog still active.")

    # === Pre-flight Checks ===

    def run_preflight_checks(self, base_dir: Optional[str] = None) -> List[str]:
        """Verify environment before starting bot. Returns list of errors."""
        base = base_dir or self._base_dir
        errors = []

        # Check .env
        env_path = os.path.join(base, ".env")
        if not os.path.exists(env_path):
            errors.append(f".env not found at {env_path}")
        else:
            with open(env_path) as f:
                content = f.read()
            for key in ["BINANCE_API_KEY", "BINANCE_API_SECRET",
                        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]:
                if key not in content:
                    errors.append(f".env missing {key}")

        # Check venv
        venv_path = os.path.join(base, ".venv")
        if not os.path.isdir(venv_path):
            errors.append(f".venv not found at {venv_path}")

        # Check disk space (100MB minimum)
        try:
            usage = shutil.disk_usage(base)
            if usage.free < 100 * 1024 * 1024:
                errors.append(
                    f"Low disk space: {usage.free // (1024*1024)}MB free")
        except Exception as e:
            errors.append(f"Disk check failed: {e}")

        # Check DB integrity
        db_path = os.path.join(base, "crypto_beast.db")
        if os.path.exists(db_path):
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result[0] != "ok":
                    errors.append(f"DB integrity check failed: {result[0]}")
                conn.close()
            except Exception as e:
                errors.append(f"DB check failed: {e}")

        # Check no zombie processes
        try:
            result = subprocess.run(
                ["pgrep", "-f", "crypto_system"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p for p in result.stdout.strip().split("\n") if p.strip()]
            if len(pids) > 0:
                errors.append(
                    f"Found {len(pids)} existing crypto_system process(es): "
                    f"{', '.join(pids)}")
        except Exception:
            pass

        # Check Binance API reachable
        try:
            import requests
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/ping", timeout=10)
            if resp.status_code != 200:
                errors.append(
                    f"Binance API unreachable (status {resp.status_code})")
        except Exception as e:
            errors.append(f"Binance API unreachable: {e}")

        return errors

    # === Self-Check Thread ===

    def _run_self_check(self) -> None:
        """Monitor main thread liveness. Kills process if hung."""
        while not self._shutting_down.is_set():
            self._shutting_down.wait(30)
            if self._shutting_down.is_set():
                return
            try:
                data = self._state.read()
                last_hb = data.get("last_heartbeat")
                if last_hb:
                    last = datetime.fromisoformat(last_hb)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                    if elapsed > 120:
                        logger.critical(
                            f"Watchdog main thread hung ({elapsed:.0f}s). "
                            "Forcing exit for launchd restart.")
                        self._telegram.send(
                            "[WATCHDOG] Main thread hung, restarting...")
                        os._exit(1)
            except Exception:
                pass

    # === Telegram Polling ===

    def _poll_telegram(self) -> None:
        """Poll Telegram for commands in a separate thread."""
        while not self._shutting_down.is_set():
            try:
                updates = self._telegram.poll()
                for command, args in updates:
                    self._commands.handle(command, args)
            except Exception as e:
                logger.debug(f"Telegram polling error: {e}")
            self._shutting_down.wait(2)

    # === Main Entry Point ===

    def run(self) -> None:
        """Main daemon loop."""
        # Configure logging
        logger.remove()
        logger.add(sys.stderr, level="INFO",
                   format="{time:HH:mm:ss} | {level: <8} | {message}")
        logger.add(
            os.path.join(self._base_dir, "logs", "watchdog.log"),
            rotation="1 day", retention="30 days", level="DEBUG",
        )

        logger.info(f"Watchdog daemon starting (mode={self._mode})")

        # Signal handling
        def handle_signal(signum, frame):
            logger.info(f"Watchdog received signal {signum}, shutting down")
            self._shutting_down.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Check for stale heartbeat (recovery from crash/downtime)
        try:
            data = self._state.read()
            last_hb = data.get("last_heartbeat")
            if last_hb:
                last = datetime.fromisoformat(last_hb)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed > 3600:
                    self._telegram.send(
                        f"[WATCHDOG] Extended downtime ({int(elapsed // 60)}min). "
                        "Running recovery checks...")
                elif elapsed > 120:
                    self._telegram.send(
                        f"[WATCHDOG] Recovered from crash/hang "
                        f"(down for {int(elapsed)}s)")
        except Exception:
            pass

        # Pre-flight checks
        errors = self.run_preflight_checks()
        if errors:
            for e in errors:
                logger.error(f"Pre-flight: {e}")
            fatal = [e for e in errors if ".env" in e or ".venv" in e]
            if fatal:
                self._telegram.send(
                    "[WATCHDOG] Pre-flight FAILED:\n" +
                    "\n".join(fatal))
                return

        # Kill any existing zombie processes
        self._event_router.kill_zombie_processes("crypto_system")

        # Start bot
        self.start_bot()

        # Start log monitor
        self._log_monitor = LogMonitor(self._log_path, self._on_log_line)
        self._log_monitor.start()

        # Start self-check thread
        self_check = Thread(target=self._run_self_check, daemon=True)
        self_check.start()

        # Initialize command handler
        from watchdog_commands import WatchdogCommands
        from dotenv import dotenv_values
        env = dotenv_values(os.path.join(self._base_dir, ".env"))
        db_path = os.path.join(self._base_dir, "crypto_beast.db")
        self._commands = WatchdogCommands(
            telegram=self._telegram,
            state=self._state,
            db_path=db_path,
            env=env,
        )

        # Start Telegram polling thread
        telegram_thread = Thread(target=self._poll_telegram, daemon=True)
        telegram_thread.start()

        self._state.update(watchdog_pid=os.getpid(), status="running")
        self._telegram.send(
            f"[WATCHDOG] Started (mode={self._mode}, "
            f"PID={os.getpid()}, bot PID={self._bot_process.pid})")

        # Main heartbeat loop
        while not self._shutting_down.is_set():
            try:
                self.run_heartbeat()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            self._shutting_down.wait(self._heartbeat_interval)

        # Shutdown
        logger.info("Watchdog shutting down...")
        if self._log_monitor:
            self._log_monitor.stop()
        self.stop_bot()
        self._state.update(status="stopped")
        self._telegram.send("[WATCHDOG] Stopped")
        logger.info("Watchdog stopped")


def main():
    parser = argparse.ArgumentParser(description="Crypto Beast Watchdog")
    parser.add_argument("mode", nargs="?", default="paper",
                        choices=["live", "paper"],
                        help="Trading mode (default: paper)")
    parser.add_argument("--base-dir", default=None,
                        help="Base directory (default: script directory)")
    args = parser.parse_args()

    daemon = WatchdogDaemon(mode=args.mode, base_dir=args.base_dir)
    daemon.run()


if __name__ == "__main__":
    main()
