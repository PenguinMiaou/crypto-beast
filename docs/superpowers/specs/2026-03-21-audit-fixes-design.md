# Crypto Beast v1.6.0 — 系统审查修复设计文档

> 日期：2026-03-21
> 版本：v1.5.7 → v1.6.0
> 目标：修复 5 位专家审查发现的 18 项问题，实现稳定暴利

## 1. 背景与动机

Crypto Beast 是运行在 Binance USDT-M Futures（hedge mode）上的 7 层异步交易系统，当前资金约 $200。经过量化策略、风控资金管理、执行微观结构、市场数据信号、系统架构 5 个维度的专家审查，发现系统综合评分仅 5.5/10。

**根因**：`strategy_engine.py` 中 confidence × weight(0.2) 的乘法导致信号被压碎到 0.05-0.2，整个交易链路近乎瘫痪。修复此问题后，其余 17 项优化才能发挥作用。

## 2. 修复清单总览

| # | 类别 | 修复项 | 优先级 | 影响文件 |
|---|------|--------|--------|----------|
| 1 | 信号 | 修复 confidence 权重乘法 | P0 | `strategy/strategy_engine.py` |
| 2 | 执行 | 移除 LIMIT 单入场覆盖 | P0 | `crypto_system.py` |
| 3 | 风控 | 添加方向暴露上限 | P0 | `risk/risk_manager.py` |
| 4 | 架构 | 修复 aiohttp session 泄漏 | P0 | `execution/executor.py` |
| 5 | 架构 | 修复 circuit breaker 文件锁 | P0 | `crypto_system.py` |
| 6 | 策略 | SL/TP 比例优化 | P1 | `strategy/*.py` |
| 7 | 风控 | 添加 48h 超时平仓 | P1 | `execution/position_manager.py` |
| 8 | 执行 | 利润保护参数优化 | P1 | `config.py`, `execution/position_manager.py` |
| 9 | 风控 | 连续仓位缩放 + base_risk 提升 | P1 | `risk/risk_manager.py`, `config.py` |
| 10 | 信号 | 降低 intel 伪数据调整量 | P1 | `crypto_system.py` |
| 11 | 风控 | HALT 缩短 + CAUTIOUS 阈值调整 | P1 | `defense/defense_manager.py`, `config.py` |
| 12 | 架构 | 合并双重 API 调用 | P1 | `crypto_system.py` |
| 13 | 数据 | 接入 WebSocket 真实数据 | P2 | 新建 `data/ws_manager.py`, 改 `data/*.py` |
| 14 | 信号 | MTF 投票改为梯度 | P2 | `analysis/multi_timeframe.py` |
| 15 | 策略 | Confidence 动态计算 | P2 | `strategy/*.py` |
| 16 | 执行 | 动态 SL 移到保本 | P2 | `execution/position_manager.py` |
| 17 | 架构 | watchdog↔bot 通信改 Unix socket | P2 | `crypto_guardian.py`, `crypto_system.py` |
| 18 | 架构 | Binance User Data Stream | P2 | 新建 `data/user_data_stream.py` |

## 3. 详细设计

---

### 3.1 #1 修复 confidence 权重乘法

**文件**：`strategy/strategy_engine.py`

**问题**：第 66-67 行 `sig.confidence *= weight(0.2) * session_weight` 将策略产出的 0.3-0.95 confidence 压缩到 0.03-0.25，几乎所有信号都低于 min_confidence(0.3) 被拒绝。

**设计**：
- `_weights`（策略权重 0.2）仅用于去重排序，不乘进 confidence
- `session_weight`（0.5-1.3）保留为时段微调因子，直接乘到 confidence
- 去重逻辑改为：同 symbol 多信号时，用 `confidence * strategy_weight` 评分选最佳信号，但最终信号保留 session-adjusted confidence

**TradeSignal 修改**（`core/models.py`）：添加 `_strategy_weight` 字段：
```python
@dataclass
class TradeSignal:
    # ... 现有字段不变 ...
    _strategy_weight: float = field(default=0.2, repr=False, compare=False)
```
使用 `field(repr=False, compare=False)` 确保不影响现有的 `__repr__` 和比较逻辑。由于 `default=0.2`，现有所有创建 TradeSignal 的代码无需修改。

**generate_signals 修改**：
```python
def generate_signals(self, symbol: str, klines: pd.DataFrame) -> List[TradeSignal]:
    # ... regime, session_weights, confluence 获取不变 ...

    signals: List[TradeSignal] = []
    for name, strategy in self._strategies.items():
        raw_signals = strategy.generate(klines, symbol, regime)
        for sig in raw_signals:
            # Session weight 作为时段微调（0.5-1.3），合理范围
            session_w = session_weights.get(name, 1.0)
            sig.confidence = round(sig.confidence * session_w, 4)
            # 策略权重仅存储，用于去重排序
            sig._strategy_weight = self._weights.get(name, 0.2)
            if confluence is not None:
                sig.timeframe_score = confluence.score
            signals.append(sig)

    # 去重：同 symbol 保留 weighted score 最高的信号
    # 理由：weighted_score = confidence × strategy_weight 确保"擅长当前 regime 的策略"
    # 优先于"碰巧高 confidence 但权重低的策略"。例如趋势市中 TrendFollower(w=0.3)
    # 的 0.6 信号 (score=0.18) 应优先于 Scalper(w=0.1) 的 0.7 信号 (score=0.07)。
    # 但最终执行时使用原始 confidence（不含 weight），因此仓位大小反映信号本身质量。
    best_per_symbol: Dict[str, tuple] = {}
    for sig in signals:
        key = sig.symbol
        weighted_score = sig.confidence * sig._strategy_weight
        if key not in best_per_symbol or weighted_score > best_per_symbol[key][0]:
            best_per_symbol[key] = (weighted_score, sig)

    return sorted(
        [v[1] for v in best_per_symbol.values()],
        key=lambda s: s.confidence, reverse=True,
    )
```

