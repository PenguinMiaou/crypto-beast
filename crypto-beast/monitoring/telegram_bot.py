"""Telegram bot with interactive commands for monitoring and control."""
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List

import aiohttp
from loguru import logger


class TelegramBot:
    """Interactive Telegram bot for Crypto Beast monitoring and control."""

    def __init__(self, token: str, chat_id: str, db=None, exchange=None, bot_state: Optional[Dict] = None):
        self.token = token
        self.chat_id = chat_id
        self.db = db
        self.exchange = exchange
        self._bot_state = bot_state or {}  # Shared state dict with main loop
        self._last_update_id = 0
        self._running = False
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    async def start_polling(self) -> None:
        """Start polling for Telegram updates in background."""
        if not self.token or not self.chat_id:
            logger.info("Telegram bot not configured, skipping")
            return

        self._running = True
        logger.info("Telegram bot polling started")

        while self._running:
            try:
                updates = await self._get_updates()
                for update in updates:
                    await self._handle_update(update)
            except Exception as e:
                logger.debug(f"Telegram poll error: {e}")
            await asyncio.sleep(2)

    async def stop(self) -> None:
        self._running = False

    async def _get_updates(self) -> list:
        """Fetch new messages from Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = {"offset": self._last_update_id + 1, "timeout": 5}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                updates = data.get("result", [])
                if updates:
                    self._last_update_id = updates[-1]["update_id"]
                return updates

    async def _handle_update(self, update: dict) -> None:
        """Process a single update."""
        message = update.get("message", {})
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Only respond to authorized chat
        if chat_id != self.chat_id:
            return

        if not text.startswith("/"):
            return

        parts = text.split()
        command = parts[0].lower().split("@")[0]  # Handle /command@botname
        args = parts[1:] if len(parts) > 1 else []

        handlers = {
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/positions": self._cmd_positions,
            "/pnl": self._cmd_pnl,
            "/balance": self._cmd_balance,
            "/trades": self._cmd_trades,
            "/close": self._cmd_close,
            "/closeall": self._cmd_closeall,
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
            "/health": self._cmd_health,
        }

        handler = handlers.get(command)
        if handler:
            try:
                await handler(args)
            except Exception as e:
                await self._reply(f"Error: {e}")
        else:
            await self._reply(f"Unknown command: {command}\nType /help for available commands")

    async def _reply(self, text: str) -> None:
        """Send reply to Telegram."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            # Try Markdown first, fall back to plain text if formatting fails
            resp = await session.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }, timeout=aiohttp.ClientTimeout(total=10))
            if resp.status != 200:
                # Markdown failed (likely special chars like $), send as plain text
                await session.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                }, timeout=aiohttp.ClientTimeout(total=10))

    # === Command Handlers ===

    async def _cmd_help(self, args: list) -> None:
        await self._reply(
            "*Crypto Beast v1.0 Commands*\n\n"
            "/status — System overview (equity, positions, uptime)\n"
            "/positions — Detailed open positions with PnL\n"
            "/pnl — Today's profit & loss\n"
            "/balance — Wallet balance from Binance\n"
            "/trades — Recent trade history (last 10)\n"
            "/close SYMBOL — Close position (e.g. /close BTCUSDT)\n"
            "/closeall — Emergency close ALL positions\n"
            "/pause — Pause opening new trades\n"
            "/resume — Resume trading\n"
            "/health — System health & module status\n"
            "/help — Show this help"
        )

    async def _cmd_status(self, args: list) -> None:
        """System overview."""
        lines = ["*System Status*\n"]

        # Mode
        paused_str = " (PAUSED)" if self._paused else ""
        mode = self._bot_state.get("mode", "LIVE")
        lines.append(f"Mode: {mode}{paused_str}")

        # Equity from DB
        if self.db:
            try:
                closed_pnl = self.db.execute(
                    "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
                ).fetchone()[0]
                starting = self._bot_state.get("starting_capital", 100)
                equity = starting + closed_pnl
                lines.append(f"Equity: ${equity:.2f} USDT")
                lines.append(f"Closed PnL: ${closed_pnl:+.2f}")
            except Exception:
                pass

            # Open positions count
            try:
                open_count = self.db.execute(
                    "SELECT COUNT(*) FROM trades WHERE status = 'OPEN'"
                ).fetchone()[0]
                lines.append(f"Open Positions: {open_count}")
            except Exception:
                pass

        # Uptime
        start_time = self._bot_state.get("start_time")
        if start_time:
            uptime = datetime.now(timezone.utc) - start_time
            hours = int(uptime.total_seconds() // 3600)
            minutes = int((uptime.total_seconds() % 3600) // 60)
            lines.append(f"Uptime: {hours}h {minutes}m")

        await self._reply("\n".join(lines))

    async def _cmd_positions(self, args: list) -> None:
        """Detailed positions."""
        if not self.db:
            await self._reply("DB not available")
            return

        rows = self.db.execute(
            "SELECT symbol, side, entry_price, quantity, leverage, strategy, stop_loss, take_profit "
            "FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        if not rows:
            await self._reply("No open positions")
            return

        lines = ["*Open Positions*\n"]
        for r in rows:
            symbol, side, entry, qty, lev, strategy, sl, tp = r
            sl_str = f"${sl:,.2f}" if sl else "N/A"
            tp_str = f"${tp:,.2f}" if tp else "N/A"
            lines.append(
                f"{'🟢' if side=='LONG' else '🔴'} {side} {symbol}\n"
                f"  Entry: ${entry:,.2f} | Qty: {qty} | {lev}x\n"
                f"  SL: {sl_str} | TP: {tp_str}\n"
                f"  Strategy: {strategy}"
            )

        await self._reply("\n".join(lines))

    async def _cmd_pnl(self, args: list) -> None:
        """Today's PnL."""
        if not self.db:
            await self._reply("DB not available")
            return

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self.db.execute(
            "SELECT symbol, side, pnl, strategy FROM trades WHERE status = 'CLOSED' AND exit_time >= ?",
            (today,)
        ).fetchall()

        if not rows:
            await self._reply(f"*Today's PnL*\n\nNo closed trades today ({today})")
            return

        total_pnl = sum(r[2] for r in rows if r[2])
        wins = sum(1 for r in rows if r[2] and r[2] > 0)
        losses = len(rows) - wins

        lines = [f"*Today's PnL ({today})*\n"]
        lines.append(f"Total: ${total_pnl:+.2f}")
        lines.append(f"Trades: {len(rows)} | W: {wins} | L: {losses}")
        lines.append("")
        for r in rows:
            pnl_str = f"${r[2]:+.2f}" if r[2] else "$0"
            lines.append(f"  {r[1]} {r[0]} | {pnl_str} | {r[3]}")

        await self._reply("\n".join(lines))

    async def _cmd_balance(self, args: list) -> None:
        """Live balance from Binance."""
        if not self.exchange:
            await self._reply("Exchange not available")
            return

        try:
            account = await self.exchange.fapiPrivateV2GetAccount()
            wallet = float(account.get("totalWalletBalance", 0))
            available = float(account.get("availableBalance", 0))
            unrealized = float(account.get("totalUnrealizedProfit", 0))

            await self._reply(
                f"*Binance Balance*\n\n"
                f"Wallet: ${wallet:.2f}\n"
                f"Available: ${available:.2f}\n"
                f"Unrealized PnL: ${unrealized:+.2f}\n"
                f"Total: ${wallet + unrealized:.2f}"
            )
        except Exception as e:
            await self._reply(f"Failed to fetch balance: {e}")

    async def _cmd_trades(self, args: list) -> None:
        """Recent trades."""
        if not self.db:
            await self._reply("DB not available")
            return

        limit = int(args[0]) if args else 10
        rows = self.db.execute(
            "SELECT symbol, side, entry_price, exit_price, pnl, strategy, status, entry_time "
            "FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,)
        ).fetchall()

        if not rows:
            await self._reply("No trades yet")
            return

        lines = [f"*Last {len(rows)} Trades*\n"]
        for r in rows:
            symbol, side, entry, exit_p, pnl, strategy, status, time = r
            pnl_str = f"${pnl:+.2f}" if pnl else ""
            exit_str = f"-> ${exit_p:,.2f}" if exit_p else ""
            icon = "🟢" if side == "LONG" else "🔴"
            if status == "CLOSED" and pnl and pnl > 0:
                status_icon = "✅"
            elif status == "CLOSED":
                status_icon = "❌"
            else:
                status_icon = "⏳"
            lines.append(f"{status_icon}{icon} {side} {symbol} ${entry:,.2f} {exit_str} {pnl_str} | {strategy}")

        await self._reply("\n".join(lines))

    async def _cmd_close(self, args: list) -> None:
        """Close a specific symbol position."""
        if not args:
            await self._reply("Usage: /close BTCUSDT")
            return

        symbol = args[0].upper()
        if not self.exchange:
            await self._reply("Exchange not available")
            return

        # Find position in DB
        row = self.db.execute(
            "SELECT id, side, quantity FROM trades WHERE symbol = ? AND status = 'OPEN'",
            (symbol,)
        ).fetchone()

        if not row:
            await self._reply(f"No open position for {symbol}")
            return

        trade_id, side, quantity = row
        close_side = "SELL" if side == "LONG" else "BUY"
        position_side = "LONG" if side == "LONG" else "SHORT"

        try:
            result = await self.exchange.fapiPrivatePostOrder({
                "symbol": symbol,
                "side": close_side,
                "positionSide": position_side,
                "type": "MARKET",
                "quantity": str(quantity),
            })

            fill_price = float(result.get("avgPrice", 0))
            entry_price = float(self.db.execute(
                "SELECT entry_price FROM trades WHERE id=?", (trade_id,)
            ).fetchone()[0])
            if side == "LONG":
                pnl = (fill_price - entry_price) * quantity
            else:
                pnl = (entry_price - fill_price) * quantity

            self.db.execute(
                "UPDATE trades SET exit_price=?, exit_time=?, pnl=?, status='CLOSED' WHERE id=?",
                (fill_price, datetime.now(timezone.utc).isoformat(), round(pnl, 4), trade_id)
            )

            await self._reply(f"*Closed {side} {symbol}*\nExit: ${fill_price:,.2f}\nPnL: ${pnl:+.4f}")
        except Exception as e:
            await self._reply(f"Close failed: {e}")

    async def _cmd_closeall(self, args: list) -> None:
        """Emergency close all positions."""
        if not self.exchange or not self.db:
            await self._reply("Exchange/DB not available")
            return

        rows = self.db.execute(
            "SELECT id, symbol, side, quantity FROM trades WHERE status = 'OPEN'"
        ).fetchall()

        if not rows:
            await self._reply("No open positions to close")
            return

        await self._reply(f"Closing {len(rows)} positions...")

        closed = 0
        for trade_id, symbol, side, quantity in rows:
            try:
                close_side = "SELL" if side == "LONG" else "BUY"
                position_side = side
                result = await self.exchange.fapiPrivatePostOrder({
                    "symbol": symbol,
                    "side": close_side,
                    "positionSide": position_side,
                    "type": "MARKET",
                    "quantity": str(quantity),
                })

                fill_price = float(result.get("avgPrice", 0))
                entry_price = float(self.db.execute(
                    "SELECT entry_price FROM trades WHERE id=?", (trade_id,)
                ).fetchone()[0])
                if side == "LONG":
                    pnl = (fill_price - entry_price) * quantity
                else:
                    pnl = (entry_price - fill_price) * quantity

                self.db.execute(
                    "UPDATE trades SET exit_price=?, exit_time=?, pnl=?, status='CLOSED' WHERE id=?",
                    (fill_price, datetime.now(timezone.utc).isoformat(), round(pnl, 4), trade_id)
                )
                closed += 1
            except Exception as e:
                await self._reply(f"Failed to close {symbol}: {e}")

        await self._reply(f"*Closed {closed}/{len(rows)} positions*")

    async def _cmd_pause(self, args: list) -> None:
        """Pause new trade opening."""
        self._paused = True
        await self._reply("*Trading PAUSED*\nBot will monitor existing positions but won't open new ones.\nUse /resume to continue.")

    async def _cmd_resume(self, args: list) -> None:
        """Resume trading."""
        self._paused = False
        await self._reply("*Trading RESUMED*\nBot will now open new positions on signals.")

    async def _cmd_health(self, args: list) -> None:
        """System health info."""
        lines = ["*System Health*\n"]

        # DB check
        if self.db:
            try:
                self.db.execute("SELECT 1").fetchone()
                lines.append("Database: OK")
            except Exception:
                lines.append("Database: ERROR")
        else:
            lines.append("Database: N/A")

        # Exchange check
        if self.exchange:
            try:
                ticker = await self.exchange.fetch_ticker("BTC/USDT")
                lines.append(f"Exchange: OK (BTC=${ticker['last']:,.2f})")
            except Exception as e:
                lines.append(f"Exchange: ERROR ({e})")
        else:
            lines.append("Exchange: N/A")

        # Trade stats
        if self.db:
            try:
                total = self.db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
                open_t = self.db.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
                closed_t = self.db.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'").fetchone()[0]
                lines.append(f"\nTrades: {total} total | {open_t} open | {closed_t} closed")
            except Exception:
                pass

        # Paused state
        lines.append(f"\nTrading: {'PAUSED' if self._paused else 'ACTIVE'}")

        await self._reply("\n".join(lines))
