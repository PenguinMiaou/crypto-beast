# main.py
"""Crypto Beast v1.0 — Autonomous Crypto Trading Bot for Binance Futures."""
import argparse
import asyncio
import signal as signal_module
import subprocess
import sys
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
        self.modules = {}

    async def initialize(self) -> bool:
        """Initialize all modules."""
        from config import Config
        from core.database import Database
        from core.rate_limiter import BinanceRateLimiter
        from core.system_guard import SystemGuard
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
        from core.models import Portfolio

        try:
            # Core
            self.config = Config()
            self.db = Database("crypto_beast.db")
            self.db.initialize()
            rate_limiter = BinanceRateLimiter()

            # Analysis
            regime_detector = MarketRegimeDetector()
            multi_timeframe = MultiTimeframe()
            session_trader = SessionTrader()
            event_engine = EventEngine()
            altcoin_radar = AltcoinRadar()
            pattern_scanner = PatternScanner()

            # Strategy
            strategy_engine = StrategyEngine(regime_detector, session_trader, multi_timeframe)
            funding_rate_arb = FundingRateArb()

            # Defense
            risk_manager = RiskManager(self.config)
            anti_trap = AntiTrap()
            fee_optimizer = FeeOptimizer()
            emergency_shield = EmergencyShield(self.config)
            recovery_mode = RecoveryMode(self.config)

            # Execution
            if self.paper_mode:
                executor = PaperExecutor(
                    db=self.db,
                    current_price_fn=lambda s: 65000.0  # Will be replaced with real price fn
                )
            else:
                # Live executor would be initialized here with real exchange
                logger.error("Live mode not yet fully configured")
                return False

            # Evolution
            compound_engine = CompoundEngine(self.config, self.db)
            evolver = Evolver(self.config, self.db)
            trade_reviewer = TradeReviewer(self.db)

            # Monitoring
            notifier = Notifier(
                telegram_token=self.config.telegram_bot_token,
                telegram_chat_id=self.config.telegram_chat_id,
            )
            monitor = MonitorData(self.db)
            system_guard = SystemGuard()

            # Store all modules
            self.modules = {
                "rate_limiter": rate_limiter,
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
                "compound_engine": compound_engine,
                "evolver": evolver,
                "trade_reviewer": trade_reviewer,
                "notifier": notifier,
                "monitor": monitor,
                "system_guard": system_guard,
            }

            mode = "PAPER" if self.paper_mode else "LIVE"
            logger.info(f"Crypto Beast v1.0 initialized in {mode} mode")
            notifier.send("System Started", f"Crypto Beast initialized in {mode} mode")

            return True

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    async def run_trading_cycle(self) -> None:
        """Execute one trading cycle."""
        m = self.modules

        # Check system health
        status = m["system_guard"].get_status()
        if status.value == "CRITICAL":
            logger.warning("System in CRITICAL state, skipping cycle")
            return

        # Check emergency shield
        from core.models import Portfolio, ShieldAction, OrderType

        # Build portfolio state
        positions = await m["executor"].get_positions()
        equity = self.config.starting_capital  # Simplified; would track real equity
        portfolio = Portfolio(
            equity=equity, available_balance=equity,
            positions=positions, peak_equity=equity,
            locked_capital=m["compound_engine"].get_locked_capital(),
            daily_pnl=0.0, total_fees_today=0.0, drawdown_pct=0.0)

        # Emergency check
        action = m["emergency_shield"].check(portfolio)
        if action != ShieldAction.CONTINUE:
            logger.warning(f"Emergency shield triggered: {action}")
            await self._emergency_close(positions)
            m["notifier"].send("EMERGENCY", f"Shield: {action.value}", level="critical")
            return

        # Check recovery mode
        recovery_params = m["recovery_mode"].check(portfolio)

        # Check if near funding settlement
        if m["event_engine"].should_reduce_exposure():
            logger.info("Near funding settlement, reducing exposure")
            return

        # Apply pending evolution config
        m["evolver"].apply_if_pending()

        # Generate signals for each symbol
        symbols = ["BTCUSDT"]  # Will expand with AltcoinRadar

        for symbol in symbols:
            # Note: In full mode, would use DataFeed for real klines
            # For now, skip if no data available
            pass

        # Update compound sizing
        m["compound_engine"].update_position_sizing(portfolio)

        # Update monitor
        m["monitor"].update({
            "status": status.value,
            "positions": len(positions),
            "equity": equity,
        })

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
                # Would call trade_reviewer.generate_report()

            # Daily evolution at 00:10 UTC
            if now.hour == 0 and now.minute == 10:
                logger.info("Running daily evolution")
                # Would call evolver.run_daily_evolution()

            # Daily backup at 00:30 UTC
            if now.hour == 0 and now.minute == 30:
                logger.info("Running daily backup")
                if self.db:
                    try:
                        self.db.backup(f"backups/crypto_beast_{now.date()}.db")
                    except Exception as e:
                        logger.error(f"Backup failed: {e}")

            await asyncio.sleep(60)

    async def shutdown_sequence(self) -> None:
        """Graceful shutdown: cancel orders, save state."""
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
                self.db.execute(
                    "INSERT INTO equity_snapshots (timestamp, equity, drawdown_pct) VALUES (?, ?, ?)",
                    (datetime.now(timezone.utc).isoformat(), self.config.starting_capital, 0.0))
            except Exception as e:
                logger.error(f"Failed to save snapshot: {e}")

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

    logger.info(f"Starting main loop (interval={bot.config.main_loop_interval}s)")

    try:
        while not shutdown.shutting_down:
            try:
                await bot.run_trading_cycle()
            except Exception as e:
                logger.error(f"Trading cycle error: {e}")
                bot.modules["notifier"].send("Error", str(e), level="warning")

            await asyncio.sleep(bot.config.main_loop_interval)
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