**预期效果**：信号 confidence 从 0.03-0.25 恢复到 0.25-0.95（乘以 session_weight 后），中高杠杆和大仓位被解锁。

---

### 3.2 #2 移除 LIMIT 单入场覆盖

**文件**：`crypto_system.py`（约第 1008-1013 行）

**问题**：FeeOptimizer 在 confidence ≤ 0.8 时将 MARKET 覆盖为 LIMIT，但：
- LIMIT 单价格设为 signal.entry_price（当前市价），GTC 挂单可能不成交
- executedQty=0 时不放 SL → 5 分钟无保护窗口
- 小账户省的 0.02% 手续费（每单约 $0.004）不值得承担风险

**设计**：
- 移除 confidence ≤ 0.8 时的 LIMIT 覆盖逻辑
- 小账户（< $500）始终用 MARKET 单
- FeeOptimizer 的 `suggest_order_type()` 仅在大账户或 DCA 分批入场时生效

```python
# crypto_system.py 约第 1008-1013 行
# 删除以下逻辑:
# if signal.confidence <= 0.8:
#     order_type = LIMIT
#     price = entry_price
# 替换为:
# 小账户始终 MARKET，不做 LIMIT 覆盖
```

**预期效果**：消除入场未成交 + 无 SL 保护的风险。

---

### 3.3 #3 添加方向暴露上限

**文件**：`risk/risk_manager.py`

**问题**：系统允许 BTC+ETH+SOL 全部 10x LONG，等效 30x 单向暴露。BTC 闪跌 3% = 亏损 90%。

**设计**：
在 `validate()` 方法中，已有的相关性惩罚之后，添加方向暴露检查：

```python
# 新增方向暴露上限检查
MAX_DIRECTIONAL_LEVERAGE = 15  # 同方向最大等效杠杆
MAX_CORRELATED_SAME_DIR = 2    # 高相关资产同方向最多 2 个

def _check_directional_exposure(self, signal, portfolio, proposed_notional, proposed_leverage):
    """检查新信号是否会导致同方向暴露过大。"""
    same_dir_notional = sum(
        pos.quantity * pos.entry_price
        for pos in portfolio.positions
        if pos.direction == signal.direction
    )
    total_notional = same_dir_notional + proposed_notional
    max_allowed = portfolio.equity * MAX_DIRECTIONAL_LEVERAGE
    if total_notional > max_allowed:
        return False, f"directional exposure {total_notional:.0f} > limit {max_allowed:.0f}"

    # 高相关资产同方向计数
    CORRELATED_GROUPS = [{"BTCUSDT", "ETHUSDT", "SOLUSDT"}]
    for group in CORRELATED_GROUPS:
        if signal.symbol not in group:
            continue
        same_dir_count = sum(
            1 for pos in portfolio.positions
            if pos.symbol in group and pos.direction == signal.direction
        )
        if same_dir_count >= MAX_CORRELATED_SAME_DIR:
            return False, f"correlated group limit: {same_dir_count} same-dir positions"

    return True, ""
```

同时将相关性惩罚从 0.8 加强到 0.6：

```python
# 现有 L56-66
correlation_penalty = 0.6  # 从 0.8 改为 0.6
```

**配置新增**（`config.py`）：
```python
max_directional_leverage: float = 15.0
max_correlated_same_dir: int = 2
correlation_penalty: float = 0.6
```

---

### 3.4 #4 修复 aiohttp session 泄漏

**文件**：`execution/executor.py`

**问题**：`_place_algo_order()`、`cancel_algo_orders()`、`ensure_sl_orders()` 每次调用都 `async with aiohttp.ClientSession()`，24/7 运行导致连接泄漏。同时每次调用都 `dotenv_values()` 读 .env 文件。

**设计**：
- 在 `__init__` 中读取 API 凭证并缓存
- 添加懒初始化的持久 `aiohttp.ClientSession`
- 所有 algo order 方法共用同一个 session
- 添加 `close()` 方法供关闭时调用

```python
class LiveExecutor:
    def __init__(self, exchange, db, rate_limiter):
        self.exchange = exchange
        self.db = db
        self.rate_limiter = rate_limiter
        # 缓存 API 凭证
        from dotenv import dotenv_values
        env = dotenv_values(str(Path(__file__).parent.parent / ".env"))
        self._api_key = env.get("BINANCE_API_KEY", "")
        self._api_secret = env.get("BINANCE_API_SECRET", "")
        # 持久 HTTP session（懒初始化）
        self._http_session: Optional[aiohttp.ClientSession] = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self):
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
```

