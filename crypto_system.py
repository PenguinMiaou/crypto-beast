# main.py
"""Crypto Beast v1.0 — Autonomous Crypto Trading Bot for Binance Futures."""
import argparse
import asyncio
import fcntl
import json
import os
import random
import signal as signal_module
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from loguru import logger

# Configure loguru
logger.remove()
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level: <8} | {message}")
logger.add("logs/crypto_beast_{time:YYYY-MM-DD}.log", rotation="1 day", retention="30 days", level="DEBUG")


def _write_watchdog_state_safe(state_path: str, updates: dict) -> None:
    """Atomic write to watchdog.state with file lock."""
    if not os.path.exists(state_path):
        with open(state_path, "w") as f:
            json.dump({}, f)
    with open(state_path, "r+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            data = json.load(f)
            data.update(updates)
            f.seek(0)
            f.truncate()
            json.dump(data, f)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class GracefulShutdown:
    """Handle SIGINT/SIGTERM for graceful shutdown."""

    def __init__(self):
        self.shutting_down = False
        signal_module.signal(signal_module.SIGINT, self._handle)
        signal_module.signal(signal_module.SIGTERM, self._handle)

    def _handle(self, signum, frame):
        if self.shutting_down:
            logger.warning("Force shutdown requested")
            sys.exit(1)
        logger.info(f"Shutdown signal received ({signum}), finishing current cycle...")
        self.shutting_down = True


class TradingBot:
    """Main trading bot orchestrator."""

    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.config = None
        self.db = None
        self.exchange = None
        self.modules = {}
        self._peak_equity = 100.0
        self._peak_wallet = 100.0  # Historical peak wallet balance (for circuit breaker)
        self._circuit_breaker_triggered = False
        self._daily_pnl = 0.0
        self._daily_fees = 0.0
        self._cycle_count = 0

    async def initialize(self) -> bool:
        """Initialize all modules with real Binance connection."""
        from dotenv import dotenv_values
        import ccxt.async_support as ccxt_async
        import ccxt as ccxt_sync
        from config import Config
        from core.database import Database
        from core.rate_limiter import BinanceRateLimiter
        from core.system_guard import SystemGuard
        from data.data_feed import DataFeed
        from analysis.market_regime import MarketRegimeDetector
        from analysis.multi_timeframe import MultiTimeframe
        from analysis.session_trader import SessionTrader
        from analysis.event_engine import EventEngine
        from analysis.altcoin_radar import AltcoinRadar
        from analysis.pattern_scanner import PatternScanner
        from strategy.strategy_engine import StrategyEngine
        from strategy.funding_rate_arb import FundingRateArb
        from defense.risk_manager import RiskManager
        from defense.anti_trap import AntiTrap
        from defense.fee_optimizer import FeeOptimizer
        from defense.defense_manager import DefenseManager
        from execution.paper_executor import PaperExecutor
        from execution.smart_order import SmartOrder
        from evolution.compound_engine import CompoundEngine
        from evolution.evolver import Evolver
        from evolution.trade_reviewer import TradeReviewer
        from data.whale_tracker import WhaleTracker
        from data.sentiment_radar import SentimentRadar
        from data.liquidation_hunter import LiquidationHunter
        from data.orderbook_sniper import OrderBookSniper
        from monitoring.notifier import Notifier
        from monitoring.monitor import MonitorData

        try:
            # Load env
            env = dotenv_values(".env")

            # Core
            self.config = Config()
            # DB stored in runtime dir (local disk, persistent)
            import os
            runtime_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(runtime_dir, "crypto_beast.db")
            self.db = Database(db_path)
            self.db.initialize()
            rate_limiter = BinanceRateLimiter()

            # Create exchange connection for data fetching
            self.exchange = ccxt_async.binance({
                'apiKey': env.get("BINANCE_API_KEY", ""),
                'secret': env.get("BINANCE_API_SECRET", ""),
                'options': {'defaultType': 'future'},
                'enableRateLimit': True,
            })

            # Also create sync exchange for price queries
            exchange_sync = ccxt_sync.binance({
                'apiKey': env.get("BINANCE_API_KEY", ""),
                'secret': env.get("BINANCE_API_SECRET", ""),
                'options': {'defaultType': 'future'},
                'enableRateLimit': True,
            })

            # Test connectivity
            t0 = time.time()
            ticker = await self.exchange.fetch_ticker("BTC/USDT")
            latency = (time.time() - t0) * 1000
            btc_price = ticker['last']
            logger.info(f"Binance connected: BTC/USDT = ${btc_price:,.2f} (latency: {latency:.0f}ms)")

            # Get account balance
            account = await self.exchange.fapiPrivateV2GetAccount()
            wallet = float(account.get('totalWalletBalance', 0))
            logger.info(f"Futures wallet: {wallet:.2f} USDT")
            self.config.starting_capital = wallet

            # Restore peak equity from DB (survives restarts)
            try:
                db_peak = self.db.execute("SELECT MAX(equity) FROM equity_snapshots").fetchone()[0]
                self._peak_equity = max(wallet, db_peak or wallet)
                logger.info(f"Peak equity restored: ${self._peak_equity:.2f}")
            except Exception:
                self._peak_equity = wallet

            # Circuit breaker: track peak wallet balance (only realized PnL + deposits)
            # Persisted in DB as a special equity_snapshot with equity=-1 marker
            try:
                db_peak_wallet = self.db.execute(
                    "SELECT MAX(equity) FROM equity_snapshots WHERE unrealized_pnl = -1"
                ).fetchone()[0]
                self._peak_wallet = max(wallet, db_peak_wallet or wallet)
            except Exception:
                self._peak_wallet = wallet
            self._circuit_breaker_triggered = False
            circuit_floor = self._peak_wallet * self.config.circuit_breaker_pct
            logger.info(f"Circuit breaker: peak wallet ${self._peak_wallet:.2f}, floor ${circuit_floor:.2f} ({self.config.circuit_breaker_pct:.0%})")

            # DataFeed
            # Default symbols: BTC + top altcoins
            initial_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
            data_feed = DataFeed(
                symbols=initial_symbols,
                intervals=["5m", "15m", "1h", "4h"],
                rate_limiter=rate_limiter,
                exchange=self.exchange,
            )

            # Preload cached klines from DB
            data_feed.load_from_db(self.db)

            # Analysis
            regime_detector = MarketRegimeDetector()
            multi_timeframe = MultiTimeframe()
            session_trader = SessionTrader()
            event_engine = EventEngine()
            altcoin_radar = AltcoinRadar()
            pattern_scanner = PatternScanner()
            whale_tracker = WhaleTracker(large_trade_threshold=self.config.whale_trade_threshold)
            sentiment_radar = SentimentRadar(
                bullish_threshold=self.config.fear_greed_bullish,
                bearish_threshold=self.config.fear_greed_bearish,
            )
            liquidation_hunter = LiquidationHunter(cascade_multiplier=self.config.cascade_multiplier)
            orderbook_sniper = OrderBookSniper(
                imbalance_bullish=self.config.orderbook_imbalance_bullish,
                imbalance_bearish=self.config.orderbook_imbalance_bearish,
            )
            smart_order = SmartOrder()

            # Strategy - weights act as multipliers on confidence
            # Higher weights = strategies contribute more to final confidence
            strategy_engine = StrategyEngine(regime_detector, session_trader, multi_timeframe)
            strategy_engine.update_weights({
                "trend_follower": 1.0,
                "mean_reversion": 0.8,
                "momentum": 0.9,
                "breakout": 0.7,
            })
            funding_rate_arb = FundingRateArb()

            # Evolution (created early so RiskManager can use Kelly sizing)
            compound_engine = CompoundEngine(self.config, self.db)
            evolver = Evolver(self.config, self.db)
            trade_reviewer = TradeReviewer(self.db)

            # Defense — lower confidence threshold for paper testing
            if self.paper_mode:
                self.config.max_risk_per_trade = 0.02  # 2% risk per trade
            risk_manager = RiskManager(self.config, self.db, compound_engine)
            anti_trap = AntiTrap()
            fee_optimizer = FeeOptimizer(self.config)
            defense = DefenseManager(self.config)

            # Execution
            def get_price(symbol):
                try:
                    ccxt_sym = symbol[:-4] + "/USDT" if symbol.endswith("USDT") and "/" not in symbol else symbol
                    t = exchange_sync.fetch_ticker(ccxt_sym)
                    return t['last']
                except Exception:
                    return btc_price

            if self.paper_mode:
                executor = PaperExecutor(db=self.db, current_price_fn=get_price)
            else:
                from execution.executor import LiveExecutor
                executor = LiveExecutor(
                    exchange=self.exchange,
                    db=self.db,
                    rate_limiter=rate_limiter,
                )

            # Position management (SL/TP)
            from execution.position_manager import PositionManager
            position_manager = PositionManager(
                db=self.db, get_price_fn=get_price,
                config=self.config,
                executor=executor if not self.paper_mode else None,
            )

            # Monitoring
            notifier = Notifier(
                telegram_token=env.get("TELEGRAM_BOT_TOKEN", ""),
                telegram_chat_id=env.get("TELEGRAM_CHAT_ID", ""),
            )
            monitor = MonitorData(self.db)
            system_guard = SystemGuard(latency_warn=1000, latency_halt=5000)
            # Don't use initial latency (includes SSL handshake)

            # Store all modules
            self.modules = {
                "rate_limiter": rate_limiter,
                "data_feed": data_feed,
                "regime_detector": regime_detector,
                "multi_timeframe": multi_timeframe,
                "session_trader": session_trader,
                "event_engine": event_engine,
                "altcoin_radar": altcoin_radar,
                "pattern_scanner": pattern_scanner,
                "whale_tracker": whale_tracker,
                "sentiment_radar": sentiment_radar,
                "liquidation_hunter": liquidation_hunter,
                "orderbook_sniper": orderbook_sniper,
                "smart_order": smart_order,
                "strategy_engine": strategy_engine,
                "funding_rate_arb": funding_rate_arb,
                "risk_manager": risk_manager,
                "anti_trap": anti_trap,
                "fee_optimizer": fee_optimizer,
                "defense": defense,
                "executor": executor,
                "position_manager": position_manager,
                "compound_engine": compound_engine,
                "evolver": evolver,
                "trade_reviewer": trade_reviewer,
                "notifier": notifier,
                "monitor": monitor,
                "system_guard": system_guard,
                "exchange_sync": exchange_sync,
            }

            mode = "PAPER" if self.paper_mode else "LIVE"
            logger.info(f"Crypto Beast v1.0 initialized in {mode} mode | Capital: {wallet:.2f} USDT")
            notifier.send("System Started", f"Crypto Beast {mode} mode | ${wallet:.2f} USDT | BTC=${btc_price:,.0f}")

            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def reconcile_with_exchange(self) -> None:
        """Sync local DB with Binance. Preserves SL/TP/strategy if already in DB."""
        logger.info("Reconciling with Binance...")

        account = await self.exchange.fapiPrivateV2GetAccount()
        positions = [p for p in account.get("positions", []) if float(p.get("positionAmt", 0)) != 0]

        db_trades = self.db.execute(
            "SELECT id, symbol, side FROM trades WHERE status = 'OPEN'"
        ).fetchall()
        # Track by symbol+side for hedge mode
        db_keys = {(row[1], row[2]) for row in db_trades}
        exchange_keys = set()
        for pos in positions:
            amt = float(pos.get("positionAmt", 0))
            side = "LONG" if amt > 0 else "SHORT"
            exchange_keys.add((pos["symbol"], side))

        # Remove stale DB trades not on exchange (match by symbol+side)
        executor = self.modules.get("executor")
        for symbol, side in db_keys - exchange_keys:
            self.db.execute(
                "UPDATE trades SET status='CLOSED', exit_time=?, exit_price=entry_price, pnl=0 "
                "WHERE symbol=? AND side=? AND status='OPEN'",
                (datetime.now(timezone.utc).isoformat(), symbol, side))
            # Cancel orphaned algo orders for this closed position
            if executor and hasattr(executor, "cancel_algo_orders"):
                binance_sym = symbol if symbol.endswith("USDT") else symbol + "USDT"
                try:
                    await executor.cancel_algo_orders(binance_sym, side)
                except Exception as e:
                    logger.warning(f"Failed to cancel algo orders for stale {symbol} {side}: {e}")
            logger.info(f"  Closed stale: {side} {symbol} (not on exchange)")

        for pos in positions:
            symbol = pos["symbol"]
            amt = float(pos["positionAmt"])
            side = "LONG" if amt > 0 else "SHORT"
            entry_price = float(pos.get("entryPrice", 0))
            leverage = int(pos.get("leverage", 1))
            unrealized = float(pos.get("unrealizedProfit", 0))

            # Match by symbol+side
            open_count = self.db.execute(
                "SELECT COUNT(*) FROM trades WHERE symbol=? AND side=? AND status='OPEN'", (symbol, side)
            ).fetchone()[0]

            if open_count == 1:
                # Exactly one record — update it, keep SL/TP/strategy
                self.db.execute(
                    "UPDATE trades SET quantity=?, entry_price=?, leverage=? WHERE symbol=? AND side=? AND status='OPEN'",
                    (abs(amt), entry_price, leverage, symbol, side))
                logger.info(f"  Synced: {side} {symbol} qty={abs(amt)} @ {entry_price} | PnL={unrealized:+.2f}")
            elif open_count > 1:
                # Duplicates — keep earliest, delete rest, then update
                self.db.execute(
                    "DELETE FROM trades WHERE status='OPEN' AND symbol=? AND side=? AND id NOT IN "
                    "(SELECT MIN(id) FROM trades WHERE status='OPEN' AND symbol=? AND side=?)",
                    (symbol, side, symbol, side))
                self.db.execute(
                    "UPDATE trades SET quantity=?, entry_price=?, leverage=? WHERE symbol=? AND side=? AND status='OPEN'",
                    (abs(amt), entry_price, leverage, symbol, side))
                logger.info(f"  Deduped+Synced: {side} {symbol} (removed {open_count - 1} duplicates)")
            else:
                # New position — try to inherit strategy from most recent CLOSED trade of same symbol+side
                last_strategy = self.db.execute(
                    "SELECT strategy FROM trades WHERE symbol=? AND side=? AND status='CLOSED' AND strategy != 'reconciled' ORDER BY id DESC LIMIT 1",
                    (symbol, side)
                ).fetchone()
                strategy = last_strategy[0] if last_strategy else "reconciled"
                self.db.execute(
                    """INSERT INTO trades (symbol, side, entry_price, quantity, leverage, strategy, entry_time, fees, status, stop_loss, take_profit)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (symbol, side, entry_price, abs(amt), leverage, strategy,
                     datetime.now(timezone.utc).isoformat(), 0, "OPEN", 0, 0))
                logger.info(f"  Added: {side} {symbol} qty={abs(amt)} @ {entry_price} {leverage}x | strategy={strategy} | PnL={unrealized:+.2f}")

        # Cancel stale LIMIT entry orders (NOT algo/SL orders — those are managed by ensure_sl_orders)
        try:
            for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
                ccxt_sym = symbol[:-4] + "/USDT"
                try:
                    # Fetch open orders and cancel only LIMIT/MARKET entry orders, not algo SL
                    open_orders = await self.exchange.fetch_open_orders(ccxt_sym)
                    for order in open_orders:
                        if order.get("type") in ("limit", "market"):
                            await self.exchange.cancel_order(order["id"], ccxt_sym)
                            logger.info(f"Cancelled stale {order['type']} order: {symbol} {order['id']}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"Failed to cancel stale orders: {e}")

        # Reconcile CLOSED trades PnL/fees with Binance income API
        await self._reconcile_pnl_with_exchange()

        # Initialize peak tracking for reconciled positions
        position_manager = self.modules.get("position_manager")
        if position_manager:
            rows = self.db.execute(
                "SELECT id, symbol, side, entry_price FROM trades WHERE status = 'OPEN'"
            ).fetchall()
            for row in rows:
                trade_id = row[0]
                if trade_id not in position_manager._peak_profits:
                    position_manager._peak_profits[trade_id] = 0.0
                    position_manager._peak_prices[trade_id] = row[3]
            if rows:
                logger.info(f"Initialized peak tracking for {len(rows)} reconciled positions")

        # Ensure all open positions have SL protection on exchange
        executor = self.modules.get("executor")
        if executor and hasattr(executor, "ensure_sl_orders"):
            try:
                placed = await executor.ensure_sl_orders(self.db)
                if placed:
                    logger.info(f"Placed {placed} missing SL orders on startup")
            except Exception as e:
                logger.warning(f"ensure_sl_orders failed: {e}")

        logger.info(f"Reconciliation complete: {len(positions)} positions synced")

    async def _reconcile_pnl_with_exchange(self) -> None:
        """Reconcile CLOSED trade PnL and fees with Binance income API (source of truth)."""
        try:
            import aiohttp, hmac, hashlib, time as _time
            from urllib.parse import urlencode
            from collections import defaultdict
            from dotenv import dotenv_values

            env = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))
            api_key = env.get("BINANCE_API_KEY", "")
            api_secret = env.get("BINANCE_API_SECRET", "")

            async def fetch_income(income_type: str) -> list:
                ts = int(_time.time() * 1000)
                params = {"incomeType": income_type, "limit": 1000, "timestamp": ts}
                query = urlencode(params)
                sig = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
                url = f"https://fapi.binance.com/fapi/v1/income?{query}&signature={sig}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers={"X-MBX-APIKEY": api_key}, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            return await resp.json()
                return []

            # Fetch realized PnL and commissions from Binance
            pnl_records = await fetch_income("REALIZED_PNL")
            fee_records = await fetch_income("COMMISSION")

            if not pnl_records:
                return

            # Aggregate by symbol
            pnl_by_symbol = defaultdict(float)
            fees_by_symbol = defaultdict(float)
            for r in pnl_records:
                pnl_by_symbol[r["symbol"]] += float(r.get("income", 0))
            for r in fee_records:
                fees_by_symbol[r["symbol"]] += abs(float(r.get("income", 0)))

            # Compare with DB
            db_rows = self.db.execute(
                "SELECT symbol, SUM(pnl), SUM(fees) FROM trades WHERE status='CLOSED' GROUP BY symbol"
            ).fetchall()
            db_pnl = {r[0]: float(r[1] or 0) for r in db_rows}
            db_fees = {r[0]: float(r[2] or 0) for r in db_rows}

            corrected = 0
            for symbol in set(list(pnl_by_symbol.keys()) + list(db_pnl.keys())):
                binance_pnl = pnl_by_symbol.get(symbol, 0)
                local_pnl = db_pnl.get(symbol, 0)
                binance_fee = fees_by_symbol.get(symbol, 0)
                local_fee = db_fees.get(symbol, 0)

                pnl_diff = abs(binance_pnl - local_pnl)
                fee_diff = abs(binance_fee - local_fee)

                if pnl_diff > 0.01 or fee_diff > 0.01:
                    # Find the most recent CLOSED trade for this symbol to apply correction
                    last_trade = self.db.execute(
                        "SELECT id FROM trades WHERE symbol=? AND status='CLOSED' ORDER BY exit_time DESC LIMIT 1",
                        (symbol,)
                    ).fetchone()
                    if last_trade:
                        # Apply PnL difference to last trade
                        self.db.execute(
                            "UPDATE trades SET pnl = pnl + ? WHERE id = ?",
                            (round(binance_pnl - local_pnl, 4), last_trade[0])
                        )
                        # Apply fee difference across all trades for this symbol
                        trade_count = self.db.execute(
                            "SELECT COUNT(*) FROM trades WHERE symbol=?", (symbol,)
                        ).fetchone()[0]
                        if trade_count > 0:
                            fee_per_trade = round(binance_fee / trade_count, 4)
                            self.db.execute(
                                "UPDATE trades SET fees=? WHERE symbol=?",
                                (fee_per_trade, symbol)
                            )
                        corrected += 1
                        logger.info(f"  PnL corrected {symbol}: DB {local_pnl:+.4f} -> Binance {binance_pnl:+.4f} (diff {binance_pnl - local_pnl:+.4f})")

            if corrected:
                logger.info(f"  PnL reconciliation: {corrected} symbol(s) corrected from Binance income API")
        except Exception as e:
            logger.debug(f"PnL reconciliation skipped: {e}")

    async def fetch_market_data(self) -> bool:
        """Fetch latest klines from Binance for all symbols/timeframes (parallel)."""
        import pandas as pd
        m = self.modules
        data_feed = m["data_feed"]
        success = True

        async def _fetch_one(symbol: str, interval: str):
            ccxt_symbol = symbol[:-4] + "/USDT" if symbol.endswith("USDT") and "/" not in symbol else symbol
            ohlcv = await self.exchange.fetch_ohlcv(ccxt_symbol, interval, limit=200)
            df = pd.DataFrame(ohlcv, columns=["open_time", "open", "high", "low", "close", "volume"])
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            return symbol, interval, df

        tasks = []
        for symbol in data_feed.symbols:
            for interval in data_feed.intervals:
                tasks.append(_fetch_one(symbol, interval))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch market data: {result}")
                success = False
            else:
                symbol, interval, df = result
                data_feed.update_cache(symbol, interval, df)

        return success

    async def run_trading_cycle(self) -> None:
        """Execute one full trading cycle."""
        m = self.modules
        self._cycle_count += 1

        # Check watchdog state for pause/commands
        _state_path = os.path.join(os.path.dirname(__file__), "watchdog.state")
        if os.path.exists(_state_path):
            try:
                import json as _json
                import fcntl
                with open(_state_path, "r+") as _f:
                    fcntl.flock(_f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        _wstate = _json.load(_f)
                        if _wstate.get("paused"):
                            logger.info("Trading paused via watchdog")
                            return
                        _cmd = _wstate.get("command")
                        if _cmd and isinstance(_cmd, dict):
                            action = _cmd.get("action", "")
                            if action == "CLOSE":
                                symbol = _cmd.get("args", "")
                                if symbol:
                                    await self._close_symbol_by_watchdog(symbol)
                            elif action == "CLOSEALL":
                                positions = await m["executor"].get_positions()
                                await self._emergency_close(positions)
                            elif action == "SHUTDOWN":
                                logger.info("Shutdown command from watchdog")
                                return
                            _wstate["command"] = None
                            _f.seek(0)
                            _f.truncate()
                            _json.dump(_wstate, _f)
                    finally:
                        fcntl.flock(_f, fcntl.LOCK_UN)
            except BlockingIOError:
                # Non-blocking: if watchdog holds the lock, next 5s cycle will pick it up
                logger.debug("Watchdog state locked by another process, skipping")
            except Exception as e:
                logger.debug(f"Failed to read watchdog.state: {e}")

        from core.models import Portfolio, ShieldAction, OrderType, ExecutionPlan, ValidatedOrder

        # 1. Fetch market data
        t0 = time.time()
        data_ok = await self.fetch_market_data()
        latency = (time.time() - t0) * 1000
        m["system_guard"].update_latency(latency)
        m["system_guard"].report_module_status("data_feed", data_ok)

        if not data_ok:
            logger.warning("Data fetch incomplete, continuing with available data")

        # Feed intelligence modules with latest data
        intel_biases = {}  # symbol -> list of DirectionalBias
        data_feed = m["data_feed"]
        for symbol in data_feed.symbols:
            klines_5m = data_feed.get_klines(symbol, "5m")
            if len(klines_5m) == 0:
                continue

            last_bar = klines_5m.iloc[-1]
            current_price = float(last_bar["close"])

            # Feed WhaleTracker with recent large-volume bars
            volume_avg = klines_5m["volume"].tail(20).mean()
            if last_bar["volume"] > volume_avg * 3:
                m["whale_tracker"].process_trade({
                    "price": current_price,
                    "quantity": last_bar["volume"],
                    "is_buyer_maker": last_bar["close"] < last_bar["open"],
                    "timestamp": datetime.now(timezone.utc),
                })

            # Feed OrderBookSniper with real orderbook data
            orderbook_signal = None
            try:
                ccxt_symbol = symbol[:-4] + "/USDT" if symbol.endswith("USDT") and "/" not in symbol else symbol
                ob = await self.exchange.fetch_order_book(ccxt_symbol, limit=20)
                orderbook_signal = m["orderbook_sniper"].get_signal(symbol, {
                    "bids": ob.get("bids", []),
                    "asks": ob.get("asks", []),
                })
            except Exception as e:
                logger.debug(f"Orderbook fetch failed for {symbol}: {e}")

            # Feed LiquidationHunter with volume-based liquidation proxy
            if len(klines_5m) >= 20:
                recent_vol = klines_5m["volume"].tail(5).mean()
                avg_vol = klines_5m["volume"].tail(20).mean()
                if avg_vol > 0:
                    m["liquidation_hunter"].update_average(avg_vol * current_price)
                if recent_vol > avg_vol * 2:
                    # Large volume spike = potential liquidation cascade
                    side = "LONG" if last_bar["close"] < last_bar["open"] else "SHORT"
                    m["liquidation_hunter"].process_liquidation({
                        "side": side,
                        "quantity": recent_vol,
                        "price": current_price,
                        "timestamp": datetime.now(timezone.utc),
                    })

            # Get directional biases from intelligence modules
            whale_signal = m["whale_tracker"].get_signal(symbol)
            sentiment_signal = m["sentiment_radar"].get_signal(symbol)
            liquidation_signal = m["liquidation_hunter"].get_signal(symbol)

            # Collect intel biases for signal enhancement
            biases = []
            if whale_signal and whale_signal.confidence > 0.3:
                biases.append(whale_signal)
            if sentiment_signal and sentiment_signal.confidence > 0.3:
                biases.append(sentiment_signal)
            if liquidation_signal and liquidation_signal.confidence > 0.3:
                biases.append(liquidation_signal)
            try:
                if orderbook_signal and orderbook_signal.confidence > 0.3:
                    biases.append(orderbook_signal)
            except Exception:
                pass
            if biases:
                intel_biases[symbol] = biases

        # 2. Check system health (affects new trades only, not position monitoring)
        system_healthy = m["system_guard"].should_trade()
        if not system_healthy:
            logger.warning(f"System not healthy (latency={m['system_guard']._api_latency_ms:.0f}ms), skipping new trades (position monitoring continues)")

        # 3. Build portfolio state — single API call for positions + account data
        positions, equity, available_balance, wallet_balance = await m["executor"].get_positions_and_account()

        # Get real equity from Binance (ground truth, not DB calculation)
        try:

            # Update peak wallet (only goes up — deposits + realized gains)
            if wallet_balance > self._peak_wallet:
                self._peak_wallet = wallet_balance
                # Persist to DB
                try:
                    self.db.execute(
                        "INSERT INTO equity_snapshots (timestamp, equity, unrealized_pnl) VALUES (?, ?, -1)",
                        (datetime.now(timezone.utc).isoformat(), wallet_balance))
                except Exception:
                    pass

            # CIRCUIT BREAKER: wallet below 80% of peak → emergency close + halt
            circuit_floor = self._peak_wallet * self.config.circuit_breaker_pct
            if wallet_balance < circuit_floor and not self._circuit_breaker_triggered:
                self._circuit_breaker_triggered = True
                logger.critical(
                    f"CIRCUIT BREAKER: wallet ${wallet_balance:.2f} < floor ${circuit_floor:.2f} "
                    f"({self.config.circuit_breaker_pct:.0%} of peak ${self._peak_wallet:.2f})"
                )
                positions = await m["executor"].get_positions()
                await self._emergency_close(positions)
                m["notifier"].send(
                    "CIRCUIT BREAKER",
                    f"熔断触发！钱包 ${wallet_balance:.2f} 低于安全底线 ${circuit_floor:.2f}\n"
                    f"(历史最高 ${self._peak_wallet:.2f} 的 {self.config.circuit_breaker_pct:.0%})\n"
                    f"所有仓位已平仓，交易已停止。\n"
                    f"发送 /resume 手动恢复交易。",
                    level="critical",
                )
                # Write paused state so bot stays stopped across restarts
                try:
                    _state_path = os.path.join(os.path.dirname(__file__), "watchdog.state")
                    _write_watchdog_state_safe(_state_path, {"paused": True})
                except Exception as _e:
                    logger.error(f"Failed to write watchdog.state: {_e}")
                return

            if self._circuit_breaker_triggered:
                # Stay halted until user manually /resume
                return

        except Exception:
            # Fallback to DB calculation if API fails
            closed_pnl = self.db.execute(
                "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
            ).fetchone()[0]
            open_fees = self.db.execute(
                "SELECT COALESCE(SUM(fees), 0) FROM trades WHERE status = 'OPEN'"
            ).fetchone()[0]
            equity = self.config.starting_capital + closed_pnl - open_fees
            for pos in positions:
                equity += pos.unrealized_pnl

        self._peak_equity = max(self._peak_equity, equity)
        drawdown = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0

        portfolio = Portfolio(
            equity=equity,
            available_balance=available_balance if available_balance > 0 else equity,
            positions=positions,
            peak_equity=self._peak_equity,
            locked_capital=m["compound_engine"].get_locked_capital(),
            daily_pnl=self._daily_pnl,
            total_fees_today=self._daily_fees,
            drawdown_pct=drawdown,
        )

        # 4. Defense check (unified recovery + emergency)
        defense_result = m["defense"].check(portfolio)
        if defense_result.action == ShieldAction.EMERGENCY_CLOSE:
            logger.warning("Defense: EMERGENCY_CLOSE")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", "Shield: drawdown limit — all positions closed", level="critical")
            return
        elif defense_result.action == ShieldAction.HALT:
            logger.warning("Defense: HALT")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", "Shield: HALT — daily loss limit, pausing 24h", level="critical")
            return
        elif defense_result.action == ShieldAction.ALREADY_NOTIFIED:
            return

        # 5. Check cooldown
        if m["defense"].is_in_cooldown():
            logger.info("In cooldown, skipping trading")
            return

        if m["defense"].pop_just_resumed():
            m["notifier"].send("Resume", "Shield cooldown expired, resuming", level="info")

        recovery_params = defense_result.params

        REGIME_OVERRIDES = {
            "TRANSITIONING": {
                "max_leverage": 5,
                "min_confidence": 0.5,
                "mtf_min_score": 5,
            },
        }

        # 6.5. Periodic SL check — ensure all positions have exchange-level SL protection
        # Needed because LIMIT orders may fill after _place_exit_orders was called with qty=0
        if self._cycle_count % 60 == 0 and not self.paper_mode and positions:
            executor = m.get("executor")
            if executor and hasattr(executor, "ensure_sl_orders"):
                try:
                    placed = await executor.ensure_sl_orders(self.db)
                    if placed:
                        logger.info(f"Periodic SL check: placed {placed} missing SL orders")
                except Exception as e:
                    logger.warning(f"Periodic SL check failed: {e}")

        # 7. Check existing positions FIRST (before opening new ones)
        to_close = m["position_manager"].check_positions()
        closed_this_cycle = False
        for trade in to_close:
            if self.paper_mode:
                m["position_manager"].close_trade(trade)
            else:
                success = await m["position_manager"].close_trade_live(trade)
                if not success:
                    continue
            closed_this_cycle = True
            self._daily_pnl += trade["pnl"]
            self._daily_fees += trade["fees"]
            m["notifier"].send(
                f"Trade Closed ({trade['reason']})",
                f"{trade['side']} {trade['symbol']} | Entry=${trade['entry_price']:,.2f} → "
                f"Exit=${trade['exit_price']:,.2f} | PnL={trade['pnl']:+.4f} | {trade['strategy']}",
                level="warning" if trade["reason"] == "STOP_LOSS" else "info",
            )

        # Process any queued SL updates (breakeven moves)
        await m["position_manager"].process_pending_sl_updates()

        # 8-10: Preparation for signal generation
        _skip_new_trades = not system_healthy

        # If we closed positions this cycle, skip opening new ones
        # (let margin settle, exchange state update, avoid ghost orders)
        if closed_this_cycle:
            _skip_new_trades = True

        if m["event_engine"].should_reduce_exposure():
            logger.debug("Near funding settlement, skipping new entries")
            _skip_new_trades = True

        if not _skip_new_trades:
            m["evolver"].apply_if_pending()

            # Update multi-timeframe confluence
            data_feed = m["data_feed"]
            for symbol in data_feed.symbols:
                klines_by_tf = {}
                for tf in data_feed.intervals:
                    kl = data_feed.get_klines(symbol, tf)
                    if len(kl) > 0:
                        klines_by_tf[tf] = kl
                if klines_by_tf:
                    m["multi_timeframe"].update(symbol, klines_by_tf)

        # 10. Generate and execute signals (skip if unhealthy/funding — position monitoring always runs)
        # When positions full: still generate signals for FLIP (reversal), but no new symbols
        _positions_full = len(positions) >= self.config.max_concurrent_positions
        if not _positions_full and portfolio.available_balance < 10:
            _skip_new_trades = True

        opened_this_cycle = 0  # Max 1 new position per cycle
        # Build set of (symbol, side) already held — prevent duplicate/opposing positions
        held_positions = set()  # type: ignore
        held_symbols = set()  # type: ignore
        for p in positions:
            binance_sym = p.symbol if p.symbol.endswith("USDT") and "/" not in p.symbol else p.symbol.replace("/USDT:USDT", "USDT").replace("/USDT", "USDT")
            held_positions.add((binance_sym, p.direction.value))
            held_symbols.add(binance_sym)

        for symbol in data_feed.symbols:
            if _skip_new_trades or opened_this_cycle >= 1:
                break

            if _positions_full:
                # Full: only process symbols we already hold (for potential flip)
                if symbol not in held_symbols:
                    continue
            else:
                # Not full: skip symbols we already hold (no stacking)
                if symbol in held_symbols:
                    continue

            klines_5m = data_feed.get_klines(symbol, "5m")
            if len(klines_5m) < 50:
                continue

            # Detect regime (also used by generate_signals internally)
            current_regime = m["regime_detector"].detect(klines_5m, symbol=symbol)

            # Apply regime tightening overrides on top of defense params
            regime_key = current_regime.value if hasattr(current_regime, "value") else str(current_regime)
            override = REGIME_OVERRIDES.get(regime_key, {})
            if override:
                for key, val in override.items():
                    current = recovery_params.get(key, val)
                    if key == "max_leverage":
                        recovery_params[key] = min(current, val)
                    elif key in ("min_confidence", "mtf_min_score"):
                        recovery_params[key] = max(current, val)

            # Generate signals
            signals = m["strategy_engine"].generate_signals(symbol, klines_5m)

            # Pattern scanning
            patterns = m["pattern_scanner"].scan(klines_5m, symbol)
            for pattern in patterns:
                from core.models import TradeSignal, MarketRegime
                # Convert pattern to TradeSignal if confidence is high enough
                if pattern.confidence >= 0.5:
                    regime = m["regime_detector"].detect(klines_5m)
                    entry = float(klines_5m.iloc[-1]["close"])
                    sl = pattern.stop_price
                    tp = pattern.target_price
                    # Cap SL distance: ensure R:R >= 1:1.5 (SL no wider than TP distance / 1.5)
                    tp_dist = abs(tp - entry)
                    sl_dist = abs(sl - entry)
                    if tp_dist > 0 and sl_dist > tp_dist / 1.5:
                        max_sl_dist = tp_dist / 1.5
                        if pattern.direction == Direction.LONG:
                            sl = round(entry - max_sl_dist, 2)
                        else:
                            sl = round(entry + max_sl_dist, 2)
                    pattern_signal = TradeSignal(
                        symbol=symbol,
                        direction=pattern.direction,
                        confidence=pattern.confidence,
                        entry_price=entry,
                        stop_loss=sl,
                        take_profit=tp,
                        strategy=f"pattern_{pattern.name}",
                        regime=regime,
                        timeframe_score=0,
                    )
                    signals.append(pattern_signal)

            if not signals:
                continue

            # Sort by confidence (strategy engine already deduped, pattern signals may be added)
            signals.sort(key=lambda s: s.confidence, reverse=True)

            # Skip if we already opened a position this cycle (max 1 per cycle)
            if opened_this_cycle >= 1:
                break

            for signal in signals:
                # When positions full, only allow flip (opposite direction to current holding)
                if _positions_full:
                    from core.models import Direction
                    current_side = next((side for sym, side in held_positions if sym == symbol), None)
                    if current_side and current_side == signal.direction.value:
                        continue  # Same direction as held — skip, no stacking

                # Apply intelligence module biases
                from core.models import SignalType, Direction
                symbol_biases = intel_biases.get(signal.symbol, [])
                if symbol_biases:
                    signal_type = SignalType.BULLISH if signal.direction == Direction.LONG else SignalType.BEARISH
                    agreement_count = sum(1 for b in symbol_biases if b.direction == signal_type)
                    conflict_count = sum(1 for b in symbol_biases if b.direction != signal_type and b.direction != SignalType.NEUTRAL)
                    intel_adj = agreement_count * 0.01 - conflict_count * 0.02
                    signal.confidence = max(0.05, min(1.0, signal.confidence + intel_adj))
                    if intel_adj != 0:
                        logger.debug(f"Intel adjustment {signal.symbol}: {intel_adj:+.2f} ({agreement_count} agree, {conflict_count} conflict)")

                # AntiTrap filter
                if m["anti_trap"].is_trap(signal, klines_5m):
                    logger.debug(f"Signal trapped: {signal.symbol} {signal.direction.value}")
                    try:
                        self.db.execute(
                            "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                            (signal.symbol, signal.direction.value, signal.strategy, "anti_trap: detected as trap",
                             signal.entry_price, datetime.now(timezone.utc).isoformat())
                        )
                    except Exception:
                        pass
                    continue

                # MTF confluence filter — block signals that conflict with higher timeframes
                mtf_direction = SignalType.BULLISH if signal.direction == Direction.LONG else SignalType.BEARISH
                mtf_min = recovery_params.get("mtf_min_score", 5)
                confluence = m["multi_timeframe"].get_confluence(signal.symbol)
                if confluence and abs(confluence.score) >= mtf_min:
                    # Strong MTF signal exists — check if it conflicts
                    if confluence.direction != mtf_direction and confluence.direction != SignalType.NEUTRAL:
                        logger.debug(f"MTF filter: {signal.symbol} {signal.direction.value} conflicts with MTF {confluence.direction.value} (score={confluence.score})")
                        try:
                            self.db.execute(
                                "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                                (signal.symbol, signal.direction.value, signal.strategy,
                                 f"mtf_filter: conflicts with MTF (score={confluence.score})",
                                 signal.entry_price, datetime.now(timezone.utc).isoformat())
                            )
                        except Exception:
                            pass
                        continue
                # Weak/neutral MTF lets signals through — don't block on insufficient data

                # Apply recovery constraints (relaxed in paper mode)
                min_conf_recovery = recovery_params.get("min_confidence", 0.3)
                if signal.confidence < min_conf_recovery:
                    logger.debug(f"Signal below recovery threshold: {signal.confidence} < {min_conf_recovery}")
                    try:
                        self.db.execute(
                            "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                            (signal.symbol, signal.direction.value, signal.strategy,
                             f"recovery_threshold: {signal.confidence:.3f} < {min_conf_recovery:.3f}",
                             signal.entry_price, datetime.now(timezone.utc).isoformat())
                        )
                    except Exception:
                        pass
                    continue

                # Risk validation
                min_conf = 0.4
                order = m["risk_manager"].validate(signal, portfolio, min_confidence=min_conf)
                if order is None:
                    try:
                        self.db.execute(
                            "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                            (signal.symbol, signal.direction.value, signal.strategy,
                             "risk_manager: validation failed",
                             signal.entry_price, datetime.now(timezone.utc).isoformat())
                        )
                    except Exception:
                        pass
                    continue

                # Cap leverage per recovery mode
                max_lev = recovery_params.get("max_leverage", 10)
                if order.leverage > max_lev:
                    order = ValidatedOrder(
                        signal=order.signal,
                        quantity=order.quantity,
                        leverage=max_lev,
                        order_type=order.order_type,
                        risk_amount=order.risk_amount,
                        max_slippage=order.max_slippage,
                    )

                # Fee optimization
                order_type = m["fee_optimizer"].recommend_order_type(signal)
                fee_est = m["fee_optimizer"].estimate_fee(
                    order.quantity * signal.entry_price, order_type)
                if not m["fee_optimizer"].is_within_budget(fee_est):
                    logger.debug("Fee budget exceeded, skipping")
                    try:
                        self.db.execute(
                            "INSERT INTO rejected_signals (symbol, side, strategy, reason, signal_price, timestamp) VALUES (?,?,?,?,?,?)",
                            (signal.symbol, signal.direction.value, signal.strategy,
                             "fee_optimizer: budget exceeded",
                             signal.entry_price, datetime.now(timezone.utc).isoformat())
                        )
                    except Exception:
                        pass
                    continue

                # Small accounts (<$500) use single entry in live (urgency=1.0 for no DCA split)
                # Paper mode uses real confidence to test DCA
                if portfolio.equity < 500 and not self.paper_mode:
                    plan = m["smart_order"].plan_execution(order, urgency=1.0)
                else:
                    plan = m["smart_order"].plan_execution(order, urgency=signal.confidence)

                # For low-urgency trades, use LIMIT to save fees (maker 0.02% vs taker 0.04%)
                # IOC (Immediate-or-Cancel) prevents stale orders — cancels if not filled immediately
                if signal.confidence < 0.6 and plan.entry_tranches:
                    first_tranche = plan.entry_tranches[0]
                    from core.models import Direction as _Direction
                    if signal.direction == _Direction.LONG:
                        limit_price = round(signal.entry_price * 0.9998, 2)  # 0.02% below
                    else:
                        limit_price = round(signal.entry_price * 1.0002, 2)  # 0.02% above
                    first_tranche["type"] = "LIMIT"
                    first_tranche["price"] = limit_price
                    first_tranche["timeInForce"] = "IOC"

                # Randomize entry timing to avoid signal crowding (game theory recommendation)
                if random.random() < 0.3:  # 30% of trades get delayed
                    delay_seconds = random.randint(5, 15)
                    await asyncio.sleep(delay_seconds)
                    # Check if price moved too much during delay
                    try:
                        ccxt_ticker_sym = signal.symbol[:-4] + "/USDT:USDT" if signal.symbol.endswith("USDT") else signal.symbol
                        current_ticker = await self.exchange.fetch_ticker(ccxt_ticker_sym)
                        current_price = current_ticker.get("last", signal.entry_price)
                        if current_price and signal.entry_price > 0:
                            drift = abs(current_price - signal.entry_price) / signal.entry_price
                            if drift > 0.005:  # >0.5% price drift
                                logger.debug(f"Signal stale after delay: {signal.symbol} drifted {drift:.2%}, skipping")
                                continue
                    except Exception:
                        pass  # If fetch fails, proceed with original signal

                # Randomize position size ±10% (mixed strategy)
                size_jitter = 1.0 + random.uniform(-0.10, 0.10)
                if plan.entry_tranches:
                    plan.entry_tranches[0]["quantity"] = round(
                        plan.entry_tranches[0]["quantity"] * size_jitter, 8
                    )

                # Close opposite-direction position first (flip instead of hedge)
                from core.models import Direction
                flip_failed = False
                for pos in positions:
                    if pos.symbol == signal.symbol and pos.direction != signal.direction:
                        logger.info(f"Flipping {signal.symbol}: closing {pos.direction.value} before opening {signal.direction.value}")
                        close_result = await m["executor"].close_position(pos, OrderType.MARKET)
                        if close_result.success:
                            pnl = pos.unrealized_pnl - close_result.fees_paid
                            self.db.execute(
                                "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, pnl=?, fees=fees+? "
                                "WHERE symbol=? AND side=? AND status='OPEN'",
                                (close_result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
                                 round(pnl, 4), round(close_result.fees_paid, 6),
                                 pos.symbol, pos.direction.value),
                            )
                            self._daily_pnl += pnl
                            self._daily_fees += close_result.fees_paid
                            m["notifier"].send(
                                f"Position Flipped ({pos.direction.value}→{signal.direction.value})",
                                f"{pos.symbol} closed {pos.direction.value} PnL={pnl:+.4f} | opening {signal.direction.value}",
                            )
                        elif close_result.error == "already_closed":
                            # Position already closed by exchange SL — mark DB with estimated PnL
                            self.db.execute(
                                "UPDATE trades SET status='CLOSED', exit_time=?, exit_price=entry_price, pnl=0 "
                                "WHERE symbol=? AND side=? AND status='OPEN'",
                                (datetime.now(timezone.utc).isoformat(), pos.symbol, pos.direction.value),
                            )
                            logger.info(f"Flip: {pos.symbol} {pos.direction.value} already closed on exchange, marked DB")
                        else:
                            # Close failed — don't open new position
                            logger.warning(f"Flip close failed for {pos.symbol}: {close_result.error}, aborting flip")
                            flip_failed = True
                        break
                if flip_failed:
                    continue

                # Execute
                result = await m["executor"].execute(plan)
                if result.success:
                    opened_this_cycle += 1
                    m["fee_optimizer"].record_fee(result.fees_paid)
                    self._daily_fees += result.fees_paid
                    # Track slippage
                    expected_price = signal.entry_price
                    actual_price = result.avg_fill_price
                    slippage_pct = abs(actual_price - expected_price) / expected_price if expected_price > 0 else 0
                    if slippage_pct > 0.001:  # > 0.1%
                        logger.warning(
                            f"HIGH SLIPPAGE: {symbol} expected ${expected_price:,.2f} got ${actual_price:,.2f} "
                            f"({slippage_pct:.3%})"
                        )
                    m["notifier"].send(
                        "Trade Opened",
                        f"{signal.direction.value} {symbol} @ ${result.avg_fill_price:,.2f} | "
                        f"qty={result.total_filled:.6f} | conf={signal.confidence:.2f} | "
                        f"slip={slippage_pct:.3%} | strategy={signal.strategy}",
                    )
                    logger.info(
                        f"TRADE: {signal.direction.value} {symbol} @ ${result.avg_fill_price:,.2f} | "
                        f"strategy={signal.strategy} | conf={signal.confidence:.3f}"
                    )
                    break  # Max 1 trade per symbol per cycle

        # 11. Position monitoring already done in step 7 above

        # 12. Update compound sizing
        m["compound_engine"].update_position_sizing(portfolio)

        # 13. Update monitor
        m["monitor"].update({
            "status": m["system_guard"].check().value,
            "positions": len(positions),
            "equity": equity,
            "peak_equity": self._peak_equity,
            "drawdown_pct": drawdown,
            "cycle": self._cycle_count,
            "session": m["session_trader"].get_current_session(),
        })

        # Log status every 10 cycles
        if self._cycle_count % 10 == 0:
            logger.info(
                f"Cycle {self._cycle_count} | Equity: ${equity:.2f} | "
                f"Positions: {len(positions)} | Session: {m['session_trader'].get_current_session()}"
            )

        # Stats checkpoint every 100 cycles
        if self._cycle_count % 100 == 0:
            try:
                total = self.db.execute(
                    "SELECT COUNT(*) FROM trades WHERE status='CLOSED'"
                ).fetchone()[0]
                logger.info(f"Stats checkpoint: {total} closed trades (need 200+ for validation)")
            except Exception:
                pass

    async def _close_symbol_by_watchdog(self, symbol: str) -> None:
        """Close a specific symbol position via watchdog command."""
        from core.models import OrderType
        positions = await self.modules["executor"].get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                await self.modules["executor"].close_position(pos, OrderType.MARKET)
                logger.info(f"Closed {symbol} via watchdog command")
                return
        logger.warning(f"No open position for {symbol} to close")

    async def _emergency_close(self, positions) -> None:
        """Close all positions on exchange AND update DB status."""
        from core.models import OrderType
        executor = self.modules["executor"]
        await executor.cancel_all_pending()
        for pos in positions:
            result = await executor.close_position(pos, OrderType.MARKET)
            # Update DB: mark as CLOSED
            if result.success:
                pnl = pos.unrealized_pnl - result.fees_paid
                self.db.execute(
                    "UPDATE trades SET status='CLOSED', exit_price=?, exit_time=?, pnl=?, fees=fees+? "
                    "WHERE symbol=? AND status='OPEN'",
                    (result.avg_fill_price, datetime.now(timezone.utc).isoformat(),
                     round(pnl, 4), round(result.fees_paid, 6), pos.symbol),
                )
                self._daily_pnl += pnl
                self._daily_fees += result.fees_paid
                logger.info(f"Emergency closed {pos.symbol}: PnL={pnl:+.4f} (fees={result.fees_paid:.4f})")

    async def run_scheduler(self, shutdown: GracefulShutdown) -> None:
        """Background scheduler for periodic tasks."""
        m = self.modules
        while not shutdown.shutting_down:
            now = datetime.now(timezone.utc)

            # Daily review at 00:05 UTC
            if now.hour == 0 and now.minute == 5:
                logger.info("Running daily trade review")
                try:
                    trades = self.db.execute(
                        "SELECT id, side, strategy, pnl, fees FROM trades WHERE status = 'CLOSED' AND exit_time >= datetime('now', '-1 day')"
                    ).fetchall()
                    if trades:
                        trade_dicts = [{"id": t[0], "pnl": t[3], "fees": t[4], "side": t[1],
                                       "regime": "RANGING", "strategy": t[2]} for t in trades]
                        report = m["trade_reviewer"].generate_report(trade_dicts)
                        logger.info(f"Daily review: {report.wins}W/{report.losses}L | Recommendations: {report.recommendations[:3]}")
                except Exception as e:
                    logger.error(f"Daily review failed: {e}")

            # Daily evolution at 00:10 UTC
            if now.hour == 0 and now.minute == 10:
                logger.info("Running daily evolution")
                try:
                    # Get yesterday's closed trades for recommendations
                    yesterday_trades = self.db.execute(
                        "SELECT id, side, strategy, pnl, fees FROM trades WHERE status = 'CLOSED' AND exit_time >= datetime('now', '-1 day')"
                    ).fetchall()
                    trade_dicts = []
                    for t in yesterday_trades:
                        trade_dicts.append({
                            "id": t[0], "pnl": t[3], "fees": t[4],
                            "side": t[1], "regime": "RANGING", "strategy": t[2]
                        })

                    # Generate recommendations from actual data
                    recommendations = []
                    if trade_dicts:
                        report = m["trade_reviewer"].generate_report(trade_dicts)
                        recommendations = report.recommendations

                    # Gather klines for evolution
                    data_feed = m["data_feed"]
                    evolution_data = {}
                    for symbol in data_feed.symbols:
                        klines = data_feed.get_klines(symbol, "5m")
                        if len(klines) >= 200:
                            evolution_data[symbol] = klines

                    if evolution_data:
                        report = await m["evolver"].run_daily_evolution(
                            data=evolution_data,
                            recommendations=recommendations
                        )
                        if report:
                            m["strategy_engine"].update_weights(report.strategy_weights)
                            m["notifier"].send(
                                "Evolution Complete",
                                f"Sharpe: {report.backtest_sharpe_before:.3f} -> {report.backtest_sharpe_after:.3f}",
                                level="info"
                            )
                except Exception as e:
                    logger.error(f"Daily evolution failed: {e}")

            # Update sentiment every 5 minutes
            if now.minute % 5 == 0 and now.second < 60:
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        # Fear & Greed Index
                        async with session.get("https://api.alternative.me/fng/?limit=1", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                fg_value = int(data["data"][0]["value"])
                                m["sentiment_radar"].update_fear_greed(fg_value)
                                logger.debug(f"Fear & Greed updated: {fg_value}")

                        # Long/Short ratio from Binance
                        async with session.get(
                            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                            params={"symbol": "BTCUSDT", "period": "5m", "limit": 1},
                            timeout=aiohttp.ClientTimeout(total=10)
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if data:
                                    ls_ratio = float(data[0]["longShortRatio"])
                                    m["sentiment_radar"].update_long_short_ratio(ls_ratio)
                                    logger.debug(f"L/S ratio updated: {ls_ratio}")
                except Exception as e:
                    logger.debug(f"Sentiment update failed: {e}")

            # Update funding rates every 30 minutes
            if now.minute % 30 == 0 and now.second < 60:
                try:
                    for symbol in m["data_feed"].symbols:
                        ccxt_sym = symbol[:-4] + "/USDT" if symbol.endswith("USDT") and "/" not in symbol else symbol
                        funding = await self.exchange.fetch_funding_rate(ccxt_sym)
                        rate = funding.get("fundingRate", 0)
                        m["funding_rate_arb"].update_funding_rate(symbol, rate)
                        logger.debug(f"Funding rate {symbol}: {rate}")
                except Exception as e:
                    logger.debug(f"Funding rate update failed: {e}")

            # Altcoin rescan every 4 hours (00:15, 04:15, 08:15, 12:15, 16:15, 20:15 UTC)
            if now.hour % 4 == 0 and now.minute == 15:
                try:
                    tickers = await self.exchange.fetch_tickers()
                    radar = m["altcoin_radar"]
                    radar._scores.clear()
                    radar._filtered_out.clear()
                    scored = 0
                    for symbol, ticker in tickers.items():
                        # Binance Futures ccxt format: "ETH/USDT:USDT"
                        if symbol.endswith(":USDT") and "/" in symbol:
                            internal_sym = symbol.split("/")[0] + "USDT"
                            vol = ticker.get("quoteVolume", 0) or 0
                            pct = ticker.get("percentage", 0) or 0
                            result = radar.score_coin(
                                internal_sym,
                                volume_24h=vol,
                                price_change_24h=pct,
                            )
                            if result is not None:
                                scored += 1
                    top_alts = radar.get_top_alts()
                    base = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
                    extra = [s for s in top_alts if s not in base]
                    new_symbols = base + extra[:2]  # Max 5 symbols total
                    m["data_feed"].symbols = new_symbols
                    filtered = len(radar.get_filtered_out())
                    logger.info(f"AltcoinRadar: scored {scored}, filtered {filtered}, trading {new_symbols}")
                except Exception as e:
                    logger.error(f"Altcoin rescan failed: {e}")

            # Reset daily counters at midnight
            if now.hour == 0 and now.minute == 0:
                self._daily_pnl = 0.0
                self._daily_fees = 0.0

            # Daily backup at 00:30 UTC
            if now.hour == 0 and now.minute == 30:
                if self.db:
                    try:
                        self.db.backup(f"backups/crypto_beast_{now.date()}.db")
                        logger.info("Daily backup complete")
                    except Exception as e:
                        logger.error(f"Backup failed: {e}")

            # Equity snapshot every hour (from Binance API, not DB)
            if now.minute == 0 and self.db:
                try:
                    account = await self.exchange.fapiPrivateV2GetAccount()
                    snap_equity = float(account.get("totalMarginBalance", 0))
                    self.db.execute(
                        "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                        (now.isoformat(), snap_equity))
                except Exception:
                    pass

            # Save klines every hour
            if now.minute == 0 and self.db:
                try:
                    m["data_feed"].save_to_db(self.db)
                except Exception:
                    pass

            await asyncio.sleep(60)

    async def shutdown_sequence(self) -> None:
        """Graceful shutdown: cancel orders, save state, close connections."""
        logger.info("Starting shutdown sequence...")

        m = self.modules

        # Cancel pending orders
        try:
            await m["executor"].cancel_all_pending()
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")

        # Save equity snapshot (from Binance API)
        if self.db and self.exchange:
            try:
                account = await self.exchange.fapiPrivateV2GetAccount()
                snap_equity = float(account.get("totalMarginBalance", 0))
                self.db.execute(
                    "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                    (datetime.now(timezone.utc).isoformat(), snap_equity))
            except Exception:
                pass

        # Close persistent aiohttp session
        try:
            await m["executor"].close()
        except Exception as e:
            logger.error(f"Failed to close executor session: {e}")

        # Close async exchange
        if self.exchange:
            try:
                await self.exchange.close()
            except Exception:
                pass

        # Notify
        m["notifier"].send("System Shutdown", "Crypto Beast shutting down gracefully")

        logger.info("Shutdown complete")


async def main(args):
    """Main async entry point."""
    shutdown = GracefulShutdown()
    bot = TradingBot(paper_mode=not args.live)

    success = await bot.initialize()
    if not success:
        logger.error("Failed to initialize. Exiting.")
        return

    # Reconcile with exchange on startup
    await bot.reconcile_with_exchange()

    # Start scheduler in background
    scheduler_task = asyncio.create_task(bot.run_scheduler(shutdown))

    interval = bot.config.main_loop_interval
    logger.info(f"Main loop started (every {interval}s). Press Ctrl+C to stop.")

    try:
        while not shutdown.shutting_down:
            try:
                await bot.run_trading_cycle()
            except Exception as e:
                logger.error(f"Trading cycle error: {e}")
                import traceback
                traceback.print_exc()
                bot.modules["notifier"].send("Error", str(e)[:200], level="warning")

            await asyncio.sleep(interval)
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await bot.shutdown_sequence()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crypto Beast v1.0")
    parser.add_argument("--live", action="store_true", help="Run in live mode (default: paper)")
    parser.add_argument("--no-dashboard", action="store_true", help="Disable dashboard")
    args = parser.parse_args()

    # macOS sleep prevention
    caffeinate = None
    try:
        caffeinate = subprocess.Popen(["caffeinate", "-dims"], stdout=subprocess.DEVNULL)
        logger.info("Sleep prevention active (caffeinate)")
    except FileNotFoundError:
        logger.warning("caffeinate not found, sleep prevention disabled")

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if caffeinate:
            caffeinate.terminate()
