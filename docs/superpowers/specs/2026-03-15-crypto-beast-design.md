# Crypto Beast v1.0 - System Design Document

## Overview

An autonomous, self-evolving cryptocurrency trading system for Binance Futures. Starting with $100 USDT, the system uses leveraged trading (5-10x dynamic), multi-strategy analysis, and automated parameter optimization to maximize returns while protecting capital.

**Key Principles:**
- Fully autonomous — no human intervention required after launch
- Self-evolving — daily backtesting, parameter optimization, strategy reweighting
- Defense in depth — multiple layers of risk management
- Capital preservation first — can't compound if you blow up

**Target:**
- Exchange: Binance Futures (USDT-M Perpetual Contracts)
- Starting Capital: $100 USDT
- Primary Asset: BTC/USDT (~60% allocation)
- Secondary: Auto-selected altcoins (~40% allocation)
- Leverage: 5-10x dynamic based on signal confidence
- Runtime: 24/7 on local Mac

---

## Architecture

7-layer architecture with 20 modules in a single Python process.

```
┌──────────────────────────────────────────────────────────────────┐
│                     CRYPTO BEAST v1.0                             │
│                                                                   │
│  ┏━━━━━━━━━━━━ Layer 0: Infrastructure ━━━━━━━━━━━┓             │
│  ┃ SystemGuard                                     ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 1: Data & Intelligence ━━━━━━┓             │
│  ┃ DataFeed | WhaleTracker | SentimentRadar        ┃             │
│  ┃ LiquidationHunter | OrderBookSniper             ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 2: Analysis ━━━━━━━━━━━━━━━━━┓             │
│  ┃ MarketRegimeDetector | EventEngine              ┃             │
│  ┃ AltcoinRadar | PatternScanner                   ┃             │
│  ┃ SessionTrader | MultiTimeframe                  ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 3: Strategy ━━━━━━━━━━━━━━━━━┓             │
│  ┃ StrategyEngine | FundingRateArb                 ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 4: Filter & Defense ━━━━━━━━━┓             │
│  ┃ AntiTrap | RiskManager | FeeOptimizer           ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 5: Execution ━━━━━━━━━━━━━━━━┓             │
│  ┃ SmartOrder -> Executor                          ┃             │
│  ┃ EmergencyShield | RecoveryMode                  ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 6: Growth & Evolution ━━━━━━━┓             │
│  ┃ CompoundEngine | Evolver | BacktestLab          ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                          │                                        │
│  ┏━━━━━━━━━━━━ Layer 7: Monitoring ━━━━━━━━━━━━━━━┓             │
│  ┃ Monitor (Dashboard) | Notifier                  ┃             │
│  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛             │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │                    SQLite Database                        │    │
│  └──────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
Main Loop (every 5 seconds):
  SystemGuard.check()
  -> DataFeed.fetch()
  -> [WhaleTracker, SentimentRadar, LiquidationHunter, OrderBookSniper].update()
  -> MarketRegimeDetector.detect()
  -> [EventEngine, AltcoinRadar, PatternScanner, SessionTrader].analyze()
  -> MultiTimeframe.filter()
  -> StrategyEngine.generate_signals()
  -> FundingRateArb.check_opportunities()
  -> AntiTrap.filter_signals()
  -> RiskManager.validate()
  -> FeeOptimizer.optimize_order_type()
  -> SmartOrder.plan_execution()
  -> Executor.execute()
  -> CompoundEngine.update_position_sizing()
  -> Monitor.update()
  -> Notifier.send_if_needed()

Evolution Loop (daily at 00:00 UTC):
  BacktestLab.run_walk_forward()
  -> Evolver.optimize_parameters()
  -> Evolver.reweight_strategies()
  -> AltcoinRadar.rescan_universe()
  -> Monitor.log_evolution_report()

Emergency Check (every tick):
  EmergencyShield.check()
  RecoveryMode.assess_state()
```

---

## Module Specifications

### Layer 0: Infrastructure

#### SystemGuard (system_guard.py)

**Purpose:** Self-monitoring of the trading bot's health.

**Responsibilities:**
- Monitor API latency to Binance (warn > 500ms, pause trading > 2000ms)
- Track API rate limits (Binance allows 1200 requests/min for orders, 2400/min for data)
- Monitor system resources (memory, CPU)
- Auto-restart on unrecoverable errors
- Network connectivity check (ping Binance API endpoints)
- Graceful degradation: if non-critical modules fail, continue trading with core modules

**Interface:**
```python
class SystemGuard:
    def check(self) -> SystemStatus:
        """Returns HEALTHY, DEGRADED, or CRITICAL"""
    def should_trade(self) -> bool:
        """False if system is not healthy enough to trade"""
    def restart_module(self, module_name: str) -> bool:
        """Attempt to restart a failed module"""
```

**Health States:**
- HEALTHY: All systems go, full trading
- DEGRADED: Some non-critical modules down, trade with reduced confidence
- CRITICAL: Core module failure or network issue, close positions and stop

---

### Layer 1: Data & Intelligence

#### DataFeed (data_feed.py)

**Purpose:** Real-time and historical market data from Binance.

**Responsibilities:**
- WebSocket connection for real-time klines (1m, 5m, 15m, 1h, 4h)
- REST API fallback when WebSocket disconnects
- OHLCV data for all tracked symbols
- Historical data download and caching for backtesting
- Data normalization and validation (detect bad ticks, gaps)

**Interface:**
```python
class DataFeed:
    async def connect(self) -> None:
        """Establish WebSocket connections"""
    def get_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """Get OHLCV data"""
    def get_orderbook(self, symbol: str, depth: int) -> OrderBook:
        """Get current order book"""
    def get_ticker(self, symbol: str) -> Ticker:
        """Get current price and 24h stats"""
```

**Data Storage:**
- Real-time data: in-memory (last 500 candles per timeframe per symbol)
- Historical data: SQLite (for backtesting)
- Cache invalidation: every 24h re-sync with exchange

#### WhaleTracker (whale_tracker.py)

**Purpose:** Monitor large transactions that may predict price moves.

**Data Sources (free APIs):**
- Whale Alert API (free tier: 10 requests/min)
- Binance large trade detection (trades > $100k from WebSocket)
- Exchange inflow/outflow estimation from public data

**Signals:**
- WHALE_DEPOSIT: Large crypto deposited to exchange -> bearish signal
- WHALE_WITHDRAW: Large crypto withdrawn from exchange -> bullish signal
- WHALE_TRADE: Large market order detected -> momentum signal