所有 `_place_algo_order`、`cancel_algo_orders`、`ensure_sl_orders` 中的 `async with aiohttp.ClientSession() as session:` 替换为 `session = await self._get_http_session()`，并移除函数内的 `dotenv_values()` 调用。

---

### 3.5 #5 修复 circuit breaker 文件锁

**文件**：`crypto_system.py`（约第 700-708 行）

**问题**：circuit breaker 触发时直接 `json.load/json.dump` 写 watchdog.state，没有文件锁，可能与 watchdog 的写操作冲突导致 JSON 损坏。

**设计**：
使用 `fcntl.LOCK_EX` 文件锁保护读写操作：

```python
import fcntl

def _write_watchdog_state_safe(state_path, updates):
    """原子写入 watchdog.state，使用文件锁。处理文件不存在的情况。"""
    # 确保文件存在
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
```

替换 circuit breaker 中的裸 json 读写。

---

### 3.6 #6 SL/TP 比例优化

**文件**：`strategy/scalper.py`, `strategy/mean_reversion.py`, `strategy/breakout.py`, `strategy/funding_rate_arb.py`

**问题与修复**：

| 策略 | 现状 | 修复后 | R:R 变化 |
|------|------|--------|----------|
| Scalper | SL=0.5ATR, TP=1.0ATR | SL=0.3ATR, TP=1.5ATR | 1:2 → 1:5 |
| MeanReversion | TP=BB中线 | TP=对侧BB | ~1:1 → ~1:2 |
| Breakout | SL=对侧BB | SL=entry±2.0ATR | 变量 → ~1:2 |
| FundingRateArb | SL=2ATR, TP=1.5ATR | SL=1.5ATR, TP=3.0ATR | 1:0.75 → 1:2 |
| Momentum | SL=1.5ATR, TP=3.0ATR | 不变 | 1:2（合理） |
| TrendFollower | SL=1.5ATR, TP=3.0ATR | 不变 | 1:2（合理） |

**Scalper 具体修改**：
```python
# scalper.py — SL/TP 计算
atr = ta.volatility.average_true_range(high, low, close, window=14).iloc[-1]
if direction == "LONG":
    stop_loss = close - 0.3 * atr   # 从 0.5 收紧到 0.3
    take_profit = close + 1.5 * atr  # 从 1.0 扩大到 1.5
```

**MeanReversion 具体修改**：
```python
# mean_reversion.py — TP 改为对侧 BB
if direction == "LONG":
    take_profit = upper_band  # 从 middle 改为 upper
elif direction == "SHORT":
    take_profit = lower_band  # 从 middle 改为 lower
```

**FundingRateArb 具体修改**：
```python
# funding_rate_arb.py — 修正 R:R 倒挂
stop_loss_distance = atr * 1.5   # 从 2.0 收紧
take_profit_distance = atr * 3.0  # 从 1.5 扩大
```

**Breakout 具体修改**：
```python
# breakout.py — SL 改用 ATR
if direction == "LONG":
    stop_loss = entry_price - 2.0 * atr  # 从对侧 BB 改为 ATR
```

**设计原则**：所有策略 R:R ≥ 1:2，Scalper 1:5 补偿低胜率。

---

### 3.7 #7 添加 48h 超时平仓

**文件**：`execution/position_manager.py`

**问题**：仓位可以无限期占用资金，震荡市中"僵尸仓位"消耗机会成本。

**设计**：
在 `check_positions()` 中添加超时检查，位于 SL/TP 和利润保护之后：

```python
# position_manager.py — check_positions() 中新增
POSITION_TIMEOUT_HOURS = 48
TIMEOUT_PNL_RANGE = (-0.01, 0.02)  # leveraged PnL 在 [-1%, +2%] 区间才超时
# 注意：profit_pct 是 leveraged PnL，即 (price_change / entry) * leverage
# 例如 10x 杠杆下 1% 价格变动 = 10% leveraged PnL = profit_pct=0.10

# 在现有 row 查询中添加 entry_time 字段
rows = self.db.execute(
    "SELECT id, symbol, side, entry_price, quantity, leverage, "
    "stop_loss, take_profit, strategy, entry_time "
    "FROM trades WHERE status = 'OPEN'"
).fetchall()

# 在利润保护检查之后、return 之前添加：
if reason is None and entry_time:
    try:
        entry_dt = datetime.fromisoformat(entry_time)
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        hours_held = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 3600
        if hours_held >= POSITION_TIMEOUT_HOURS:
            if TIMEOUT_PNL_RANGE[0] <= profit_pct <= TIMEOUT_PNL_RANGE[1]:
                reason = "TIMEOUT"
                exit_price = current_price
    except (ValueError, TypeError):
        pass
```

**配置新增**（`config.py`）：
```python
position_timeout_hours: int = 48
timeout_pnl_min: float = -0.01
timeout_pnl_max: float = 0.02
```

**注意**：超时平仓只在 PnL 在 [-1%, +2%] 之间时触发。如果仓位深度浮亏（<-1%）不触发——让 SL 处理；如果在盈利（>2%）不触发——让利润保护处理。

