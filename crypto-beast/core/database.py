import shutil
import sqlite3
import threading
from pathlib import Path

from loguru import logger


class Database:
    def __init__(self, db_path: str = "crypto_beast.db"):
        self.db_path = db_path
        self._conn_instance = None

    @property
    def _conn(self) -> sqlite3.Connection:
        if self._conn_instance is None:
            self._conn_instance = sqlite3.connect(
                self.db_path, check_same_thread=False)
            self._conn_instance.execute("PRAGMA journal_mode=WAL")
            self._conn_instance.execute("PRAGMA busy_timeout=5000")
        return self._conn_instance

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity REAL NOT NULL,
            leverage INTEGER NOT NULL,
            strategy TEXT NOT NULL,
            entry_time TIMESTAMP NOT NULL,
            exit_time TIMESTAMP,
            pnl REAL,
            fees REAL,
            status TEXT DEFAULT 'OPEN',
            stop_loss REAL,
            take_profit REAL
        );

        CREATE TABLE IF NOT EXISTS equity_snapshots (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            equity REAL NOT NULL,
            unrealized_pnl REAL,
            locked_capital REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS strategy_performance (
            id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL,
            date DATE NOT NULL,
            trades INTEGER,
            wins INTEGER,
            total_pnl REAL,
            sharpe_ratio REAL,
            weight REAL
        );

        CREATE TABLE IF NOT EXISTS evolution_log (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            parameters_before JSON,
            parameters_after JSON,
            backtest_sharpe REAL,
            changes_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS klines (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            open_time TIMESTAMP NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY (symbol, interval, open_time)
        );

        CREATE TABLE IF NOT EXISTS whale_events (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            event_type TEXT,
            symbol TEXT,
            amount REAL,
            direction TEXT
        );

        CREATE TABLE IF NOT EXISTS trade_reviews (
            id INTEGER PRIMARY KEY,
            trade_id INTEGER NOT NULL REFERENCES trades(id),
            review_date DATE NOT NULL,
            outcome TEXT NOT NULL,
            loss_category TEXT,
            classification_confidence REAL,
            evidence TEXT,
            recommendation TEXT,
            regime_at_entry TEXT,
            session_at_entry TEXT,
            confluence_at_entry INTEGER,
            capture_efficiency REAL
        );

        CREATE TABLE IF NOT EXISTS review_reports (
            id INTEGER PRIMARY KEY,
            period TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            total_trades INTEGER,
            wins INTEGER,
            losses INTEGER,
            loss_distribution JSON,
            recommendations JSON,
            hypothetical_results JSON,
            report_text TEXT
        );

        CREATE TABLE IF NOT EXISTS system_health (
            id INTEGER PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            status TEXT,
            api_latency_ms REAL,
            memory_mb REAL,
            active_modules INTEGER,
            details TEXT
        );
        """
        self._conn.executescript(schema)
        self._conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        cursor = self._conn.execute(query, params)
        if not query.strip().upper().startswith("SELECT"):
            self._conn.commit()
        return cursor

    def executemany(self, query: str, params_list: list[tuple]) -> None:
        self._conn.executemany(query, params_list)
        self._conn.commit()

    def backup(self, backup_path: str) -> None:
        backup_conn = sqlite3.connect(backup_path)
        self._conn.backup(backup_conn)
        backup_conn.close()
        logger.info(f"Database backed up to {backup_path}")

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
