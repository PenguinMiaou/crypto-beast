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

# === Trade Review Types ===

class LossCategory(Enum):
    STOP_TOO_TIGHT = "STOP_TOO_TIGHT"
    AGAINST_TREND = "AGAINST_TREND"
    FAKE_SIGNAL = "FAKE_SIGNAL"
    BAD_TIMING = "BAD_TIMING"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    FEE_EROSION = "FEE_EROSION"
    CORRELATION_LOSS = "CORRELATION_LOSS"
    EVENT_IMPACT = "EVENT_IMPACT"

@dataclass
class LossClassification:
    trade_id: int
    category: LossCategory
    confidence: float
    evidence: str
    recommendation: str

@dataclass
class WinProfile:
    regime: MarketRegime
    session: str
    confluence_score: int
    key_signals: list[str]
    capture_efficiency: float

@dataclass
class ReviewReport:
    period: str
    timestamp: datetime
    total_trades: int
    wins: int
    losses: int
    loss_classifications: list[LossClassification]
    win_profiles: list[WinProfile]
    recommendations: list[str]
    hypothetical_results: dict

# === Backtest Types ===

@dataclass
class BacktestResult:
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    total_trades: int
    trades: list  # [{entry, exit, pnl, fees, ...}]

@dataclass
class WalkForwardResult:
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    best_params: dict
    is_valid: bool  # True if OOS sharpe > 0

@dataclass
class MonteCarloResult:
    median_return: float
    worst_case_drawdown: float  # 5th percentile
    probability_of_ruin: float  # % of simulations that hit max_drawdown
    confidence_95_return: float

# === Evolution Types ===

@dataclass
class EvolutionReport:
    timestamp: datetime
    parameters_changed: dict  # {param: {old: x, new: y}}
    backtest_sharpe_before: float
    backtest_sharpe_after: float
    strategy_weights: dict
    recommendations_applied: list

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