---

### 3.8 #8 利润保护参数优化

**文件**：`config.py`, `execution/position_manager.py`

**问题**：5% leveraged PnL 激活阈值在 10x 杠杆下仅需 0.5% 价格变动，噪音易误触发。低层级 50% 回撤太宽松。

**设计**：

**config.py 参数调整**：
```python
profit_protect_activation_pct: float = 0.08  # 从 0.05 提高到 0.08
profit_protect_drawback_pct: float = 0.35    # 从 0.50 收紧到 0.35
```

**position_manager.py 分层调整**：
```python
# 修改分层回撤逻辑
if peak_profit >= 0.40:
    max_drawback = 0.20  # 40%+ 利润：允许 20% 回撤（不变）
elif peak_profit >= 0.20:
    max_drawback = 0.25  # 20-40%：从 0.30 收紧到 0.25
elif peak_profit >= 0.10:
    max_drawback = 0.30  # 10-20%：从 0.40 收紧到 0.30
else:
    max_drawback = self._profit_protect_drawback_pct  # <10%：0.35（从 0.50）
```

**新增最低保底利润**：
```python
# 一旦激活，至少保住 activation * 40% 的利润
min_guaranteed = self._profit_protect_activation_pct * 0.4
if profit_pct < min_guaranteed and peak_profit >= self._profit_protect_activation_pct:
    reason = "PROFIT_PROTECT"
```

---

### 3.9 #9 连续仓位缩放 + base_risk 提升

**文件**：`risk/risk_manager.py`, `config.py`

**问题**：仅 3 档阶梯（2%/4%/6%），confidence 0.71 和 0.99 仓位一样大。2% base_risk 对 $200 太保守。

**设计**：

**config.py**：
```python
max_risk_per_trade: float = 0.03  # 从 0.02 提高到 0.03
```

**risk_manager.py 仓位计算**：
```python
# 替换 3 档阶梯为连续函数
# confidence 0.3 → multiplier 1.0 (3% risk)
# confidence 0.65 → multiplier 2.0 (6% risk)
# confidence 1.0 → multiplier 3.5 (10.5% risk)
MIN_CONF = 0.3
MAX_MULTIPLIER = 3.5
risk_multiplier = 1.0 + (signal.confidence - MIN_CONF) / (1.0 - MIN_CONF) * (MAX_MULTIPLIER - 1.0)
risk_multiplier = max(1.0, min(MAX_MULTIPLIER, risk_multiplier))
```

**最大风险分析**：confidence=1.0 时 risk = 3% × 3.5 = 10.5%。配合 #3 的方向暴露上限（15x 等效杠杆），即使 3 个同向最大仓位，总风险也被 15x 限制封顶，不会出现 31.5% 账户风险的极端情况。实际上 15x 限制意味着同向最多 ~1.5 个满仓位（10x × 1.5 = 15x）。

**效果对比**：

| Confidence | 旧 risk | 新 risk | 变化 |
|-----------|---------|---------|------|
| 0.3 | 2% | 3% | +50% |
| 0.5 | 4% | 4.7% | +18% |
| 0.7 | 6% | 6.4% | +7% |
| 0.9 | 6% | 8.8% | +47% |

---

### 3.10 #10 降低 intel 伪数据调整量

**文件**：`crypto_system.py`（约第 897-907 行）

**问题**：WhaleTracker 和 LiquidationHunter 用 K 线模拟数据，可能产生反向信号干扰。

**设计**：
```python
# 降低调整量，直到 #13 接入真实 WebSocket 数据
INTEL_AGREE_ADJ = 0.01   # 从 0.03 降到 0.01
INTEL_CONFLICT_ADJ = 0.02  # 从 0.05 降到 0.02
```

当 #13 完成后恢复为 0.03/0.05 或更高。

---

### 3.11 #11 HALT 缩短 + CAUTIOUS 阈值调整

**文件**：`defense/defense_manager.py`, `config.py`

**问题**：
- HALT 24h 太长，加密市场 V 型反转常在 2-6h 内发生
- CAUTIOUS 5% drawdown = $10 就触发，太保守

**设计**：

**config.py**：
```python
recovery_cautious: float = 0.08  # 从 0.05 提高到 0.08
```

**defense_manager.py**：
```python
# HALT 时间从 24h 改为 8h
self._cooldown_until = now + timedelta(hours=8)  # 从 24 改为 8
```

**RECOVERY_PARAMS 微调**：
```python
RECOVERY_PARAMS = {
    RecoveryState.NORMAL:   {"max_leverage": 10, "min_confidence": 0.3, "mtf_min_score": 5},
    RecoveryState.CAUTIOUS: {"max_leverage": 7,  "min_confidence": 0.4, "mtf_min_score": 5},  # leverage 5→7, conf 0.5→0.4
    RecoveryState.RECOVERY: {"max_leverage": 5,  "min_confidence": 0.5, "mtf_min_score": 6},  # leverage 3→5, conf 0.6→0.5
    RecoveryState.CRITICAL: {"max_leverage": 3,  "min_confidence": 0.6, "mtf_min_score": 7},  # leverage 2→3, conf 0.7→0.6
}
```

