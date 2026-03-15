"""Notification system: Telegram + macOS native notifications."""
import subprocess
from datetime import datetime
from typing import Optional, List
from loguru import logger


class Notifier:
    """Send notifications via Telegram and macOS."""

    def __init__(self, telegram_token: str = "", telegram_chat_id: str = ""):
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self._history: List[dict] = []

    def send(self, title: str, message: str, level: str = "info") -> bool:
        """Send a notification. Always logs + macOS, optionally Telegram."""
        logger.info(f"[{level.upper()}] {title}: {message}")

        # Record
        self._history.append({
            "title": title, "message": message,
            "level": level, "timestamp": datetime.utcnow()
        })

        # macOS notification
        self._send_macos(title, message)

        # Telegram (only if configured and level is warning/critical)
        if self.telegram_token and self.telegram_chat_id and level in ("warning", "critical"):
            return self._send_telegram(title, message)

        return True

    def _send_macos(self, title: str, message: str) -> None:
        """Send macOS notification via osascript."""
        try:
            script = f'display notification "{message}" with title "Crypto Beast" subtitle "{title}"'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
        except Exception as e:
            logger.debug(f"macOS notification failed: {e}")

    def _send_telegram(self, title: str, message: str) -> bool:
        """Send Telegram message (sync, for simplicity)."""
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            text = f"*{title}*\n{message}"
            resp = requests.post(url, json={
                "chat_id": self.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def format_trade_notification(self, trade: dict) -> str:
        """Format a trade for notification."""
        side = trade.get("side", "?")
        symbol = trade.get("symbol", "?")
        price = trade.get("entry_price", 0)
        pnl = trade.get("pnl")

        if pnl is not None:
            return f"{side} {symbol} @ {price:.2f} | PnL: {pnl:+.2f}"
        return f"{side} {symbol} @ {price:.2f}"

    def format_daily_summary(self, trades: List[dict], equity: float) -> str:
        """Format daily summary."""
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl", 0) <= 0)
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        return f"Trades: {len(trades)} | W/L: {wins}/{losses} | PnL: {total_pnl:+.2f} | Equity: {equity:.2f}"

    def get_history(self) -> List[dict]:
        return self._history.copy()
