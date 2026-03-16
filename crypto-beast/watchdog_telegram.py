"""Lightweight Telegram sender for watchdog notifications."""
import requests
from loguru import logger


class WatchdogTelegram:
    """Send Telegram messages without async dependencies."""

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        self._last_update_id = 0

    def send(self, text: str) -> bool:
        """Send message. Tries Markdown first, falls back to plain text."""
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=10)
            if resp.status_code == 200:
                return True
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    def poll(self) -> list:
        """Fetch new Telegram updates. Returns list of (command, args) tuples."""
        if not self.enabled:
            return []
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        try:
            resp = requests.get(url, params={
                "offset": self._last_update_id + 1,
                "timeout": 2,
            }, timeout=5)
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for update in data.get("result", []):
                self._last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "").strip()
                chat_id = str(message.get("chat", {}).get("id", ""))
                if chat_id != self.chat_id:
                    continue
                if not text.startswith("/"):
                    continue
                parts = text.split()
                command = parts[0].lower().split("@")[0]
                args = parts[1:] if len(parts) > 1 else []
                results.append((command, args))
            return results
        except Exception as e:
            logger.debug(f"Telegram poll error: {e}")
            return []