**理由**：修复 #1 后 confidence 恢复正常范围（0.3-0.9），旧的 min_confidence 阈值（CAUTIOUS 0.5, RECOVERY 0.6, CRITICAL 0.7）在正常 confidence 下仍然过度限制。下调让系统在防御状态下仍能抓住高质量信号。

---

### 3.12 #12 合并双重 API 调用

**文件**：`crypto_system.py`

**问题**：`run_trading_cycle()` 中 `get_positions()`（L657）和获取 equity（L663）分别调用 `fapiPrivateV2GetAccount`，每周期消耗 2 次重量级 API 调用。

**设计**：
让 `get_positions()` 返回完整 account data，主循环复用：

```python
# executor.py — 修改 get_positions 返回 account data
async def get_positions_and_account(self) -> tuple:
    """Fetch positions and account data in single API call."""
    account = await self.exchange.fapiPrivateV2GetAccount()
    positions = []
    for pos in account.get("positions", []):
        amt = float(pos.get("positionAmt", 0))
        if amt == 0:
            continue
        positions.append(Position(...))
    equity = float(account.get("totalMarginBalance", 0))
    available = float(account.get("availableBalance", 0))
    return positions, equity, available

# crypto_system.py — 主循环中
positions, equity, available = await executor.get_positions_and_account()
# 不再单独调用 get_equity()
```

---

### 3.13 #13 接入 WebSocket 真实数据

**新文件**：`data/ws_manager.py`

**问题**：WhaleTracker 用 K 线模拟大户交易，LiquidationHunter 用 volume spike 模拟清算。都不是真实数据。

**设计**：创建统一的 WebSocket 管理器：

```python
# data/ws_manager.py
class BinanceWSManager:
    """管理 Binance WebSocket 连接，分发数据到情报模块。"""

    def __init__(self, symbols: List[str]):
        self._symbols = symbols
        self._callbacks: Dict[str, List[Callable]] = {}
        self._ws = None
        self._running = False

    async def start(self):
        """启动 WebSocket 连接，订阅 aggTrade + forceOrder + depth。"""
        streams = []
        for sym in self._symbols:
            s = sym.lower()
            streams.append(f"{s}@aggTrade")       # 逐笔成交 → WhaleTracker
            streams.append(f"{s}@depth20@100ms")   # 20档深度 → OrderBookSniper
        streams.append("!forceOrder@arr")          # 全市场强平 → LiquidationHunter

        url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
        # 连接管理 + 自动重连 + 心跳

    async def _handle_message(self, msg):
        """解析消息并分发到注册的回调。"""
        stream = msg.get("stream", "")
        data = msg.get("data", {})
        if "aggTrade" in stream:
            await self._dispatch("aggTrade", data)
        elif "forceOrder" in stream:
            await self._dispatch("forceOrder", data)
        elif "depth" in stream:
            await self._dispatch("depth", data)

    def on(self, event: str, callback: Callable):
        """注册事件回调。"""
        self._callbacks.setdefault(event, []).append(callback)

    async def _reconnect(self):
        """自动重连逻辑（指数退避，最大 60s）。"""
        ...

    async def close(self):
        """关闭连接。"""
        ...
```

**WhaleTracker 改造**：
```python
# 现有 process_trade() 接口不变，但数据源从 K 线模拟改为 aggTrade
# ws_manager.on("aggTrade", whale_tracker.process_trade)
# aggTrade 格式: {"s": "BTCUSDT", "p": "87000.0", "q": "1.5", "m": true}
# m=true 表示卖方主动 (maker is buyer)
```

**LiquidationHunter 改造**：
```python
# 接收真实 forceOrder 而非 volume spike 模拟
# forceOrder 格式: {"s": "BTCUSDT", "S": "SELL", "q": "0.5", "p": "86500.0"}
# S=SELL 表示多头被强平
```

**OrderBookSniper 改造**：
```python
# 从 REST 20档改为 WebSocket depth20@100ms
# 延迟从 ~200ms 降到 ~100ms
```

**集成到主循环**：
```python
# crypto_system.py startup
ws_manager = BinanceWSManager(symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
ws_manager.on("aggTrade", whale_tracker.process_ws_trade)
ws_manager.on("forceOrder", liquidation_hunter.process_ws_liquidation)
ws_manager.on("depth", orderbook_sniper.process_ws_depth)
await ws_manager.start()  # 后台任务

# 修复后恢复 intel 调整量
INTEL_AGREE_ADJ = 0.03
INTEL_CONFLICT_ADJ = 0.05
```

---

### 3.14 #14 MTF 投票改为梯度

**文件**：`analysis/multi_timeframe.py`

**问题**：`_vote()` 只返回 +1/-1（二值），导致 score 只有有限离散值。在震荡市中 score 常在 [-4, 4]，过滤器几乎不起作用。

**设计**：引入中性票（0）和梯度投票：

```python
@staticmethod
def _vote(df: pd.DataFrame) -> int:
    """EMA9/21 交叉的梯度投票。

    Returns:
        +1 if clear bullish (spread > 0.1%)
        -1 if clear bearish (spread < -0.1%)
         0 if neutral (spread within ±0.1%)
    """
    close = df["close"]
    ema9 = ta.trend.ema_indicator(close, window=9)
    ema21 = ta.trend.ema_indicator(close, window=21)
    spread = (ema9.iloc[-1] - ema21.iloc[-1]) / close.iloc[-1]
    if abs(spread) < 0.001:  # 0.1% 以内视为中性
        return 0
    return 1 if spread > 0 else -1
```

