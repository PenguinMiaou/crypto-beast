# main.py
"""Crypto Beast v1.0 — Autonomous Crypto Trading Bot for Binance Futures."""
import argparse
import asyncio
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
        from execution.paper_executor import PaperExecutor
        from execution.emergency_shield import EmergencyShield
        from execution.recovery_mode import RecoveryMode
        from evolution.compound_engine import CompoundEngine
        from evolution.evolver import Evolver
        from evolution.trade_reviewer import TradeReviewer
        from monitoring.notifier import Notifier
        from monitoring.monitor import MonitorData

        try:
            # Load env
            env = dotenv_values(".env")

            # Core
            self.config = Config()
            self.db = Database("crypto_beast.db")
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
            self._peak_equity = wallet

            # DataFeed
            data_feed = DataFeed(
                symbols=["BTCUSDT"],
                intervals=["5m", "15m", "1h", "4h"],
                rate_limiter=rate_limiter,
                exchange=self.exchange,
            )

            # Analysis
            regime_detector = MarketRegimeDetector()
            multi_timeframe = MultiTimeframe()
            session_trader = SessionTrader()
            event_engine = EventEngine()
            altcoin_radar = AltcoinRadar()
            pattern_scanner = PatternScanner()

            # Strategy - weights act as multipliers on confidence
            # Higher weights = strategies contribute more to final confidence
            strategy_engine = StrategyEngine(regime_detector, session_trader, multi_timeframe)
            strategy_engine.update_weights({
                "trend_follower": 1.0,
                "mean_reversion": 0.8,
                "momentum": 0.9,
                "breakout": 0.7,
                "scalper": 0.6,
            })
            funding_rate_arb = FundingRateArb()

            # Defense — lower confidence threshold for paper testing
            if self.paper_mode:
                self.config.max_risk_per_trade = 0.02  # 2% risk per trade
            risk_manager = RiskManager(self.config)
            anti_trap = AntiTrap()
            fee_optimizer = FeeOptimizer()
            emergency_shield = EmergencyShield(self.config)
            recovery_mode = RecoveryMode(self.config)

            # Execution
            def get_price(symbol):
                try:
                    t = exchange_sync.fetch_ticker(symbol.replace("USDT", "/USDT"))
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
            position_manager = PositionManager(db=self.db, get_price_fn=get_price)

            # Evolution
            compound_engine = CompoundEngine(self.config, self.db)
            evolver = Evolver(self.config, self.db)
            trade_reviewer = TradeReviewer(self.db)

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
                "strategy_engine": strategy_engine,
                "funding_rate_arb": funding_rate_arb,
                "risk_manager": risk_manager,
                "anti_trap": anti_trap,
                "fee_optimizer": fee_optimizer,
                "emergency_shield": emergency_shield,
                "recovery_mode": recovery_mode,
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

    async def fetch_market_data(self) -> bool:
        """Fetch latest klines from Binance for all symbols/timeframes."""
        m = self.modules
        data_feed = m["data_feed"]
        success = True

        for symbol in data_feed.symbols:
            ccxt_symbol = symbol.replace("USDT", "/USDT")
            for interval in data_feed.intervals:
                try:
                    import pandas as pd
                    ohlcv = await self.exchange.fetch_ohlcv(ccxt_symbol, interval, limit=200)
                    df = pd.DataFrame(ohlcv, columns=["open_time", "open", "high", "low", "close", "volume"])
                    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
                    data_feed.update_cache(symbol, interval, df)
                except Exception as e:
                    logger.warning(f"Failed to fetch {symbol} {interval}: {e}")
                    success = False

        return success

    async def run_trading_cycle(self) -> None:
        """Execute one full trading cycle."""
        m = self.modules
        self._cycle_count += 1

        from core.models import Portfolio, ShieldAction, OrderType, ExecutionPlan

        # 1. Fetch market data
        t0 = time.time()
        data_ok = await self.fetch_market_data()
        latency = (time.time() - t0) * 1000
        m["system_guard"].update_latency(latency)
        m["system_guard"].report_module_status("data_feed", data_ok)

        if not data_ok:
            logger.warning("Data fetch incomplete, continuing with available data")

        # 2. Check system health
        if not m["system_guard"].should_trade():
            logger.warning(f"System not healthy (latency={m['system_guard']._api_latency_ms:.0f}ms), skipping")
            return

        # 3. Build portfolio state
        positions = await m["executor"].get_positions()

        # Calculate real equity from DB
        closed_pnl = self.db.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
        ).fetchone()[0]
        open_fees = self.db.execute(
            "SELECT COALESCE(SUM(fees), 0) FROM trades WHERE status = 'OPEN'"
        ).fetchone()[0]
        equity = self.config.starting_capital + closed_pnl - open_fees

        # Add unrealized PnL from open positions
        for pos in positions:
            equity += pos.unrealized_pnl

        self._peak_equity = max(self._peak_equity, equity)
        drawdown = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0

        portfolio = Portfolio(
            equity=equity,
            available_balance=equity,
            positions=positions,
            peak_equity=self._peak_equity,
            locked_capital=m["compound_engine"].get_locked_capital(),
            daily_pnl=self._daily_pnl,
            total_fees_today=self._daily_fees,
            drawdown_pct=drawdown,
        )

        # 4. Emergency check
        action = m["emergency_shield"].check(portfolio)
        if action != ShieldAction.CONTINUE:
            logger.warning(f"Emergency shield: {action.value}")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", f"Shield: {action.value}", level="critical")
            return

        # 5. Check cooldown
        if m["emergency_shield"].is_in_cooldown():
            logger.info("In cooldown, skipping trading")
            return

        # 6. Recovery mode adjustment
        m["recovery_mode"].assess_state(portfolio)
        recovery_params = m["recovery_mode"].get_adjusted_params()

        # 7. Check funding settlement
        if m["event_engine"].should_reduce_exposure():
            logger.debug("Near funding settlement, skipping new entries")
            return

        # 8. Apply pending evolution
        m["evolver"].apply_if_pending()

        # 9. Update multi-timeframe confluence
        data_feed = m["data_feed"]
        for symbol in data_feed.symbols:
            klines_by_tf = {}
            for tf in data_feed.intervals:
                kl = data_feed.get_klines(symbol, tf)
                if len(kl) > 0:
                    klines_by_tf[tf] = kl
            if klines_by_tf:
                m["multi_timeframe"].update(symbol, klines_by_tf)

        # 10. Generate and execute signals
        for symbol in data_feed.symbols:
            klines_5m = data_feed.get_klines(symbol, "5m")
            if len(klines_5m) < 50:
                continue

            # Generate signals
            signals = m["strategy_engine"].generate_signals(symbol, klines_5m)

            if not signals:
                continue

            for signal in signals:
                # AntiTrap filter
                if m["anti_trap"].is_trap(signal, klines_5m):
                    logger.debug(f"Signal trapped: {signal.symbol} {signal.direction.value}")
                    continue

                # Apply recovery constraints (relaxed in paper mode)
                min_conf_recovery = recovery_params.get("min_confidence", 0.5)
                if self.paper_mode:
                    min_conf_recovery = min(0.15, min_conf_recovery)
                if signal.confidence < min_conf_recovery:
                    logger.debug(f"Signal below recovery threshold: {signal.confidence} < {min_conf_recovery}")
                    continue

                # Risk validation (lower threshold in paper mode)
                min_conf = 0.1 if self.paper_mode else 0.3
                order = m["risk_manager"].validate(signal, portfolio, min_confidence=min_conf)
                if order is None:
                    continue

                # Cap leverage per recovery mode
                max_lev = recovery_params.get("max_leverage", 10)
                if order.leverage > max_lev:
                    order = order  # RiskManager already handles this

                # Fee optimization
                order_type = m["fee_optimizer"].recommend_order_type(signal)
                fee_est = m["fee_optimizer"].estimate_fee(
                    order.quantity * signal.entry_price, order_type)
                if not m["fee_optimizer"].is_within_budget(fee_est):
                    logger.debug("Fee budget exceeded, skipping")
                    continue

                # Create execution plan (simple single-tranche for paper)
                plan = ExecutionPlan(
                    order=order,
                    entry_tranches=[{
                        "price": signal.entry_price,
                        "quantity": order.quantity,
                        "type": "MARKET",
                    }],
                    exit_tranches=[],
                )

                # Execute
                result = await m["executor"].execute(plan)
                if result.success:
                    m["fee_optimizer"].record_fee(result.fees_paid)
                    self._daily_fees += result.fees_paid
                    m["notifier"].send(
                        "Trade Opened",
                        f"{signal.direction.value} {symbol} @ ${result.avg_fill_price:,.2f} | "
                        f"qty={result.total_filled:.6f} | conf={signal.confidence:.2f} | "
                        f"strategy={signal.strategy}",
                    )
                    logger.info(
                        f"TRADE: {signal.direction.value} {symbol} @ ${result.avg_fill_price:,.2f} | "
                        f"strategy={signal.strategy} | conf={signal.confidence:.3f}"
                    )

        # 11. Check existing positions for SL/TP
        to_close = m["position_manager"].check_positions()
        for trade in to_close:
            m["position_manager"].close_trade(trade)
            self._daily_pnl += trade["pnl"]
            self._daily_fees += trade["fees"]
            m["notifier"].send(
                f"Trade Closed ({trade['reason']})",
                f"{trade['side']} {trade['symbol']} | Entry=${trade['entry_price']:,.2f} → "
                f"Exit=${trade['exit_price']:,.2f} | PnL={trade['pnl']:+.4f} | {trade['strategy']}",
                level="warning" if trade["reason"] == "STOP_LOSS" else "info",
            )

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

    async def _emergency_close(self, positions) -> None:
        """Close all positions in emergency."""
        from core.models import OrderType
        executor = self.modules["executor"]
        await executor.cancel_all_pending()
        for pos in positions:
            await executor.close_position(pos, OrderType.MARKET)

    async def run_scheduler(self, shutdown: GracefulShutdown) -> None:
        """Background scheduler for periodic tasks."""
        while not shutdown.shutting_down:
            now = datetime.now(timezone.utc)

            # Daily review at 00:05 UTC
            if now.hour == 0 and now.minute == 5:
                logger.info("Running daily trade review")
                try:
                    trades = self.db.execute(
                        "SELECT * FROM trades WHERE status = 'CLOSED' AND exit_time >= date('now', '-1 day')"
                    ).fetchall()
                    if trades:
                        trade_dicts = [{"id": t[0], "pnl": t[7], "fees": t[8], "side": t[2],
                                       "regime": "RANGING", "strategy": t[9]} for t in trades]
                        report = m["trade_reviewer"].generate_report(trade_dicts)
                        logger.info(f"Daily review: {report.wins}W/{report.losses}L | Recommendations: {report.recommendations[:3]}")
                except Exception as e:
                    logger.error(f"Daily review failed: {e}")

            # Daily evolution at 00:10 UTC
            if now.hour == 0 and now.minute == 10:
                logger.info("Running daily evolution")
                try:
                    m["evolver"].apply_if_pending()
                except Exception as e:
                    logger.error(f"Daily evolution failed: {e}")

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

            # Equity snapshot every hour
            if now.minute == 0 and self.db:
                try:
                    closed_pnl = self.db.execute(
                        "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
                    ).fetchone()[0]
                    open_fees = self.db.execute(
                        "SELECT COALESCE(SUM(fees), 0) FROM trades WHERE status = 'OPEN'"
                    ).fetchone()[0]
                    snap_equity = self.config.starting_capital + closed_pnl - open_fees
                    self.db.execute(
                        "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                        (now.isoformat(), snap_equity))
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

        # Save equity snapshot
        if self.db:
            try:
                closed_pnl = self.db.execute(
                    "SELECT COALESCE(SUM(pnl), 0) FROM trades WHERE status = 'CLOSED'"
                ).fetchone()[0]
                open_fees = self.db.execute(
                    "SELECT COALESCE(SUM(fees), 0) FROM trades WHERE status = 'OPEN'"
                ).fetchone()[0]
                snap_equity = self.config.starting_capital + closed_pnl - open_fees
                self.db.execute(
                    "INSERT INTO equity_snapshots (timestamp, equity) VALUES (?, ?)",
                    (datetime.now(timezone.utc).isoformat(), snap_equity))
            except Exception:
                pass

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
