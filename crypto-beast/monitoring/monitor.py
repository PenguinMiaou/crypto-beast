"""Streamlit dashboard for Crypto Beast monitoring."""
from datetime import datetime
from typing import Dict, List, Optional


class MonitorData:
    """Data provider for the monitoring dashboard."""

    def __init__(self, db=None):
        self.db = db
        self._system_state: Optional[dict] = None

    def update(self, state: dict) -> None:
        """Update cached system state."""
        self._system_state = state
        self._system_state["last_update"] = datetime.utcnow().isoformat()

    def get_equity_history(self) -> List[dict]:
        """Get equity snapshots from DB."""
        if not self.db:
            return []
        rows = self.db.execute(
            "SELECT timestamp, equity, drawdown_pct FROM equity_snapshots ORDER BY timestamp DESC LIMIT 1000"
        ).fetchall()
        return [{"timestamp": r[0], "equity": r[1], "drawdown_pct": r[2]} for r in rows]

    def get_trade_history(self, limit: int = 100) -> List[dict]:
        """Get recent trades from DB."""
        if not self.db:
            return []
        rows = self.db.execute(
            "SELECT id, symbol, side, entry_price, exit_price, quantity, leverage, pnl, fees, strategy, entry_time, exit_time, status FROM trades ORDER BY entry_time DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{
            "id": r[0], "symbol": r[1], "side": r[2], "entry_price": r[3],
            "exit_price": r[4], "quantity": r[5], "leverage": r[6],
            "pnl": r[7], "fees": r[8], "strategy": r[9],
            "entry_time": r[10], "exit_time": r[11], "status": r[12],
        } for r in rows]

    def get_strategy_performance(self) -> Dict[str, dict]:
        """Get strategy-level performance metrics."""
        if not self.db:
            return {}
        rows = self.db.execute(
            """SELECT strategy, COUNT(*) as trades,
                      SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                      SUM(pnl) as total_pnl,
                      AVG(pnl) as avg_pnl
               FROM trades WHERE status = 'CLOSED' GROUP BY strategy"""
        ).fetchall()
        result = {}
        for r in rows:
            result[r[0]] = {
                "trades": r[1], "wins": r[2],
                "total_pnl": r[3], "avg_pnl": r[4],
                "win_rate": r[2] / r[1] if r[1] > 0 else 0,
            }
        return result

    def get_system_state(self) -> Optional[dict]:
        return self._system_state