**MTF 过滤阈值调整**：
```python
# config.py
mtf_min_confluence: int = 4  # 从 6 降到 4（因为有中性票，score 分布更集中）
```

**效果**：
- 强趋势（4 个 TF 同向）：score = ±10，过滤逆势交易
- 中等趋势（3 同向 1 中性）：score = ±9 或 ±6，仍过滤
- 震荡（2 同向 2 反向或中性）：score 在 [-4, 4]，不过滤（允许交易）
- 这比旧的二值投票更精确

---

### 3.15 #15 Confidence 动态计算

**文件**：`strategy/trend_follower.py`, `strategy/momentum.py`, `strategy/breakout.py`, `strategy/scalper.py`, `strategy/mean_reversion.py`

**设计原则**：每个策略的 confidence 改为连续函数，反映信号强度而非硬编码跳变。

**TrendFollower**：
```python
# 基于 EMA spread 连续映射
spread_pct = abs(ema_fast - ema_slow) / close
base_conf = 0.35 + min(0.45, spread_pct * 100)  # 0.35 ~ 0.80
# regime 调整
if regime in (TRENDING_UP, TRENDING_DOWN):
    base_conf += 0.1
elif regime == RANGING:
    base_conf -= 0.1
# volume boost
if volume_ratio > 1.2:
    base_conf += 0.05
confidence = min(0.95, max(0.3, base_conf))
```

**Momentum**：
```python
# MACD histogram / ATR 强度
hist_strength = abs(macd_hist) / atr
base_conf = 0.35 + min(0.45, hist_strength * 8)
```

**Breakout**：
```python
# volume_ratio 和 squeeze 强度
base_conf = 0.40 + min(0.40, (volume_ratio - 1.0) * 0.15)
if bb_squeeze:  # BB 宽度 < 10th percentile
    base_conf += 0.1
```

**Scalper**：
```python
# RSI 距离极值
rsi_distance = min(abs(rsi - 0), abs(rsi - 100))  # 越近极值越强
base_conf = 0.35 + min(0.35, (50 - rsi_distance) / 50 * 0.35)
```

**MeanReversion**：
```python
# 价格距 BB 边缘的百分比
bb_width = upper - lower
distance_from_band = abs(close - lower) / bb_width if direction == LONG else abs(upper - close) / bb_width
base_conf = 0.40 + min(0.40, (1.0 - distance_from_band) * 0.5)
```

---

### 3.16 #16 动态 SL 移到保本

**文件**：`execution/position_manager.py`

**问题**：盈利仓位 SL 始终在原始位置，回调时可能从盈利变亏损。

**设计**：
当 leveraged PnL > 5% 时，将 SL 移到入场价 + 手续费（保本），并更新交易所 algo order：

```python
# position_manager.py — check_positions() 中新增
BREAKEVEN_THRESHOLD = 0.05  # 5% leveraged PnL 时移动 SL 到保本

# 在 peak tracking 之后、SL/TP 检查之前：
if profit_pct >= BREAKEVEN_THRESHOLD and stop_loss:
    # 计算保本 SL = entry + round-trip fees
    fee_adj = entry_price * 0.0008 / leverage  # 2x taker fee / leverage
    if side == "LONG":
        breakeven_sl = entry_price + fee_adj
        if stop_loss < breakeven_sl:
            new_sl = round(breakeven_sl, 2)
            self._schedule_sl_update(trade_id, symbol, side, quantity, new_sl)
            stop_loss = new_sl
    else:
        breakeven_sl = entry_price - fee_adj
        if stop_loss > breakeven_sl:
            new_sl = round(breakeven_sl, 2)
            self._schedule_sl_update(trade_id, symbol, side, quantity, new_sl)
            stop_loss = new_sl

def _schedule_sl_update(self, trade_id, symbol, side, quantity, new_sl):
    """同步更新 DB，异步更新交易所 SL（通过 pending 队列）。

    check_positions() 是同步方法，不能直接 await。
    DB 更新立即执行，交易所 SL 更新加入队列由主循环 await。
    """
    # 1. 立即更新 DB（同步）
    self.db.execute("UPDATE trades SET stop_loss = ? WHERE id = ?", (new_sl, trade_id))
    # 2. 加入待执行队列（主循环 await）
    self._pending_sl_updates.append({
        "trade_id": trade_id, "symbol": symbol,
        "side": side, "quantity": quantity, "new_sl": new_sl,
    })
    logger.info(f"SL update scheduled: {symbol} {side} SL→{new_sl}")

async def process_pending_sl_updates(self):
    """由主循环调用，执行队列中的交易所 SL 更新。"""
    while self._pending_sl_updates:
        update = self._pending_sl_updates.pop(0)
        if self._executor:
            binance_sym = self._executor._to_binance_symbol(update["symbol"])
            pos_side = update["side"]
            try:
                await self._executor.cancel_algo_orders(binance_sym, pos_side)
                close_side = "SELL" if pos_side == "LONG" else "BUY"
                rounded_qty = self._executor._round_qty(update["symbol"], update["quantity"])
                await self._executor._place_algo_order(
                    binance_sym, close_side, pos_side, "STOP_MARKET",
                    rounded_qty, update["new_sl"]
                )
                logger.info(f"SL moved to breakeven: {update['symbol']} {pos_side} SL={update['new_sl']}")
            except Exception as e:
                logger.warning(f"Failed to update exchange SL: {e}")
```

