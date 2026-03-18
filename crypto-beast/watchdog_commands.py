"""Telegram command handlers for watchdog."""
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from loguru import logger


class WatchdogCommands:
    """Handle Telegram commands in the watchdog context."""

    def __init__(self, telegram, state, db_path: str, env: Dict[str, str]):
        self._telegram = telegram
        self._state = state
        self._db_path = db_path
        self._api_key = env.get("BINANCE_API_KEY", "")
        self._api_secret = env.get("BINANCE_API_SECRET", "")
        self._confirm_pending: Optional[str] = None
        self._confirm_time: Optional[float] = None

    def _query_db(self, query: str, params: tuple = ()) -> List:
        """Execute a read-only DB query."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            result = conn.execute(query, params).fetchall()
            conn.close()
            return result
        except Exception as e:
            logger.error(f"DB query failed: {e}")
            return []

    def handle(self, command: str, args: List[str]) -> None:
        """Route a command to its handler."""
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
            "/watchdog": self._cmd_watchdog,
            "/stopall": self._cmd_stopall,
            "/confirm": self._cmd_confirm,
            "/restart": self._cmd_restart,
            "/review": self._cmd_review,
            "/approve": self._cmd_approve,
            "/reject": self._cmd_reject,
            "/rollback": self._cmd_rollback,
            "/directive": self._cmd_directive,
            "/directives": self._cmd_directives,
            "/deldirective": self._cmd_deldirective,
            "/cost": self._cmd_cost,
            "/version": self._cmd_version,
        }
        handler = handlers.get(command)
        if handler:
            try:
                handler(args)
            except Exception as e:
                self._telegram.send(f"Error: {e}")
        else:
            self._telegram.send(f"Unknown: {command}\nType /help for commands")

    def _cmd_help(self, args: List[str]) -> None:
        self._telegram.send(
            "*Crypto Beast v1.0*\n\n"
            "/status — 系统概览\n"
            "/positions — 持仓详情\n"
            "/pnl — 今日盈亏\n"
            "/balance — 钱包余额\n"
            "/trades — 最近交易\n"
            "/close SYMBOL — 平仓\n"
            "/closeall — 全部平仓\n"
            "/pause — 暂停开单\n"
            "/resume — 恢复交易\n"
            "/health — 系统健康\n"
            "/watchdog — 守护进程状态\n"
            "/stopall — 停止一切\n"
            "/restart — 重启Bot\n"
            "/review — 触发复盘\n"
            "/approve — 批准建议\n"
            "/reject — 拒绝建议\n"
            "/rollback — 回滚版本\n"
            "/directive — 设置策略方向\n"
            "/directives — 查看指令\n"
            "/cost — Token消耗\n"
            "/version — 策略版本"
        )

    def _cmd_status(self, args: List[str]) -> None:
        lines = ["*系统状态*\n"]
        state = self._state.read()
        lines.append(f"模式: {'PAUSED' if state.get('paused') else 'RUNNING'}")
        lines.append(f"状态: {state.get('status', '?')}")

        # Equity from DB
        rows = self._query_db(
            "SELECT COALESCE(SUM(pnl), 0) as total_pnl FROM trades WHERE status = 'CLOSED'"
        )
        if rows:
            closed_pnl = float(rows[0]["total_pnl"])
            lines.append(f"已平仓盈亏: ${closed_pnl:+.2f}")

        # Open positions
        rows = self._query_db("SELECT COUNT(*) as cnt FROM trades WHERE status = 'OPEN'")
        if rows:
            lines.append(f"持仓数: {rows[0]['cnt']}")

        # Uptime
        uptime = state.get("uptime_seconds", 0)
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        lines.append(f"运行时间: {hours}h {minutes}m")
        lines.append(f"今日重启: {state.get('restarts_today', 0)}")

        self._telegram.send("\n".join(lines))

    def _cmd_positions(self, args: List[str]) -> None:
        rows = self._query_db(
            "SELECT symbol, side, entry_price, quantity, leverage, strategy, stop_loss, take_profit "
            "FROM trades WHERE status = 'OPEN'"
        )
        if not rows:
            self._telegram.send("无持仓")
            return
        lines = ["*持仓详情*\n"]
        for r in rows:
            sl = f"${r['stop_loss']:,.2f}" if r["stop_loss"] else "N/A"
            tp = f"${r['take_profit']:,.2f}" if r["take_profit"] else "N/A"
            lines.append(
                f"{'🟢' if r['side']=='LONG' else '🔴'} {r['side']} {r['symbol']}\n"
                f"  入场: ${r['entry_price']:,.2f} | 数量: {r['quantity']} | {r['leverage']}x\n"
                f"  SL: {sl} | TP: {tp}\n"
                f"  策略: {r['strategy']}"
            )
        self._telegram.send("\n".join(lines))

    def _cmd_pnl(self, args: List[str]) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows = self._query_db(
            "SELECT symbol, side, pnl, strategy FROM trades WHERE status = 'CLOSED' AND exit_time >= ?",
            (today,)
        )
        if not rows:
            self._telegram.send(f"*今日盈亏*\n\n今天无平仓 ({today})")
            return
        total_pnl = sum(float(r["pnl"]) for r in rows if r["pnl"])
        wins = sum(1 for r in rows if r["pnl"] and float(r["pnl"]) > 0)
        losses = len(rows) - wins
        lines = [f"*今日盈亏 ({today})*\n"]
        lines.append(f"总计: ${total_pnl:+.2f}")
        lines.append(f"交易: {len(rows)} | 胜: {wins} | 负: {losses}")
        for r in rows:
            pnl_str = f"${float(r['pnl']):+.2f}" if r["pnl"] else "$0"
            lines.append(f"  {r['side']} {r['symbol']} | {pnl_str} | {r['strategy']}")
        self._telegram.send("\n".join(lines))

    def _cmd_balance(self, args: List[str]) -> None:
        try:
            import hmac
            import hashlib
            import time as _time
            from urllib.parse import urlencode
            ts = int(_time.time() * 1000)
            params = {"timestamp": ts}
            query = urlencode(params)
            sig = hmac.new(self._api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={sig}"
            resp = requests.get(url, headers={"X-MBX-APIKEY": self._api_key}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                wallet = float(data.get("totalWalletBalance", 0))
                available = float(data.get("availableBalance", 0))
                unrealized = float(data.get("totalUnrealizedProfit", 0))
                self._telegram.send(
                    f"*钱包余额*\n\n"
                    f"钱包: ${wallet:.2f}\n"
                    f"可用: ${available:.2f}\n"
                    f"浮动盈亏: ${unrealized:+.2f}\n"
                    f"总计: ${wallet + unrealized:.2f}"
                )
            else:
                self._telegram.send(f"查询失败: {resp.status_code}")
        except Exception as e:
            self._telegram.send(f"查询失败: {e}")

    def _cmd_trades(self, args: List[str]) -> None:
        limit = int(args[0]) if args else 10
        rows = self._query_db(
            "SELECT symbol, side, entry_price, exit_price, pnl, strategy, status, entry_time "
            "FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,)
        )
        if not rows:
            self._telegram.send("暂无交易记录")
            return
        lines = [f"*最近 {len(rows)} 笔交易*\n"]
        for r in rows:
            pnl_str = f"${float(r['pnl']):+.2f}" if r["pnl"] else ""
            exit_str = f"-> ${float(r['exit_price']):,.2f}" if r["exit_price"] else ""
            icon = "🟢" if r["side"] == "LONG" else "🔴"
            if r["status"] == "CLOSED" and r["pnl"] and float(r["pnl"]) > 0:
                s_icon = "✅"
            elif r["status"] == "CLOSED":
                s_icon = "❌"
            else:
                s_icon = "⏳"
            lines.append(f"{s_icon}{icon} {r['side']} {r['symbol']} ${float(r['entry_price']):,.2f} {exit_str} {pnl_str} | {r['strategy']}")
        self._telegram.send("\n".join(lines))

    def _cmd_close(self, args: List[str]) -> None:
        if not args:
            self._telegram.send("用法: /close BTCUSDT")
            return
        symbol = args[0].upper()
        # Delegate to bot via watchdog.state command
        self._state.update(command={"action": "CLOSE", "args": symbol})
        self._telegram.send(f"已发送平仓指令: {symbol}")

    def _cmd_closeall(self, args: List[str]) -> None:
        self._state.update(command={"action": "CLOSEALL"})
        self._telegram.send("已发送全部平仓指令")

    def _cmd_pause(self, args: List[str]) -> None:
        self._state.update(paused=True)
        self._telegram.send("*交易已暂停*\n现有持仓继续监控，不再开新单\n/resume 恢复")

    def _cmd_resume(self, args: List[str]) -> None:
        self._state.update(paused=False)
        self._telegram.send("*交易已恢复*")

    def _cmd_health(self, args: List[str]) -> None:
        lines = ["*系统健康*\n"]
        # DB check
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("SELECT 1").fetchone()
            lines.append("数据库: OK")
            total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            open_t = conn.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
            closed_t = conn.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'").fetchone()[0]
            lines.append(f"交易: {total} 总计 | {open_t} 持仓 | {closed_t} 已平")
            conn.close()
        except Exception:
            lines.append("数据库: ERROR")

        # Binance ping
        try:
            resp = requests.get("https://fapi.binance.com/fapi/v1/ping", timeout=5)
            lines.append(f"交易所: {'OK' if resp.status_code == 200 else 'ERROR'}")
        except Exception:
            lines.append("交易所: UNREACHABLE")

        state = self._state.read()
        lines.append(f"\n状态: {'PAUSED' if state.get('paused') else 'ACTIVE'}")
        lines.append(f"Bot PID: {state.get('bot_pid', 'N/A')}")
        self._telegram.send("\n".join(lines))

    def _cmd_watchdog(self, args: List[str]) -> None:
        state = self._state.read()
        events = state.get("recent_events", [])
        recent = events[-5:] if events else []
        lines = ["*守护进程状态*\n"]
        lines.append(f"Watchdog PID: {state.get('watchdog_pid', '?')}")
        lines.append(f"Bot PID: {state.get('bot_pid', '?')}")
        lines.append(f"状态: {state.get('status', '?')}")
        lines.append(f"运行: {state.get('uptime_seconds', 0) // 3600}h")
        lines.append(f"今日重启: {state.get('restarts_today', 0)}")
        lines.append(f"Claude调用: {state.get('claude_calls_today', 0)}")
        if recent:
            lines.append("\n*最近事件:*")
            for e in recent:
                lines.append(f"  [{e.get('level')}] {e.get('event', '')[:60]}")
        self._telegram.send("\n".join(lines))

    def _cmd_stopall(self, args: List[str]) -> None:
        import time as _time
        self._confirm_pending = "STOPALL"
        self._confirm_time = _time.time()
        self._telegram.send("确认停止Bot和Watchdog？\n60秒内发送 /confirm 确认")

    def _cmd_confirm(self, args: List[str]) -> None:
        import time as _time
        if not self._confirm_pending or not self._confirm_time:
            self._telegram.send("无待确认操作")
            return
        if _time.time() - self._confirm_time > 60:
            self._confirm_pending = None
            self._telegram.send("确认已超时")
            return
        if self._confirm_pending == "STOPALL":
            self._state.update(command={"action": "STOP"})
            self._telegram.send("已发送停止指令")
        self._confirm_pending = None

    def _cmd_restart(self, args: List[str]) -> None:
        self._state.update(command={"action": "RESTART"})
        self._telegram.send("已发送重启指令")

    def _cmd_review(self, args: List[str]) -> None:
        if args:
            # View past review
            date = args[0]
            review_path = os.path.join(os.path.dirname(self._db_path), "logs", "reviews", f"{date}.md")
            if os.path.exists(review_path):
                with open(review_path) as f:
                    content = f.read()[:500]
                self._telegram.send(f"*复盘 {date}*\n\n{content}...")
            else:
                self._telegram.send(f"未找到 {date} 的复盘报告")
        else:
            # Trigger ad-hoc review
            self._state.update(command={"action": "REVIEW"})
            self._telegram.send("已触发即时复盘，请稍候...")

    def _cmd_approve(self, args: List[str]) -> None:
        """Approve pending parameter changes from daily review."""
        state = self._state.read()
        approvals = state.get("pending_approvals", [])
        if not approvals:
            self._telegram.send("无待批准的建议")
            return

        if args:
            # Approve specific items by number
            try:
                ids = [int(a) for a in args[0].split(",")]
            except ValueError:
                self._telegram.send("用法: /approve 1,2 或 /approve (全部)")
                return
            selected = [a for a in approvals if a.get("id") in ids]
            if not selected:
                self._telegram.send(f"未找到建议 #{args[0]}")
                return
        else:
            selected = approvals

        # Write approved items to a file for Claude to apply
        approved_file = os.path.join(os.path.dirname(self._db_path), "review_data", "approved_changes.json")
        os.makedirs(os.path.dirname(approved_file), exist_ok=True)
        with open(approved_file, "w") as f:
            json.dump(selected, f, indent=2, default=str)

        # Mark as approved in recommendation_history
        try:
            import sqlite3
            conn = sqlite3.connect(self._db_path)
            for item in selected:
                conn.execute(
                    "UPDATE recommendation_history SET approved=1, applied_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), item.get("db_id"))
                )
            conn.commit()
            conn.close()
        except Exception:
            pass

        # Clear approved items from pending
        remaining = [a for a in approvals if a not in selected]
        self._state.update(pending_approvals=remaining)

        # Signal watchdog to apply changes via Claude
        self._state.update(command={"action": "APPLY_APPROVED"})
        self._telegram.send(f"已批准 {len(selected)} 项建议，正在调用Claude执行...")

    def _cmd_reject(self, args: List[str]) -> None:
        """Reject all pending parameter changes."""
        state = self._state.read()
        approvals = state.get("pending_approvals", [])
        if not approvals:
            self._telegram.send("无待批准的建议")
            return
        self._state.update(pending_approvals=[])
        self._telegram.send(f"已拒绝 {len(approvals)} 项建议")

    def _cmd_rollback(self, args: List[str]) -> None:
        """Rollback to previous strategy version."""
        rows = self._query_db(
            "SELECT version, date, config_snapshot FROM strategy_versions ORDER BY date DESC LIMIT 2"
        )
        if len(rows) < 2:
            self._telegram.send("无法回滚：只有一个版本")
            return
        current = rows[0]
        previous = rows[1]
        if not previous["config_snapshot"]:
            self._telegram.send(f"无法回滚到 {previous['version']}：缺少配置快照")
            return
        # Write rollback instruction for Claude
        rollback_file = os.path.join(os.path.dirname(self._db_path), "review_data", "rollback_target.json")
        os.makedirs(os.path.dirname(rollback_file), exist_ok=True)
        with open(rollback_file, "w") as f:
            json.dump({
                "from_version": current["version"],
                "to_version": previous["version"],
                "config_snapshot": previous["config_snapshot"],
            }, f, indent=2)
        self._state.update(command={"action": "ROLLBACK"})
        self._telegram.send(f"正在从 {current['version']} 回滚到 {previous['version']}...")

    def _cmd_directive(self, args: List[str]) -> None:
        if not args:
            self._telegram.send("用法: /directive <战略指导>\n例: /directive 这个月保守一点")
            return
        text = " ".join(args)
        state = self._state.read()
        directives = state.get("directives", [])
        new_id = max([d.get("id", 0) for d in directives], default=0) + 1
        directives.append({
            "id": new_id,
            "text": text,
            "created": datetime.now(timezone.utc).isoformat(),
        })
        self._state.update(directives=directives)
        self._telegram.send(f"已添加指令 #{new_id}: {text}")

    def _cmd_directives(self, args: List[str]) -> None:
        state = self._state.read()
        directives = state.get("directives", [])
        if not directives:
            self._telegram.send("无活跃指令\n/directive <文本> 添加")
            return
        lines = ["*活跃指令*\n"]
        for d in directives:
            lines.append(f"#{d.get('id')} — {d.get('text')}")
        self._telegram.send("\n".join(lines))

    def _cmd_deldirective(self, args: List[str]) -> None:
        if not args:
            self._telegram.send("用法: /deldirective N")
            return
        try:
            del_id = int(args[0])
        except ValueError:
            self._telegram.send("请输入数字ID")
            return
        state = self._state.read()
        directives = state.get("directives", [])
        new_directives = [d for d in directives if d.get("id") != del_id]
        if len(new_directives) == len(directives):
            self._telegram.send(f"未找到指令 #{del_id}")
            return
        self._state.update(directives=new_directives)
        self._telegram.send(f"已删除指令 #{del_id}")

    def _cmd_cost(self, args: List[str]) -> None:
        log_path = os.path.join(os.path.dirname(self._db_path), "logs", "claude_calls.log")
        if not os.path.exists(log_path):
            self._telegram.send("暂无Claude调用记录")
            return
        try:
            with open(log_path) as f:
                lines = f.readlines()
            today_count = sum(1 for l in lines if datetime.now(timezone.utc).strftime("%Y-%m-%d") in l)
            self._telegram.send(
                f"*Claude调用统计*\n\n"
                f"今日: {today_count} 次\n"
                f"总计: {len(lines)} 次\n"
                f"今日剩余预算: {3 - self._state.read().get('claude_calls_today', 0)} 次紧急调用"
            )
        except Exception as e:
            self._telegram.send(f"读取失败: {e}")

    def _cmd_version(self, args: List[str]) -> None:
        rows = self._query_db(
            "SELECT version, date, description, source FROM strategy_versions ORDER BY date DESC LIMIT 5"
        )
        if not rows:
            self._telegram.send("*Crypto Beast v1.0*\n无版本记录")
            return
        lines = ["*策略版本*\n"]
        for r in rows:
            lines.append(f"*{r['version']}* ({r['date']})")
            lines.append(f"  {r['description']}")
            lines.append(f"  来源: {r['source']}")
        self._telegram.send("\n".join(lines))