**Interface:**
```python
class WhaleTracker:
    def update(self) -> list[WhaleEvent]:
        """Check for new whale activity"""
    def get_signal(self, symbol: str) -> Signal:
        """Returns BULLISH, BEARISH, or NEUTRAL with confidence"""
```

#### SentimentRadar (sentiment_radar.py)

**Purpose:** Gauge market sentiment for contrarian and momentum signals.

**Data Sources (free):**
- Fear & Greed Index API (alternative.me)
- Binance long/short ratio (built-in API)
- Open interest changes (Binance API)

**Logic:**
- Fear & Greed < 20 (Extreme Fear) -> contrarian bullish signal
- Fear & Greed > 80 (Extreme Greed) -> contrarian bearish signal
- Long/Short ratio extreme -> contrarian signal
- Open interest spike + price move -> trend confirmation

**Interface:**
```python
class SentimentRadar:
    def update(self) -> SentimentState:
        """Fetch latest sentiment data"""
    def get_signal(self, symbol: str) -> Signal:
        """Sentiment-based signal with confidence"""
```

#### LiquidationHunter (liquidation_hunter.py)

**Purpose:** Detect and trade liquidation cascades.

**Mechanism:**
- Monitor Binance forced liquidation stream (WebSocket: `forceOrder`)
- Track cumulative liquidation volume in rolling windows (1m, 5m, 15m)
- When liquidation volume exceeds 2x average -> cascade detected
- Long liquidation cascade -> look for bottom to buy (after cascade subsides)
- Short liquidation cascade -> look for top to short (after squeeze subsides)

**Entry Logic:**
- Wait for liquidation rate to peak and start declining (cascade exhaustion)
- Confirm with order book (buying pressure returning after long cascade)
- Tight stop loss below cascade low

**Interface:**
```python
class LiquidationHunter:
    def update(self, liquidation_event: dict) -> None:
        """Process new liquidation data"""
    def get_signal(self, symbol: str) -> Signal:
        """Liquidation-based entry signal"""
    def is_cascade_active(self, symbol: str) -> bool:
        """Whether a liquidation cascade is currently happening"""
```

#### OrderBookSniper (orderbook_sniper.py)

**Purpose:** Read order book depth for supply/demand imbalance signals.

**Analysis:**
- Bid/Ask imbalance ratio (bid_volume / ask_volume at top 20 levels)
- Large wall detection (single order > 5x average at that level)
- Wall pulling detection (large order placed then cancelled -> likely fake)
- Spread analysis (widening spread = uncertainty)

**Signals:**
- BID_HEAVY: Buy pressure dominates -> bullish
- ASK_HEAVY: Sell pressure dominates -> bearish
- WALL_DETECTED: Large support/resistance level identified
- WALL_PULLED: Fake wall detected -> trade opposite direction

**Interface:**
```python
class OrderBookSniper:
    def update(self, orderbook: OrderBook) -> None:
        """Analyze current order book state"""
    def get_signal(self, symbol: str) -> Signal:
        """Order book based signal"""
    def get_imbalance(self, symbol: str) -> float:
        """Bid/ask imbalance ratio: >1 bullish, <1 bearish"""
```

---

### Layer 2: Analysis

#### MarketRegimeDetector (market_regime.py)

**Purpose:** Classify current market state to select appropriate strategies.

**Regimes:**
- TRENDING_UP: Strong uptrend (use trend-following strategies, higher leverage)
- TRENDING_DOWN: Strong downtrend (short-biased strategies)
- RANGING: Sideways/choppy (mean reversion, grid strategies, lower leverage)
- HIGH_VOLATILITY: Explosive moves (reduce position size, wider stops)
- LOW_VOLATILITY: Compression (prepare for breakout, reduce trading)

**Detection Methods:**
- ADX (Average Directional Index): > 25 = trending, < 20 = ranging
- Bollinger Band width: narrow = low vol, wide = high vol
- Moving average alignment: 20 > 50 > 200 = strong uptrend
- ATR percentile: current ATR vs historical ATR

**Interface:**
```python
class MarketRegimeDetector:
    def detect(self, symbol: str) -> MarketRegime:
        """Current market regime with confidence"""
    def get_regime_history(self, symbol: str, periods: int) -> list[MarketRegime]:
        """Recent regime changes"""
```

#### EventEngine (event_engine.py)

**Purpose:** Track scheduled events that cause predictable volatility.

**Event Types:**
- Macro: CPI, FOMC, Non-Farm Payroll, GDP (from free economic calendar APIs)
- Crypto: Token unlocks, exchange listings, contract expirations
- Binance-specific: Futures quarterly expiration dates, funding rate settlement times

**Behavior:**
- Pre-event (1h before): Reduce position size or close positions
- Post-event: Wait for initial spike to settle (5-15 min), then trade the direction
- Funding settlement (every 8h): Adjust positions for funding rate opportunities

**Interface:**
```python
class EventEngine:
    def get_upcoming_events(self, hours: int = 24) -> list[Event]:
        """Events in the next N hours"""
    def should_reduce_risk(self) -> bool:
        """True if a major event is imminent"""
    def get_signal(self) -> Signal:
        """Event-based trading signal"""
```

#### AltcoinRadar (altcoin_radar.py)

**Purpose:** Auto-select the best altcoins to trade and exploit BTC-altcoin lag.

**Coin Selection Criteria (re-evaluated daily by Evolver):**
- Minimum 24h volume > $50M (liquidity requirement for $100 account)
- Available on Binance Futures with USDT margin
- Beta to BTC > 1.5 (amplifies BTC moves)
- Spread < 0.05% (execution quality)

**BTC-Altcoin Lag Strategy:**
- Monitor BTC for sudden moves (> 0.5% in 1 minute)
- Calculate historical lag for each altcoin (typically 10-120 seconds)
- When BTC spikes, immediately enter altcoin position before it catches up
- This is a high-frequency opportunity; execute within seconds

**Interface:**
```python
class AltcoinRadar:
    def rescan_universe(self) -> list[str]:
        """Re-evaluate which altcoins to track (daily)"""
    def get_beta_signal(self, btc_move: float) -> list[TradeSignal]:
        """Lag-based signals when BTC moves"""
    def get_tracked_symbols(self) -> list[str]:
        """Currently tracked altcoins"""
```

**Default Universe (starting set, refined by Evolver):**
- ETH/USDT, SOL/USDT, BNB/USDT, DOGE/USDT, XRP/USDT
- Evolver may add/remove based on performance

#### PatternScanner (pattern_scanner.py)

**Purpose:** Detect classical chart patterns with statistical edge.