**配置新增**（`config.py`）：
```python
breakeven_sl_threshold: float = 0.05
```

---

### 3.17 #17 watchdog↔bot 通信改 Unix socket

**文件**：`crypto_guardian.py`, `crypto_system.py`

**问题**：watchdog.state 文件在外接 ORICO 硬盘上频繁读写，I/O 延迟高且锁竞争。

**设计**：
使用 Unix domain socket 替代文件 I/O：

```python
# 新增 ipc/socket_ipc.py
import asyncio
import json
import os

SOCKET_PATH = "/tmp/crypto_beast_ipc.sock"

class IPCServer:
    """watchdog 端：接收 bot 的心跳和状态查询。"""

    def __init__(self):
        self._state = {}
        self._server = None

    async def start(self):
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
        self._server = await asyncio.start_unix_server(
            self._handle_client, SOCKET_PATH
        )

    async def _handle_client(self, reader, writer):
        data = await reader.read(4096)
        msg = json.loads(data.decode())
        if msg.get("type") == "heartbeat":
            self._state.update(msg.get("data", {}))
            writer.write(json.dumps({"ok": True}).encode())
        elif msg.get("type") == "query":
            writer.write(json.dumps(self._state).encode())
        elif msg.get("type") == "command":
            # watchdog 向 bot 发送命令
            self._state["pending_command"] = msg.get("command")
            writer.write(json.dumps({"ok": True}).encode())
        await writer.drain()
        writer.close()

    async def stop(self):
        if self._server:
            self._server.close()


class IPCClient:
    """bot 端：发送心跳，查询 watchdog 命令。"""

    async def send_heartbeat(self, data: dict):
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
            writer.write(json.dumps({"type": "heartbeat", "data": data}).encode())
            await writer.drain()
            resp = await reader.read(4096)
            writer.close()
            return json.loads(resp.decode())
        except Exception:
            return None

    async def query_state(self) -> dict:
        try:
            reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
            writer.write(json.dumps({"type": "query"}).encode())
            await writer.drain()
            resp = await reader.read(4096)
            writer.close()
            return json.loads(resp.decode())
        except Exception:
            return {}
```

**向后兼容**：保留 watchdog.state 文件作为 fallback（socket 不可用时回退到文件），确保平滑迁移。

**注意**：socket 路径使用 `/tmp/`（本地磁盘），不在外接硬盘上，消除 I/O 延迟。

---

### 3.18 #18 Binance User Data Stream

**新文件**：`data/user_data_stream.py`

**问题**：每 5 秒轮询 `fapiPrivateV2GetAccount` 获取账户状态，消耗 API 调用量。

**设计**：使用 Binance User Data Stream 推送账户变动：

```python
# data/user_data_stream.py
class UserDataStream:
    """Binance User Data Stream — 实时推送账户变动。

    Events:
    - ACCOUNT_UPDATE: 余额和持仓变化
    - ORDER_TRADE_UPDATE: 订单状态变化
    - listenKey 需要每 30 分钟续期
    """

    def __init__(self, exchange, api_key: str, api_secret: str):
        self._exchange = exchange
        self._api_key = api_key
        self._api_secret = api_secret
        self._listen_key: Optional[str] = None
        self._ws = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._keepalive_task: Optional[asyncio.Task] = None

    async def start(self):
        """获取 listenKey 并连接 WebSocket。"""
        # POST /fapi/v1/listenKey
        self._listen_key = await self._create_listen_key()
        url = f"wss://fstream.binance.com/ws/{self._listen_key}"
        # 连接 WebSocket + 启动 keepalive 定时器
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self):
        """每 25 分钟续期 listenKey（有效期 60 分钟，25 分钟续一次留余量）。"""
        while True:
            await asyncio.sleep(25 * 60)
            try:
                await self._extend_listen_key()
            except Exception as e:
                logger.warning(f"listenKey renewal failed: {e}")
                # 重新创建
                self._listen_key = await self._create_listen_key()

    async def _handle_message(self, msg):
        event = msg.get("e")
        if event == "ACCOUNT_UPDATE":
            # 余额 + 持仓变化
            await self._dispatch("account_update", msg)
        elif event == "ORDER_TRADE_UPDATE":
            # 订单状态（SL/TP 触发通知）
            await self._dispatch("order_update", msg)

    def on(self, event: str, callback: Callable):
        self._callbacks.setdefault(event, []).append(callback)

    async def close(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()
        # DELETE /fapi/v1/listenKey
        await self._delete_listen_key()
```

**集成到主循环**：
```python
# 启动 User Data Stream
user_stream = UserDataStream(exchange, api_key, api_secret)
user_stream.on("account_update", on_account_update)
user_stream.on("order_update", on_order_update)
await user_stream.start()

# on_account_update 缓存最新的 equity/positions
# 主循环从缓存读取，不再每周期调 API
# 保留每 60 周期一次的 API 调用作为校验
```

