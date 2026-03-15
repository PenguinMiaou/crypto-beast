"""Tests for PositionManager SL/TP monitoring."""
import pytest

from core.database import Database
from execution.position_manager import PositionManager


@pytest.fixture
def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    d.initialize()
    return d


def _insert_trade(db, symbol="BTCUSDT", side="LONG", entry_price=65000.0,
                  quantity=0.01, leverage=5, strategy="trend_follower",
                  stop_loss=None, take_profit=None, status="OPEN"):
    db.execute(
        "INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, fees, status, stop_loss, take_profit) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (symbol, side, entry_price, quantity, leverage, strategy, "2026-01-01", 0.05, status, stop_loss, take_profit)
    )


class TestCheckPositions:

    def test_long_stop_loss_hit(self, db):
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 63500.0)
        result = pm.check_positions()
        assert len(result) == 1
        assert result[0]["reason"] == "STOP_LOSS"
        assert result[0]["exit_price"] == 64000.0

    def test_long_take_profit_hit(self, db):
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 68000.0)
        result = pm.check_positions()
        assert len(result) == 1
        assert result[0]["reason"] == "TAKE_PROFIT"
        assert result[0]["exit_price"] == 67000.0

    def test_short_stop_loss_hit(self, db):
        _insert_trade(db, side="SHORT", entry_price=65000.0,
                      stop_loss=66000.0, take_profit=63000.0)
        pm = PositionManager(db, lambda s: 66500.0)
        result = pm.check_positions()
        assert len(result) == 1
        assert result[0]["reason"] == "STOP_LOSS"
        assert result[0]["exit_price"] == 66000.0

    def test_short_take_profit_hit(self, db):
        _insert_trade(db, side="SHORT", entry_price=65000.0,
                      stop_loss=66000.0, take_profit=63000.0)
        pm = PositionManager(db, lambda s: 62500.0)
        result = pm.check_positions()
        assert len(result) == 1
        assert result[0]["reason"] == "TAKE_PROFIT"
        assert result[0]["exit_price"] == 63000.0

    def test_price_between_sl_tp_no_close(self, db):
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 65500.0)
        result = pm.check_positions()
        assert len(result) == 0

    def test_no_sl_tp_skipped(self, db):
        _insert_trade(db, stop_loss=None, take_profit=None)
        pm = PositionManager(db, lambda s: 63000.0)
        result = pm.check_positions()
        assert len(result) == 0

    def test_pnl_calculation_long_sl(self, db):
        # LONG entry=65000 exit=64000 qty=0.01 lev=5
        # pnl = (64000-65000)*0.01*5 = -50
        # fees = 64000*0.01*0.0004 = 0.256
        # net = -50 - 0.256 = -50.256
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 63000.0)
        result = pm.check_positions()
        assert result[0]["pnl"] == round(-50.0 - 64000.0 * 0.01 * 0.0004, 4)

    def test_pnl_calculation_short_tp(self, db):
        # SHORT entry=65000 exit=63000 qty=0.01 lev=5
        # pnl = (65000-63000)*0.01*5 = 100
        # fees = 63000*0.01*0.0004 = 0.252
        # net = 100 - 0.252 = 99.748
        _insert_trade(db, side="SHORT", entry_price=65000.0,
                      stop_loss=66000.0, take_profit=63000.0)
        pm = PositionManager(db, lambda s: 62000.0)
        result = pm.check_positions()
        assert result[0]["pnl"] == round(100.0 - 63000.0 * 0.01 * 0.0004, 4)


class TestCloseTrade:

    def test_close_trade_updates_db(self, db):
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 63000.0)
        results = pm.check_positions()
        assert len(results) == 1

        pm.close_trade(results[0])

        row = db.execute("SELECT exit_price, pnl, status, exit_time FROM trades WHERE id = 1").fetchone()
        assert row[0] == 64000.0
        assert row[2] == "CLOSED"
        assert row[3] is not None  # exit_time set

    def test_closed_trade_not_rechecked(self, db):
        _insert_trade(db, stop_loss=64000.0, take_profit=67000.0)
        pm = PositionManager(db, lambda s: 63000.0)
        results = pm.check_positions()
        pm.close_trade(results[0])

        # Second check should find nothing
        results2 = pm.check_positions()
        assert len(results2) == 0