**Patterns Detected:**
- Double Top/Bottom (reversal, ~65% accuracy historically)
- Head and Shoulders / Inverse H&S (reversal, ~70% accuracy)
- Triangle (ascending/descending/symmetrical) (continuation/breakout)
- Flag/Pennant (continuation, ~67% accuracy)
- Support/Resistance breakout with volume confirmation

**Implementation:**
- Use pivot point detection (local highs/lows)
- Pattern matching via geometric rules (not ML, keeps it simple and fast)
- Volume confirmation required (breakout on > 1.5x average volume)
- Stop loss: below pattern low (for bullish) / above pattern high (for bearish)

**Interface:**
```python
class PatternScanner:
    def scan(self, symbol: str, timeframe: str) -> list[Pattern]:
        """Detect active patterns"""
    def get_signal(self, symbol: str) -> Signal:
        """Pattern-based entry signal with target and stop"""
```

#### SessionTrader (session_trader.py)

**Purpose:** Optimize strategy selection based on trading session.

**Sessions (UTC):**
- Asia: 00:00-08:00 UTC (lower volatility, mean reversion works better)
- Europe: 08:00-16:00 UTC (increasing volatility, trend starts)
- US: 13:00-21:00 UTC (highest volatility, strongest trends)
- Overlap EU+US: 13:00-16:00 UTC (most volatile, best for breakouts)

**Behavior:**
- Weight strategies differently per session
- Evolver tracks per-session performance and adjusts weights
- Asian session: lower leverage, range strategies
- US session: higher leverage, trend strategies

**Interface:**
```python
class SessionTrader:
    def get_current_session(self) -> Session:
        """Current trading session"""
    def get_strategy_weights(self) -> dict[str, float]:
        """Session-adjusted strategy weights"""
```

#### MultiTimeframe (multi_timeframe.py)

**Purpose:** Require alignment across timeframes before trading.

**Timeframes Monitored:** 5m, 15m, 1h, 4h

**Confluence Scoring:**
- Each timeframe votes: BULLISH (+1), BEARISH (-1), NEUTRAL (0)
- Score = weighted sum (4h weight: 4, 1h: 3, 15m: 2, 5m: 1)
- Max score: +10 (all bullish), Min: -10 (all bearish)
- Trade only when |score| >= 6 (strong confluence)

**Interface:**
```python
class MultiTimeframe:
    def get_confluence(self, symbol: str) -> ConfluenceScore:
        """Multi-timeframe alignment score"""
    def filter_signal(self, signal: Signal) -> Signal:
        """Pass through only if confluence confirms direction"""
```

---

### Layer 3: Strategy

#### StrategyEngine (strategy_engine.py)

**Purpose:** Core strategy execution with multiple parallel strategies.

**Built-in Strategies:**

1. **TrendFollower:**
   - EMA crossover (fast/slow, default 9/21)
   - Entry on pullback to EMA in trend direction
   - Trailing stop at 2x ATR
   - Best in: TRENDING regimes

2. **MeanReversion:**
   - Bollinger Band bounce (entry at 2σ, target at mean)
   - RSI oversold/overbought confirmation
   - Tight stop at 2.5σ
   - Best in: RANGING regimes

3. **Momentum:**
   - Volume-weighted price momentum
   - Entry when momentum accelerates (MACD histogram increasing)
   - Exit when momentum fades
   - Best in: HIGH_VOLATILITY trending

4. **Breakout:**
   - Range compression detection (Bollinger squeeze)
   - Entry on breakout with volume confirmation
   - Stop below range
   - Best in: LOW_VOLATILITY -> breakout transition

5. **Scalper:**
   - Short-term RSI (2-period) extreme readings
   - 1-3 candle holding period on 5m chart
   - Very tight stops, high win rate target
   - Best in: RANGING with clear levels

**Strategy Scoring:**
- Each strategy outputs: direction, confidence (0-1), entry_price, stop_loss, take_profit
- Weighted by: strategy performance (Evolver-adjusted), market regime fit, session weight
- Final signal = weighted ensemble of all strategies

**Interface:**
```python
class StrategyEngine:
    def generate_signals(self, market_data: MarketData) -> list[TradeSignal]:
        """Generate signals from all strategies"""
    def get_strategy_weights(self) -> dict[str, float]:
        """Current strategy weight allocation"""
    def update_weights(self, new_weights: dict[str, float]) -> None:
        """Called by Evolver to adjust weights"""
```

#### FundingRateArb (funding_rate_arb.py)

**Purpose:** Capture funding rate payments as low-risk income.

**Mechanism:**
- Binance perpetual futures charge/pay funding every 8 hours
- When funding rate is extremely positive (> 0.05%): shorts pay longs -> go short
- When funding rate is extremely negative (< -0.05%): longs pay shorts -> go long
- Hold position through funding settlement, exit after collection