**降级策略**：WebSocket 断线时自动回退到 REST 轮询模式。

---

## 4. 配置变更汇总

```python
# config.py 新增/修改的字段
@dataclass
class Config:
    # 修改
    max_risk_per_trade: float = 0.03          # 从 0.02
    recovery_cautious: float = 0.08           # 从 0.05
    profit_protect_activation_pct: float = 0.08  # 从 0.05
    profit_protect_drawback_pct: float = 0.35    # 从 0.50
    mtf_min_confluence: int = 4               # 从 6

    # 新增
    max_directional_leverage: float = 15.0
    max_correlated_same_dir: int = 2
    correlation_penalty: float = 0.6
    position_timeout_hours: int = 48
    timeout_pnl_min: float = -0.01
    timeout_pnl_max: float = 0.02
    breakeven_sl_threshold: float = 0.05
    halt_cooldown_hours: int = 8              # 从硬编码 24
```

## 5. 新增文件

| 文件 | 用途 |
|------|------|
| `data/ws_manager.py` | Binance 市场数据 WebSocket 管理器 |
| `data/user_data_stream.py` | Binance User Data Stream（账户变动推送） |
| `ipc/socket_ipc.py` | Unix domain socket IPC（watchdog↔bot） |

## 6. 测试计划

### 单元测试（新增/修改）

| 测试文件 | 覆盖 |
|---------|------|
| `tests/test_strategy_engine.py` | #1: confidence 不被权重压缩，去重用 weighted score |
| `tests/test_risk_manager.py` | #3: 方向暴露上限, #9: 连续缩放 |
| `tests/test_position_manager.py` | #7: 超时平仓, #8: 利润保护参数, #16: 保本 SL |
| `tests/test_defense_manager.py` | #11: HALT 8h, CAUTIOUS 8% |
| `tests/test_multi_timeframe.py` | #14: 梯度投票 |
| `tests/test_strategies.py` | #6: 各策略 SL/TP R:R, #15: 动态 confidence |
| `tests/test_ws_manager.py` | #13: WebSocket 连接/重连/分发 |
| `tests/test_ipc.py` | #17: Unix socket IPC |
| `tests/test_user_data_stream.py` | #18: listenKey 管理 |

### 集成测试

- Paper 模式运行 1h，验证信号频率从"几乎不交易"提升到 3-8 次/小时
- 验证所有 409 个现有测试通过
- 验证 direction exposure 限制在 15x 以内
- 手动测试 Telegram 命令仍正常

## 7. 实施顺序

### Phase 1: 核心修复 #1-#12（顺序执行，分 2 次 commit）

**Commit 1 (P0 — 关键修复)**：#1, #2, #3, #4, #5
**Commit 2 (P1 — 参数优化)**：#6, #7, #8, #9, #10, #11, #12

分开 commit 便于回滚：如果 P1 参数调整有问题，可以单独 revert 而不影响 P0 的关键 bug 修复。
1. #1 confidence 权重修复
2. #9 连续缩放 + base_risk（依赖 #1 的正确 confidence）
3. #3 方向暴露上限（依赖 #9 的正确仓位计算）
4. #11 HALT 缩短 + CAUTIOUS 调整
5. #2 移除 LIMIT 覆盖
6. #4 aiohttp session 修复
7. #5 circuit breaker 文件锁
8. #12 合并 API 调用
9. #6 SL/TP 比例优化
10. #8 利润保护参数
11. #7 超时平仓
12. #10 intel 调整量降低

### Phase 2: 深度优化 #13-#18（新模块，可部分并行）
1. #14 MTF 梯度投票（独立，先做）
2. #15 confidence 动态计算（独立，先做）
3. #16 动态 SL 保本（依赖 position_manager 稳定）
4. #13 WebSocket 数据源（独立新模块）
5. #18 User Data Stream（独立新模块）
6. #17 Unix socket IPC（独立新模块）

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| #1 修复后信号突增，交易过于频繁 | 手续费快速消耗 | min_confidence 0.3 + RiskManager 费用检查 + 观察 paper 模式 |
| #3 暴露上限过紧，错过好机会 | 资金利用率降低 | 15x 上限已足够激进，配置可调 |
| #13 WebSocket 断线 | 情报模块无数据 | 自动回退 REST，重连指数退避 |
| #17 Unix socket 不可用 | watchdog↔bot 通信中断 | 保留 watchdog.state 文件作 fallback |
| 多项同时修改引入 regression | 测试不通过 | Phase 1 完成后跑全量测试再进 Phase 2 |

## 9. 文档更新

实施完成后需同步更新：
- **CLAUDE.md**：更新 profit_protect_activation_pct（当前写的 0.02 是过时值，实际代码为 0.05，本次改为 0.08）；添加新增配置项说明；版本号更新为 v1.6.0
- **策略详解.md**：更新各策略 SL/TP 参数和 R:R 比例
- **Git tag**：v1.6.0 release（MINOR 版本因新功能：超时平仓、WebSocket 数据源、Unix socket IPC）
