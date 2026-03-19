#!/usr/bin/env python3
"""Crypto Beast Watchdog Daemon — monitors and auto-restarts the trading bot."""
import argparse
import json
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

        # Claude integration
        self._claude_lock = False
        self._claude_lock_time: Optional[float] = None
        self._last_daily_review: Optional[str] = None
        self._last_weekly_review: Optional[str] = None
        self._last_monthly_review: Optional[str] = None

    # === DB Recording ===

    def _record_intervention(self, level: str, event: str, action: str,
                              outcome: str, claude_used: bool = False,
                              duration: int = 0) -> None:
        """Record an intervention to the watchdog_interventions DB table."""
        try:
            import sqlite3
            db_path = os.path.join(self._base_dir, "crypto_beast.db")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO watchdog_interventions (timestamp, level, event, action, outcome, claude_used, duration_seconds) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), level, event[:500], action[:200], outcome, int(claude_used), duration)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to record intervention: {e}")

    def _ensure_initial_version(self) -> None:
        """Create v1.0 strategy version if none exists."""
        try:
            import sqlite3
            db_path = os.path.join(self._base_dir, "crypto_beast.db")
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM strategy_versions").fetchone()[0]
            if count == 0:
                conn.execute(
                    "INSERT INTO strategy_versions (version, date, description, source) VALUES (?, ?, ?, ?)",
                    ("v1.0", datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                     "Initial release — 6 strategies, Binance USDT-M Futures", "manual")
                )
                conn.commit()
                logger.info("Created initial strategy version v1.0")
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to ensure initial version: {e}")

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
        if self._shutting_down.is_set():
            logger.info("Watchdog shutting down, skipping restart")
            return
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
        self._record_intervention("L1", reason, "restart", "bot_restarted")

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
            # Extract error key: strip timestamp/level prefix, take first 80 chars of message
            import re as _re
            msg = _re.sub(r'^\d{2}:\d{2}:\d{2}\s*\|\s*\w+\s*\|\s*', '', line[-200:])
            error_key = msg[:80]
            if self._event_router.should_escalate_l2(error_key):
                logger.warning(f"L2 event detected: {line[-200:]}")
                self._telegram.send(f"[L2] 检测到未知错误，正在调用Claude分析...")
                self._state.add_event("L2", line[-200:])
                Thread(
                    target=self.escalate_to_claude,
                    args=(f"Error detected in log:\n{line[-200:]}\n\nFull recent log context needed.",),
                    daemon=True,
                ).start()
            else:
                logger.debug(f"L2 event suppressed (cooldown): {line[-100:]}")

    # === Claude Integration ===

    def escalate_to_claude(self, error_context: str) -> bool:
        """Escalate an error to Claude Code for analysis and fix."""
        if self._shutting_down.is_set():
            return False
        import time as _time

        # Check daily budget
        state = self._state.read()
        if state.get("claude_calls_today", 0) >= 3:
            logger.warning("Claude daily budget exceeded, skipping escalation")
            return False

        # Check concurrency lock
        if self._claude_lock:
            if self._claude_lock_time and (_time.time() - self._claude_lock_time) < 900:
                logger.info("Claude session already active, skipping")
                return False
            # Stale lock, release
            self._claude_lock = False

        # Write error context
        context_file = "/tmp/crypto_beast_error_context.txt"
        with open(context_file, "w") as f:
            f.write(error_context)

        # Acquire lock
        self._claude_lock = True
        self._claude_lock_time = _time.time()

        try:
            script = os.path.join(self._base_dir, "scripts", "emergency-fix.sh")
            result = subprocess.run(
                ["bash", script],
                cwd=self._base_dir,
                capture_output=True, text=True,
                timeout=600,  # 10 minutes (claude needs time for analysis + fix + pytest)
            )
            success = result.returncode == 0
            self._state.update(claude_calls_today=state["claude_calls_today"] + 1)

            duration = int(time.time() - self._claude_lock_time) if self._claude_lock_time else 0

            # Read Claude's fix summary for Telegram
            fix_summary = ""
            try:
                fix_log = "/tmp/claude_fix_output.log"
                if os.path.exists(fix_log):
                    with open(fix_log) as f:
                        content = f.read().strip()
                    # Take last 500 chars as summary (Claude puts summary at end)
                    fix_summary = content[-500:] if len(content) > 500 else content
            except Exception:
                pass

            if success:
                msg = f"[L2] Claude修复成功({duration}s)，正在重启Bot"
                if fix_summary:
                    msg += f"\n\n修复详情:\n{fix_summary[:800]}"
                self._telegram.send(msg)
                self._record_intervention("L2", error_context[:500], "claude_fix", "success", claude_used=True, duration=duration)
                self.restart_bot("L2 Claude fix applied")
            else:
                msg = f"[L2-TERMINAL] Claude修复失败({duration}s)，需要人工介入"
                if fix_summary:
                    msg += f"\n\n详情:\n{fix_summary[:800]}"
                self._telegram.send(msg)
                self._state.update(status="L2-TERMINAL")
                self._record_intervention("L2", error_context[:500], "claude_fix", "failed", claude_used=True, duration=duration)

            return success
        except subprocess.TimeoutExpired:
            self._telegram.send("[L2] Claude修复超时(5min)，需要人工介入")
            self._state.update(status="L2-TERMINAL")
            return False
        except Exception as e:
            logger.error(f"Claude escalation failed: {e}")
            return False
        finally:
            self._claude_lock = False
            self._claude_lock_time = None

    def run_review(self, review_type: str) -> bool:
        """Run a Claude review (daily/weekly/monthly)."""
        if self._claude_lock:
            logger.info("Claude session active, skipping review")
            return False

        self._claude_lock = True
        self._claude_lock_time = time.time()

        try:
            script = os.path.join(self._base_dir, "scripts", f"{review_type}-review.sh")
            if not os.path.exists(script):
                logger.warning(f"Review script not found: {script}")
                return False

            self._telegram.send(f"[L3] 开始{review_type}复盘...")
            result = subprocess.run(
                ["bash", script],
                cwd=self._base_dir,
                capture_output=True, text=True,
                timeout=600,  # 10 minutes
            )
            # Send Telegram summary FIRST (with retries for network timeout)
            summary_file = os.path.join(self._base_dir, "review_data", "telegram_summary.txt")
            try:
                if os.path.exists(summary_file):
                    with open(summary_file) as f:
                        summary = f.read().strip()
                    if summary:
                        sent = False
                        for attempt in range(3):
                            try:
                                self._telegram.send(f"[L3] {review_type}复盘完成:\n{summary}")
                                sent = True
                                break
                            except Exception:
                                import time as _time
                                _time.sleep(10)  # Wait 10s before retry
                        if not sent:
                            logger.error(f"Failed to send review summary after 3 attempts")
                    os.remove(summary_file)
                else:
                    self._telegram.send(f"[L3] {review_type}复盘完成")
            except Exception as e:
                logger.error(f"Failed to send review summary: {e}")

            try:
                state = self._state.read()
                self._state.update(claude_calls_today=state.get("claude_calls_today", 0) + 1)
            except Exception as e:
                logger.error(f"Failed to update claude call counter: {e}")

            duration = int(time.time() - self._claude_lock_time) if self._claude_lock_time else 0
            success = result.returncode == 0
            self._record_intervention(
                "L3", f"{review_type} review", "review",
                "success" if success else "failed",
                claude_used=True, duration=duration,
            )
            return success
        except subprocess.TimeoutExpired:
            self._telegram.send(f"[L3] {review_type}复盘超时")
            return False
        except Exception as e:
            logger.error(f"Review failed: {e}")
            return False
        finally:
            self._claude_lock = False
            self._claude_lock_time = None

    def _apply_approved_changes(self) -> None:
        """Apply approved changes via Claude."""
        approved_file = os.path.join(self._base_dir, "review_data", "approved_changes.json")
        if not os.path.exists(approved_file):
            self._telegram.send("[CMD] 未找到已批准的变更文件")
            return

        if self._claude_lock:
            self._telegram.send("[CMD] Claude正忙，请稍后再试")
            return

        self._claude_lock = True
        self._claude_lock_time = time.time()
        try:
            with open(approved_file) as f:
                changes = json.load(f)

            # Write a Claude prompt for applying changes
            prompt = (
                f"Apply these approved parameter changes to Crypto Beast:\n\n"
                f"{json.dumps(changes, indent=2)}\n\n"
                f"1. Read config.py\n"
                f"2. Apply each change\n"
                f"3. Run python -m pytest -q\n"
                f"4. If tests pass, commit with '[approved] <description>'\n"
                f"5. If tests fail, git checkout . and report failure\n"
                f"NEVER modify .env, watchdog.py, or watchdog_state.py"
            )

            result = subprocess.run(
                ["claude", "-p", prompt, "--allowedTools", "Read,Bash,Edit,Write,Glob,Grep"],
                cwd=self._base_dir,
                capture_output=True, text=True,
                timeout=300,
            )

            if result.returncode == 0:
                self._telegram.send("[CMD] 变更已应用，正在重启Bot")
                self.restart_bot("Approved changes applied")
                os.remove(approved_file)
            else:
                self._telegram.send("[CMD] 变更应用失败，已回滚")
        except Exception as e:
            self._telegram.send(f"[CMD] 应用变更出错: {e}")
        finally:
            self._claude_lock = False
            self._claude_lock_time = None

    def _run_rollback(self) -> None:
        """Execute a strategy rollback via Claude."""
        rollback_file = os.path.join(self._base_dir, "review_data", "rollback_target.json")
        if not os.path.exists(rollback_file):
            self._telegram.send("[CMD] 未找到回滚目标")
            return

        if self._claude_lock:
            self._telegram.send("[CMD] Claude正忙，请稍后再试")
            return

        self._claude_lock = True
        self._claude_lock_time = time.time()
        try:
            with open(rollback_file) as f:
                target = json.load(f)

            prompt = (
                f"Rollback Crypto Beast strategy from {target['from_version']} to {target['to_version']}.\n\n"
                f"Config snapshot to restore:\n{target.get('config_snapshot', 'N/A')}\n\n"
                f"1. Read current config.py\n"
                f"2. Restore the parameters from the snapshot\n"
                f"3. Run python -m pytest -q\n"
                f"4. If tests pass, commit with '[rollback] {target['from_version']} -> {target['to_version']}'\n"
                f"5. Insert new strategy_version record\n"
                f"NEVER modify .env, watchdog.py, or watchdog_state.py"
            )

            result = subprocess.run(
                ["claude", "-p", prompt, "--allowedTools", "Read,Bash,Edit,Write,Glob,Grep"],
                cwd=self._base_dir,
                capture_output=True, text=True,
                timeout=300,
            )

            if result.returncode == 0:
                self._telegram.send(f"[CMD] 已回滚到 {target['to_version']}，正在重启Bot")
                self.restart_bot(f"Rollback to {target['to_version']}")
                os.remove(rollback_file)
            else:
                self._telegram.send("[CMD] 回滚失败")
        except Exception as e:
            self._telegram.send(f"[CMD] 回滚出错: {e}")
        finally:
            self._claude_lock = False
            self._claude_lock_time = None

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

        # Check review schedule
        if now.hour == 0 and 30 <= now.minute <= 35:
            today_str = now.strftime("%Y-%m-%d")
            if self._last_daily_review != today_str:
                self._last_daily_review = today_str
                Thread(target=self.run_review, args=("daily",), daemon=True).start()

        # Weekly: Monday 00:45 UTC
        if now.weekday() == 0 and now.hour == 0 and 45 <= now.minute <= 50:
            week_str = now.strftime("%Y-W%V")
            if self._last_weekly_review != week_str:
                self._last_weekly_review = week_str
                Thread(target=self.run_review, args=("weekly",), daemon=True).start()

        # Monthly: 1st of month 01:00 UTC
        if now.day == 1 and now.hour == 1 and 0 <= now.minute <= 5:
            month_str = now.strftime("%Y-%m")
            if self._last_monthly_review != month_str:
                self._last_monthly_review = month_str
                Thread(target=self.run_review, args=("monthly",), daemon=True).start()

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

        elif action == "APPLY_APPROVED":
            logger.info("Applying approved changes via Claude")
            Thread(target=self._apply_approved_changes, daemon=True).start()

        elif action == "REVIEW":
            logger.info("Ad-hoc review triggered")
            Thread(target=self.run_review, args=("daily",), daemon=True).start()

        elif action == "ROLLBACK":
            logger.info("Rollback triggered")
            Thread(target=self._run_rollback, daemon=True).start()

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

        os.makedirs(os.path.join(self._base_dir, "logs", "reviews"), exist_ok=True)

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

        # Ensure initial strategy version exists
        self._ensure_initial_version()

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