**Risk Management:**
- Only enter when funding rate is > 2x average (clear extreme)
- Position size: max 20% of capital (this is a supplementary strategy)
- Stop loss: 1% (funding profit is small, can't afford large adverse move)
- Track historical funding rate patterns per symbol

**Interface:**
```python
class FundingRateArb:
    def check_opportunities(self) -> list[FundingSignal]:
        """Check for funding rate arbitrage opportunities"""
    def get_next_settlement(self) -> datetime:
        """Time until next funding settlement"""
```

---

### Layer 4: Filter & Defense

#### AntiTrap (anti_trap.py)

**Purpose:** Filter out false signals and market manipulation.

**Trap Detection:**

1. **Pin Bar / Wick Trap:**
   - Candle with wick > 3x body -> likely manipulation, skip signal

2. **Fake Breakout:**
   - Price breaks level but closes back inside within 2 candles
   - Require 2-candle close confirmation beyond breakout level

3. **Volume Divergence:**
   - Price makes new high but volume declining -> weak trend, skip long
   - Price makes new low but volume declining -> weak decline, skip short

4. **Sudden Spread Widening:**
   - If bid-ask spread suddenly > 3x normal -> low liquidity, don't trade

5. **Pump & Dump Detection (altcoins):**
   - Price up > 10% in 5 minutes with no news -> likely pump, don't chase
   - Wait for dump phase, potentially short

**Interface:**
```python
class AntiTrap:
    def filter_signal(self, signal: TradeSignal) -> TradeSignal | None:
        """Returns None if signal is likely a trap"""
    def get_trap_warnings(self, symbol: str) -> list[TrapWarning]:
        """Active trap warnings"""
```

#### RiskManager (risk_manager.py)

**Purpose:** Position sizing, stop loss management, and portfolio risk control.

**Rules:**
- Max risk per trade: 2% of capital (at $100, risk max $2 per trade)
- Max concurrent positions: 3
- Max correlation exposure: if BTC and ETH both long, count as 1.5x exposure
- Position sizing formula: `size = (capital * risk_pct) / (entry - stop_loss)`
- Dynamic leverage: confidence > 0.8 -> 10x, confidence 0.5-0.8 -> 5x, confidence < 0.5 -> no trade

**Stop Loss Types:**
- Initial stop: set at entry based on ATR (1.5x ATR from entry)
- Break-even stop: move stop to entry after 1:1 R:R achieved
- Trailing stop: trail at 2x ATR once in profit

**Interface:**
```python
class RiskManager:
    def validate(self, signal: TradeSignal, portfolio: Portfolio) -> ValidatedOrder | None:
        """Validate signal against risk rules, return sized order or None"""
    def update_stops(self, positions: list[Position]) -> list[StopUpdate]:
        """Update trailing stops for open positions"""
    def get_portfolio_risk(self) -> PortfolioRisk:
        """Current portfolio risk metrics"""
```

#### FeeOptimizer (fee_optimizer.py)

**Purpose:** Minimize trading fees to preserve profits.

**Strategies:**
- Prefer limit orders (Maker fee: 0.02%) over market orders (Taker fee: 0.04%)
- For non-urgent entries: place limit order at current price, wait up to 30 seconds
- For urgent entries (liquidation hunter, breakout): accept market order fee
- Track total fees paid and report in dashboard
- If BNB balance available, auto-enable BNB fee discount (25% off)

**Fee Budget:**
- Daily fee budget: max 0.5% of capital
- If exceeded, reduce trading frequency for rest of day

**Interface:**
```python
class FeeOptimizer:
    def optimize_order_type(self, signal: TradeSignal, urgency: str) -> OrderType:
        """LIMIT or MARKET based on urgency and fee budget"""
    def get_fee_stats(self) -> FeeStats:
        """Today's fee consumption"""
    def within_budget(self) -> bool:
        """Whether daily fee budget allows more trades"""
```

---

### Layer 5: Execution

#### SmartOrder (smart_order.py)

**Purpose:** Intelligent order execution to optimize entry/exit prices.

**Entry Strategies:**
- **Single entry:** For small positions or urgent signals
- **DCA entry (3 tranches):** Split into 3 orders at -0.1%, -0.3%, -0.5% from signal price
- **Iceberg:** For larger positions (when capital grows), hide order size

**Exit Strategies:**
- **Trailing take-profit:** Move TP up as price moves in favor
- **Scaled exit (3 tranches):**
  - TP1 at 1:1 R:R -> close 30%
  - TP2 at 2:1 R:R -> close 30%
  - TP3: trailing stop on remaining 40%
- **Time-based exit:** If position flat after 4 hours, close (avoiding chop)

**Interface:**
```python
class SmartOrder:
    def plan_execution(self, order: ValidatedOrder) -> ExecutionPlan:
        """Create multi-step execution plan"""
    def get_active_plans(self) -> list[ExecutionPlan]:
        """Currently executing plans"""
```

#### Executor (executor.py)

**Purpose:** Direct interface with Binance API for order execution.

**Responsibilities:**
- Place/cancel/modify orders via Binance Futures API
- Order status tracking and fill confirmation
- Handle partial fills gracefully
- Retry logic for transient API errors (max 3 retries with exponential backoff)
- Order reconciliation: compare local state with exchange state every 60s

**API Library:** `ccxt` for REST, `python-binance` for WebSocket streams

**Interface:**
```python
class Executor:
    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute an order plan"""
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
    async def get_positions(self) -> list[Position]:
        """Current open positions from exchange"""
    async def reconcile(self) -> list[Discrepancy]:
        """Compare local state with exchange"""
```

#### EmergencyShield (emergency_shield.py)

**Purpose:** Last-resort protection against catastrophic losses.

**Triggers:**
- Daily loss > 10% of capital -> HALT trading for 24 hours
- Total drawdown > 30% from peak -> CLOSE ALL positions, notify user, require manual restart
- Binance API returning errors for > 2 minutes -> CLOSE ALL positions
- Network disconnected for > 1 minute while positions are open -> CLOSE ALL

**Actions on Trigger:**
1. Cancel all pending orders
2. Market-close all open positions
3. Send emergency notification
4. Log event with full context
5. Enter cooldown period

**Interface:**
```python
class EmergencyShield:
    def check(self, portfolio: Portfolio) -> ShieldAction:
        """Returns CONTINUE, HALT, or EMERGENCY_CLOSE"""
    def is_in_cooldown(self) -> bool:
        """Whether shield has been triggered and in cooldown"""
    def reset(self) -> None:
        """Manual reset after emergency (requires explicit call)"""
```

#### RecoveryMode (recovery_mode.py)

**Purpose:** Adaptive behavior during drawdown periods (before emergency triggers).

**States:**
- NORMAL: Drawdown < 5% -> full trading
- CAUTIOUS: Drawdown 5-10% -> reduce leverage to 3x, only highest confidence signals
- RECOVERY: Drawdown 10-20% -> reduce leverage to 2x, only MultiTimeframe score >= 8
- CRITICAL: Drawdown 20-30% -> minimal trading, 1x leverage, only funding rate arb
- EMERGENCY: Drawdown > 30% -> handled by EmergencyShield

**Behavior:**
- Track peak equity and current equity
- Gradually restore normal trading as drawdown recovers
- Log recovery progress

**Interface:**
```python
class RecoveryMode:
    def assess_state(self, portfolio: Portfolio) -> RecoveryState:
        """Current recovery state"""
    def adjust_parameters(self, params: TradingParams) -> TradingParams:
        """Modify leverage, confidence thresholds based on state"""
```

---

### Layer 6: Growth & Evolution

#### CompoundEngine (compound_engine.py)

**Purpose:** Optimize capital growth through intelligent compounding.

**Mechanism:**
- After each profitable trade, recalculate position sizes based on new equity
- Kelly Criterion for optimal bet sizing: `f = (bp - q) / b`
  - b = average win/loss ratio
  - p = win probability
  - q = 1 - p
  - Use half-Kelly (f/2) for safety
- Profit lock: When equity reaches milestones, lock a portion:
  - $150: lock $20 (never risk it)
  - $200: lock $50
  - $500: lock $150
  - Locked capital excluded from position sizing

**Interface:**
```python
class CompoundEngine:
    def update_position_sizing(self, portfolio: Portfolio) -> PositionSizing:
        """Recalculate position sizes after equity change"""
    def get_kelly_fraction(self, strategy: str) -> float:
        """Optimal bet size for a strategy"""
    def get_locked_capital(self) -> float:
        """Capital locked and protected from trading"""
```

#### Evolver (evolver.py)

**Purpose:** Daily automated optimization of all system parameters.

**What It Optimizes:**
1. Strategy parameters (EMA periods, RSI thresholds, BB width, etc.)
2. Strategy weights (allocate more capital to winning strategies)
3. Coin universe (add/remove altcoins based on performance)
4. Leverage levels (per-regime, per-session)
5. Stop loss / take profit distances
6. Signal confidence thresholds

**Optimization Method:**
- Walk-forward optimization (train on 30 days, validate on 7 days)
- Parameter grid search with Bayesian optimization for efficiency
- Fitness function: Sharpe Ratio * sqrt(trade_count) (reward consistency, not just returns)
- Anti-overfitting: parameter changes limited to 20% per day (smooth evolution)

**Evolution Schedule:**
- Daily at 00:00 UTC: full optimization cycle (~5-10 min on Mac)
- Weekly: deeper analysis with Monte Carlo simulation
- Monthly: strategy review, potentially add new strategy variants

**Interface:**
```python
class Evolver:
    def run_daily_evolution(self) -> EvolutionReport:
        """Full daily optimization cycle"""
    def run_weekly_deep_analysis(self) -> WeeklyReport:
        """Deep Monte Carlo analysis"""
    def get_current_config(self) -> SystemConfig:
        """Current optimized configuration"""
```

#### BacktestLab (backtest_lab.py)

**Purpose:** Rigorous backtesting infrastructure to validate strategies.

**Features:**
- Realistic simulation: include slippage (0.05%), fees (maker/taker), funding rates
- Walk-forward validation: never test on training data
- Monte Carlo simulation: randomize trade order 1000x, check worst-case drawdown
- Market impact modeling: for larger positions (when capital grows)
- Multi-asset backtesting: test portfolio-level performance

**Output Metrics:**
- Total return, Sharpe ratio, Sortino ratio, max drawdown
- Win rate, average win/loss, profit factor
- Worst streak, best streak
- Monthly return breakdown

**Interface:**
```python
class BacktestLab:
    def run_backtest(self, strategy: Strategy, data: pd.DataFrame, config: dict) -> BacktestResult:
        """Run single backtest"""
    def run_walk_forward(self, strategy: Strategy, train_days: int, test_days: int) -> WalkForwardResult:
        """Walk-forward optimization and validation"""
    def run_monte_carlo(self, trades: list[Trade], iterations: int = 1000) -> MonteCarloResult:
        """Monte Carlo simulation on trade sequence"""
```

---

### Layer 7: Monitoring

#### Monitor (monitor.py)

**Purpose:** Local web dashboard for real-time system monitoring.

**Dashboard (Flask/Streamlit, localhost:8080):**

**Page 1 - Overview:**
- Current equity and P&L (daily, weekly, total)
- Equity curve chart
- Open positions with unrealized P&L
- System health status (all module statuses)

**Page 2 - Trades:**
- Trade history table (entry, exit, P&L, strategy, duration)
- Win rate by strategy, by coin, by session
- Fee analysis

**Page 3 - Evolution:**
- Current strategy weights
- Parameter change history
- Backtest results from last evolution
- Coin universe changes

**Page 4 - Signals:**
- Real-time signal feed from all modules
- Market regime indicator
- Sentiment gauges
- Whale activity log

**Interface:**
```python
class Monitor:
    def start(self, port: int = 8080) -> None:
        """Start dashboard web server"""
    def update(self, system_state: SystemState) -> None:
        """Update dashboard with latest state"""
```

#### Notifier (notifier.py)

**Purpose:** Push notifications for important events.

**Channels (user selects one):**
- Telegram Bot (recommended, free, easy setup)
- macOS native notifications (always enabled as backup)

**Notification Types:**
- TRADE_OPEN: "Opened LONG BTC/USDT @ 65,000 | 10x | Size: $50"
- TRADE_CLOSE: "Closed LONG BTC/USDT @ 66,500 | P&L: +$7.50 (+15%)"
- STOP_HIT: "Stop loss triggered BTC/USDT | P&L: -$2.00 (-2%)"
- EMERGENCY: "EMERGENCY SHIELD ACTIVATED | Daily loss: -12%"
- EVOLUTION: "Daily evolution complete | Top strategy: TrendFollower (weight: 35%)"
- MILESTONE: "New equity high: $250.00 (+150%)"

**Interface:**
```python
class Notifier:
    def send(self, notification: Notification) -> None:
        """Send notification through configured channel"""
    def configure_telegram(self, bot_token: str, chat_id: str) -> None:
        """Setup Telegram notifications"""
```

---

## Database Schema (SQLite)

```sql
-- Trade history
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,  -- LONG or SHORT
    entry_price REAL NOT NULL,
    exit_price REAL,
    quantity REAL NOT NULL,
    leverage INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    pnl REAL,
    fees REAL,
    status TEXT DEFAULT 'OPEN'  -- OPEN, CLOSED, STOPPED, LIQUIDATED
);

-- Equity snapshots (for curve and drawdown tracking)
CREATE TABLE equity_snapshots (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    equity REAL NOT NULL,
    unrealized_pnl REAL,
    locked_capital REAL DEFAULT 0
);

-- Strategy performance tracking
CREATE TABLE strategy_performance (
    id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL,
    date DATE NOT NULL,
    trades INTEGER,
    wins INTEGER,
    total_pnl REAL,
    sharpe_ratio REAL,
    weight REAL
);

-- Evolution history
CREATE TABLE evolution_log (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    parameters_before JSON,
    parameters_after JSON,
    backtest_sharpe REAL,
    changes_summary TEXT
);

-- Market data cache
CREATE TABLE klines (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    open_time TIMESTAMP NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, interval, open_time)
);

-- Whale events log
CREATE TABLE whale_events (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    event_type TEXT,
    symbol TEXT,
    amount REAL,
    direction TEXT
);

-- System health log
CREATE TABLE system_health (
    id INTEGER PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    status TEXT,
    api_latency_ms REAL,
    memory_mb REAL,
    active_modules INTEGER,
    details TEXT
);
```

---

## Project Structure

```
crypto-beast/
├── main.py                      # Entry point, main loop orchestration
├── config.py                    # Configuration management
├── requirements.txt             # Python dependencies
├── .env                         # API keys (gitignored)
├── .env.example                 # Template for API keys
│
├── core/                        # Core infrastructure
│   ├── __init__.py
│   ├── system_guard.py          # SystemGuard
│   ├── database.py              # SQLite connection and helpers
│   └── models.py                # Shared data models (Signal, Trade, Position, etc.)
│
├── data/                        # Layer 1: Data & Intelligence
│   ├── __init__.py
│   ├── data_feed.py             # DataFeed
│   ├── whale_tracker.py         # WhaleTracker
│   ├── sentiment_radar.py       # SentimentRadar
│   ├── liquidation_hunter.py    # LiquidationHunter
│   └── orderbook_sniper.py      # OrderBookSniper
│
├── analysis/                    # Layer 2: Analysis
│   ├── __init__.py
│   ├── market_regime.py         # MarketRegimeDetector
│   ├── event_engine.py          # EventEngine
│   ├── altcoin_radar.py         # AltcoinRadar
│   ├── pattern_scanner.py       # PatternScanner
│   ├── session_trader.py        # SessionTrader
│   └── multi_timeframe.py       # MultiTimeframe
│
├── strategy/                    # Layer 3: Strategy
│   ├── __init__.py
│   ├── strategy_engine.py       # StrategyEngine (orchestrator)
│   ├── trend_follower.py        # TrendFollower strategy
│   ├── mean_reversion.py        # MeanReversion strategy
│   ├── momentum.py              # Momentum strategy
│   ├── breakout.py              # Breakout strategy
│   ├── scalper.py               # Scalper strategy
│   └── funding_rate_arb.py      # FundingRateArb
│
├── defense/                     # Layer 4: Filter & Defense
│   ├── __init__.py
│   ├── anti_trap.py             # AntiTrap
│   ├── risk_manager.py          # RiskManager
│   └── fee_optimizer.py         # FeeOptimizer
│
├── execution/                   # Layer 5: Execution
│   ├── __init__.py
│   ├── smart_order.py           # SmartOrder
│   ├── executor.py              # Executor (live trading)
│   ├── paper_executor.py        # PaperExecutor (simulated trading)
│   ├── emergency_shield.py      # EmergencyShield
│   └── recovery_mode.py         # RecoveryMode
│
├── evolution/                   # Layer 6: Growth & Evolution
│   ├── __init__.py
│   ├── compound_engine.py       # CompoundEngine
│   ├── evolver.py               # Evolver
│   └── backtest_lab.py          # BacktestLab
│
├── monitoring/                  # Layer 7: Monitoring
│   ├── __init__.py
│   ├── monitor.py               # Monitor (Dashboard)
│   ├── notifier.py              # Notifier
│   └── templates/               # Dashboard HTML templates
│       └── index.html
│
├── tests/                       # Test suite
│   ├── __init__.py
│   ├── test_strategies.py
│   ├── test_risk_manager.py
│   ├── test_backtest_lab.py
│   ├── test_executor.py
│   └── test_integration.py
│
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-03-15-crypto-beast-design.md  # This document
```

---

## Dependencies

```
# Core
ccxt>=4.0                    # Exchange API (Binance)
python-binance>=1.0          # Binance-specific WebSocket support

# Data & Analysis
pandas>=2.0                  # Data manipulation
numpy>=1.24                  # Numerical computing
ta>=0.11                     # Technical analysis indicators

# Backtesting & Optimization
scipy>=1.11                  # Optimization algorithms
optuna>=3.4                  # Bayesian hyperparameter optimization

# Dashboard
streamlit>=1.30              # Web dashboard

# Notifications
python-telegram-bot>=20.0    # Telegram notifications

# Database
# sqlite3 (built-in)

# Utilities
python-dotenv>=1.0           # Environment variables
schedule>=1.2                # Task scheduling
aiohttp>=3.9                 # Async HTTP
websockets>=12.0             # WebSocket connections
loguru>=0.7                  # Logging
```

---

## Configuration

```python
# config.py defaults
DEFAULT_CONFIG = {
    # Capital
    "starting_capital": 100.0,
    "capital_allocation": {"BTC": 0.6, "altcoins": 0.4},

    # Leverage
    "leverage": {"high_confidence": 10, "medium_confidence": 5, "low_confidence": 0},
    "max_leverage": 10,

    # Risk
    "max_risk_per_trade": 0.02,       # 2% of capital
    "max_concurrent_positions": 3,
    "max_daily_loss": 0.10,            # 10% -> halt
    "max_total_drawdown": 0.30,        # 30% -> emergency

    # Recovery thresholds
    "recovery_cautious": 0.05,         # 5% drawdown
    "recovery_recovery": 0.10,         # 10% drawdown
    "recovery_critical": 0.20,         # 20% drawdown

    # Fees
    "maker_fee": 0.0002,               # 0.02%
    "taker_fee": 0.0004,               # 0.04%
    "daily_fee_budget": 0.005,         # 0.5% of capital

    # Evolution
    "evolution_time_utc": "00:00",
    "backtest_train_days": 30,
    "backtest_test_days": 7,
    "max_param_change_pct": 0.20,      # 20% max change per evolution

    # Compound
    "kelly_fraction": 0.5,             # Half-Kelly
    "profit_lock_milestones": {150: 20, 200: 50, 500: 150},

    # MultiTimeframe
    "mtf_min_confluence": 6,           # Min score to trade

    # System
    "main_loop_interval": 5,           # seconds
    "api_latency_warn": 500,           # ms
    "api_latency_halt": 2000,          # ms
    "dashboard_port": 8080,
}
```

---

## Startup & Launch Sequence

```
1. Load .env (API keys)
2. Load config (with Evolver overrides from last session)
3. Initialize SQLite database
4. SystemGuard.start() -> health check
5. DataFeed.connect() -> establish WebSocket
6. Load all modules with last saved parameters
7. Verify Binance API connectivity and permissions
8. Check account balance (confirm >= configured capital)
9. Reconcile: check for any open positions from previous session
10. Start Monitor dashboard
11. Enter main loop
12. Log: "CRYPTO BEAST v1.0 ONLINE"
```

---

## Pre-Launch Checklist (before going live with $100)

- [ ] All modules pass unit tests
- [ ] Integration test: full pipeline with mock exchange
- [ ] Paper trading: 7+ days of simulated trading with no crashes
- [ ] Backtest validation: positive Sharpe ratio on walk-forward test
- [ ] Emergency shield test: manually trigger each emergency scenario
- [ ] Network failure test: disconnect and verify graceful handling
- [ ] API permission verification: futures trading enabled on Binance
- [ ] Notification test: confirm Telegram/notifications working
- [ ] Review all stop loss logic manually
- [ ] Verify fee calculations match Binance actual fees

---

## Appendix A: Shared Data Models (core/models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

# === Enums ===

class Direction(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class SignalType(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class MarketRegime(Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"

class RecoveryState(Enum):
    NORMAL = "NORMAL"
    CAUTIOUS = "CAUTIOUS"
    RECOVERY = "RECOVERY"
    CRITICAL = "CRITICAL"

class SystemStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"

class ShieldAction(Enum):
    CONTINUE = "CONTINUE"
    HALT = "HALT"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"

class OrderType(Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

# === Data Layer Signals (Layer 1 output) ===

@dataclass
class DirectionalBias:
    """Output from Layer 1 data modules (Whale, Sentiment, Liquidation, OrderBook)."""
    source: str              # e.g., "whale_tracker", "sentiment_radar"
    symbol: str
    direction: SignalType    # BULLISH, BEARISH, NEUTRAL
    confidence: float        # 0.0 to 1.0
    reason: str              # Human-readable explanation
    timestamp: datetime = field(default_factory=datetime.utcnow)

# === Strategy Layer Signals (Layer 3 output) ===

@dataclass
class TradeSignal:
    """Actionable trade signal from StrategyEngine."""
    symbol: str
    direction: Direction     # LONG or SHORT
    confidence: float        # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    strategy: str            # Which strategy generated this
    regime: MarketRegime     # Market regime at signal time
    timeframe_score: int     # MultiTimeframe confluence score
    timestamp: datetime = field(default_factory=datetime.utcnow)

# === Validated Order (Layer 4 output) ===

@dataclass
class ValidatedOrder:
    """Trade signal after passing RiskManager validation."""
    signal: TradeSignal
    quantity: float          # Position size (in base currency)
    leverage: int            # Actual leverage to use
    order_type: OrderType    # LIMIT or MARKET
    risk_amount: float       # Dollar amount at risk
    max_slippage: float      # Maximum acceptable slippage (0.001 = 0.1%)

# === Execution Types ===

@dataclass
class ExecutionPlan:
    """Multi-step execution plan from SmartOrder."""
    order: ValidatedOrder
    entry_tranches: list[dict]    # [{price, quantity, type}]
    exit_tranches: list[dict]     # [{price, quantity, trigger}]
    trailing_stop: Optional[dict] = None
    time_limit_hours: float = 4.0

@dataclass
class ExecutionResult:
    """Result from Executor."""
    success: bool
    order_ids: list[str]
    avg_fill_price: float
    total_filled: float
    fees_paid: float
    slippage: float          # Actual vs expected entry
    error: Optional[str] = None

# === Portfolio & Position ===

@dataclass
class Position:
    """Open position on exchange."""
    symbol: str
    direction: Direction
    entry_price: float
    quantity: float
    leverage: int
    unrealized_pnl: float
    strategy: str
    entry_time: datetime
    current_stop: float
    order_ids: list[str] = field(default_factory=list)

@dataclass
class Portfolio:
    """Current portfolio state."""
    equity: float
    available_balance: float
    positions: list[Position]
    peak_equity: float
    locked_capital: float
    daily_pnl: float
    total_fees_today: float
    drawdown_pct: float      # Current drawdown from peak

@dataclass
class PositionSizing:
    """Position sizing parameters from CompoundEngine."""
    available_capital: float    # Capital available for new trades
    kelly_fractions: dict       # {strategy_name: fraction}
    max_position_pct: float     # Max % of capital per position

# === Analysis Types ===

@dataclass
class ConfluenceScore:
    """Multi-timeframe confluence result."""
    symbol: str
    score: int               # -10 to +10
    direction: SignalType    # Overall direction
    breakdown: dict          # {timeframe: vote}

@dataclass
class Pattern:
    """Detected chart pattern."""
    name: str                # e.g., "double_bottom"
    symbol: str
    timeframe: str
    direction: Direction
    target_price: float
    stop_price: float
    confidence: float
    detected_at: datetime = field(default_factory=datetime.utcnow)

# === Market Data ===

@dataclass
class MarketData:
    """Aggregated market data snapshot for one symbol."""
    symbol: str
    klines: dict             # {timeframe: pd.DataFrame}
    orderbook: dict          # {bids: [], asks: []}
    ticker: dict             # {price, volume_24h, change_24h}
    funding_rate: float
    open_interest: float

@dataclass
class OrderBook:
    """Order book snapshot."""
    symbol: str
    bids: list[list[float]]  # [[price, quantity], ...]
    asks: list[list[float]]
    timestamp: datetime

# === System Types ===

@dataclass
class SystemState:
    """Full system state for Monitor."""
    status: SystemStatus
    recovery_state: RecoveryState
    portfolio: Portfolio
    active_signals: list[TradeSignal]
    biases: list[DirectionalBias]
    regime: dict             # {symbol: MarketRegime}
    strategy_weights: dict   # {strategy: weight}
    api_latency_ms: float
    uptime_seconds: float
```

---

## Appendix B: Architecture Decisions

### B1: Async Architecture

**Decision:** Full asyncio application using `asyncio.run()`.

All modules use `async` interfaces. The main loop is an async function:

```python
async def main_loop():
    while True:
        if not system_guard.should_trade():
            await asyncio.sleep(5)
            continue

        # Lock prevents new trades during emergency
        async with trading_lock:
            data = await data_feed.fetch()
            biases = await asyncio.gather(
                whale_tracker.update(),
                sentiment_radar.update(),
                liquidation_hunter.update(),
                orderbook_sniper.update(),
            )
            # ... pipeline continues

        await asyncio.sleep(config.main_loop_interval)
```

External API calls (Whale Alert, sentiment, economic calendar) run on **independent timers** with caching, NOT in the main 5-second loop:

```python
# Slow external APIs update on their own schedule, cache results
class WhaleTracker:
    UPDATE_INTERVAL = 60  # seconds, not every 5s

    async def _background_updater(self):
        """Runs independently, caches results"""
        while True:
            try:
                self._cached_events = await self._fetch_whale_alert()
            except Exception:
                pass  # Use stale cache, log warning
            await asyncio.sleep(self.UPDATE_INTERVAL)

    async def update(self) -> list[WhaleEvent]:
        """Returns cached data, never blocks main loop"""
        return self._cached_events
```

### B2: Exchange Library

**Decision:** Use `ccxt` as the primary library for all REST API calls. Use `python-binance` only for WebSocket streams (liquidation, klines, order book).

Rationale: ccxt provides a unified interface and makes future multi-exchange support easier. python-binance has better WebSocket support for Binance-specific streams.

### B3: AltcoinRadar Fast Path

The BTC-altcoin lag strategy bypasses the full pipeline:

```python
async def altcoin_fast_path(btc_move: float):
    """Dedicated fast path, runs outside main loop on BTC price change events"""
    if abs(btc_move) < 0.005:  # < 0.5% move, ignore
        return
    signals = altcoin_radar.get_beta_signal(btc_move)
    for signal in signals:
        # Skip MultiTimeframe, AntiTrap — speed matters
        # Still go through RiskManager (non-negotiable)
        order = risk_manager.validate_fast(signal, portfolio)
        if order:
            await executor.execute_market(order)  # Always market order
```

### B4: Evolver Atomic Swap

Parameter updates are atomic — computed in background, swapped between main loop iterations:

```python
class Evolver:
    async def run_daily_evolution(self):
        # Compute new params (takes minutes, doesn't affect live trading)
        new_config = await self._optimize()

        # Atomic swap: main loop checks this flag
        self._pending_config = new_config

    def apply_if_pending(self):
        """Called by main loop between iterations"""
        if self._pending_config:
            self._active_config = self._pending_config
            self._pending_config = None
            return True
        return False
```

### B5: Centralized Rate Limiter

All Binance API calls go through a single rate limiter:

```python
class BinanceRateLimiter:
    """Centralized rate limiter for all Binance API calls."""
    ORDER_LIMIT = 1200      # per minute
    DATA_LIMIT = 2400       # per minute

    async def acquire_order_slot(self) -> bool:
        """Wait for available order rate limit slot"""
    async def acquire_data_slot(self) -> bool:
        """Wait for available data rate limit slot"""
    def get_usage(self) -> dict:
        """Current rate limit usage"""
```

All modules receive the shared rate limiter instance at initialization.

### B6: SQLite WAL Mode & Writes

```python
# database.py initialization
connection.execute("PRAGMA journal_mode=WAL")
connection.execute("PRAGMA busy_timeout=5000")
```

All writes go through a single async write queue to prevent contention:

```python
class Database:
    async def write(self, query: str, params: tuple):
        """All writes are serialized through this queue"""
        await self._write_queue.put((query, params))
```

---

## Appendix C: Paper Trading Mode

A `PaperExecutor` implements the same interface as `Executor` but simulates fills locally:

```python
class PaperExecutor(Executor):
    """Simulates order execution without touching Binance."""

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Simulate fill at current market price + simulated slippage"""
        current_price = self.data_feed.get_ticker(plan.order.signal.symbol).price
        slippage = random.uniform(0, 0.001)  # 0-0.1% simulated slippage
        fill_price = current_price * (1 + slippage if plan.order.signal.direction == Direction.LONG else 1 - slippage)

        # Record in database with paper_trade flag
        # Track P&L as if real
        return ExecutionResult(
            success=True,
            order_ids=[f"PAPER-{uuid4()}"],
            avg_fill_price=fill_price,
            total_filled=plan.order.quantity,
            fees_paid=plan.order.quantity * fill_price * 0.0004,
            slippage=slippage,
        )
```

**Startup flag:** `python main.py --paper` uses PaperExecutor instead of real Executor.

---

## Appendix D: Graceful Shutdown

```python
import signal

class GracefulShutdown:
    def __init__(self):
        signal.signal(signal.SIGINT, self._handle)
        signal.signal(signal.SIGTERM, self._handle)
        self.shutting_down = False

    def _handle(self, signum, frame):
        self.shutting_down = True

# In main loop:
async def shutdown_sequence():
    """Ordered shutdown procedure"""
    logger.warning("SHUTDOWN INITIATED")

    # 1. Stop accepting new signals
    strategy_engine.pause()

    # 2. Cancel all pending orders on exchange
    await executor.cancel_all_pending()

    # 3. Close all open positions (market orders)
    positions = await executor.get_positions()
    for pos in positions:
        await executor.close_position(pos, order_type=OrderType.MARKET)

    # 4. Save current state
    evolver.save_current_config()
    database.flush()

    # 5. Send notification
    notifier.send(Notification(type="SHUTDOWN", message="Crypto Beast shutdown complete. All positions closed."))

    # 6. Close connections
    await data_feed.disconnect()

    logger.info("SHUTDOWN COMPLETE")
```

---

## Appendix E: Security Requirements

### API Key Configuration
- **Futures trading:** ENABLED
- **Spot trading:** Not needed, can be disabled
- **Withdrawals:** MUST BE DISABLED — the bot never needs to withdraw
- **IP restriction:** Restrict to the Mac's public IP (and any VPN IP if used)

### Credential Storage
- API key and secret in `.env` file with `chmod 600` (owner read/write only)
- `.env` in `.gitignore` — never committed
- Telegram bot token in same `.env` file
- Future improvement: migrate to macOS Keychain via `keyring` library

### Dashboard Security
- Bind to `127.0.0.1` only (not `0.0.0.0`) — no external access
- No authentication needed when bound to localhost only

---

## Appendix F: Operational Requirements

### macOS Sleep Prevention
```bash
# The system must run with caffeinate to prevent sleep:
caffeinate -dims python main.py
```
This prevents display sleep (-d), idle sleep (-i), disk sleep (-m), and system sleep (-s).

### Logging
- Library: `loguru`
- Log file: `logs/crypto_beast_{date}.log`
- Rotation: 50MB per file, keep 30 days
- Format: `{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {module}:{function}:{line} | {message}`
- Levels: DEBUG for development, INFO for production
- Trade-related logs: always INFO level (never miss a trade log)

### Database Backup
- Daily backup at 00:30 UTC (after evolution completes): `cp crypto_beast.db backups/crypto_beast_{date}.db`
- Keep 30 days of backups
- Backup before any Evolver parameter change

### Binance Minimum Order Sizes
- BTC/USDT: min notional $5
- Most altcoins: min notional $5-$20
- At startup: validate that `capital * risk_per_trade * leverage >= min_notional` for all tracked symbols
- In CRITICAL recovery state (1x leverage): may not meet minimums for altcoins — system should automatically skip those and trade only BTC

### Time Synchronization
- Use Binance server time as reference: `GET /fapi/v1/time`
- Compare with local time at startup; warn if drift > 1 second
- All timestamps in database stored as UTC

---

## Risk Disclaimer

This system uses leveraged trading which carries substantial risk. The $100 starting capital could be entirely lost. Past backtesting performance does not guarantee future results. The "self-evolving" nature means the system will adapt, but markets can change in ways that no historical data can predict. This system is built for educational purposes and autonomous trading experimentation. Trade at your own risk.
