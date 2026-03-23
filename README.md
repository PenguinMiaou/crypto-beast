# Crypto Beast v1.7 — 全自动加密货币合约交易机器人

全自动 Binance USDT-M 永续合约交易系统。7 层架构，7 个交易策略（含 Ichimoku Cloud），4 个情报模块，自适应风控（Kelly + Adaptive Risk），ML regime 检测，回测框架，3 层守护防护，每 5 秒一个交易循环。

## 它能做什么

- **自动交易**：7 个策略 + Ensemble 投票 + Regime-aware 权重，根据市场状态自动切换策略偏好
- **自适应风控**：连败自动缩仓、胜率低暂停交易、Kelly Criterion 封杀负期望策略
- **智能防御**：5 级防御状态机（NORMAL→CAUTIOUS→RECOVERY→CRITICAL→HALT→EMERGENCY）
- **自我修复**：程序崩了自动重启，遇到未知错误调用 Claude AI 分析修复
- **回测验证**：内置回测框架 + 参数优化 + Walk-forward 验证，拒绝过拟合
- **ML 增强**：LightGBM 市场状态检测，每周自动重训练
- **每日复盘**：Claude AI 每天自动分析交易表现，生成报告，提出改进建议
- **Telegram 远程控制**：手机上随时查看状态、平仓、暂停交易
- **Dashboard 仪表板**：网页上看实时持仓、权益、策略表现
- **山寨币雷达**：每 4 小时自动扫描 600+ 个币种，筛选高流动性标的加入交易

## 交易策略

| 策略 | 类型 | 适用市场 | 说明 |
|------|------|----------|------|
| TrendFollower | 趋势跟随 | 趋势市 | EMA9/21 交叉 + ATR 止损止盈 |
| Momentum | 动量 | 趋势市 | MACD 直方图递增 + EMA20 方向 |
| Breakout | 突破 | 波动市 | BB Squeeze + 放量突破 |
| MeanReversion | 均值回归 | 震荡市 | BB + RSI 超买超卖 |
| IchimokuCloud | 一目均衡 | 趋势市 | TK 交叉 + 云层确认（基于 FreqST ichiV1） |
| EnhancedBbRsi | BB+RSI增强 | 震荡市 | BB + RSI + MACD 确认 + ADX 过滤 |
| FundingRateArb | 资金费率 | 极端费率 | 资金费率极端时方向性交易 |

## 风控系统

| 层级 | 机制 | 说明 |
|------|------|------|
| Adaptive Risk | 连败缩仓 | 连败 3→50%, 5→25%; 胜率≤30%→2h 冷静期 |
| Kelly Criterion | 策略封杀 | 负期望策略自动禁止交易 |
| DefenseManager | 状态机 | 回撤 8%→降杠杆, 10%→限信号, 20%→最低杠杆 |
| HALT | 熔断 | 日亏 10%→暂停 8h |
| Circuit Breaker | 紧急 | 钱包低于历史峰值 75%→全部平仓 |
| 方向暴露上限 | 防集中 | 同方向最大 15x 等效杠杆 |
| 快速止损 | 早期退出 | 开仓 <30min 且亏损 >1%→立即止损 |

## 你需要准备什么

1. **一台 Mac 电脑**（需要 24 小时开着，或者用 Mac Mini/服务器）
2. **Binance 账户** + 合约交易已开通 + **Hedge Mode（双向持仓）**
3. **至少 $20 USDT** 在合约账户里（建议 $100+）
4. **（可选）$5 BNB** 在合约账户 — 开启手续费 10% 折扣
5. **（可选）Telegram 账号** — 用来接收交易通知和远程控制
6. **（可选）Claude Code CLI** — 用来启用 AI 自动修复和每日复盘

---

## 第一步：下载代码

```bash
git clone https://github.com/PenguinMiaou/crypto-beast.git
cd crypto-beast
```

## 第二步：安装 Python 环境

Mac 自带 Python 3.9+。在终端运行：

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境（每次打开新终端都要执行这一步）
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

> **怎么知道装好了？** 运行 `python3 -m pytest -q`，看到 `459 passed` 就是成功了。

## 第三步：配置 Binance API

### 3.1 创建 API Key

1. 打开 [Binance](https://www.binance.com)，登录
2. 右上角头像 → **API 管理**
3. 点 **创建 API** → 选 **System generated**
4. 设置一个名字（比如 "CryptoBeast"）
5. **非常重要**：权限设置
   - ✅ 允许 **读取**
   - ✅ 允许 **合约交易**
   - ❌ 关闭 **提现**（安全起见！）
   - ❌ 关闭 **现货交易**
6. **IP 限制**：建议设置为你电脑的 IP（更安全）
7. 复制 API Key 和 Secret Key（Secret 只显示一次！）

### 3.2 开通合约交易 + Hedge Mode

1. 进入 Binance **合约交易** 页面
2. 如果没开通过，按提示完成合约交易开通
3. 右上角 ⚙️ 设置 → **持仓模式** → 选 **双向持仓（Hedge Mode）**
4. 打开 **BNB 抵扣手续费**（省 10% 手续费）

### 3.3 填写配置文件

```bash
# 复制模板
cp .env.example .env

# 用文本编辑器打开 .env
nano .env    # 或者用 VS Code: code .env
```

填入你的信息：

```
BINANCE_API_KEY=你的API_Key
BINANCE_API_SECRET=你的Secret_Key
TELEGRAM_BOT_TOKEN=你的Bot_Token（没有先留空）
TELEGRAM_CHAT_ID=你的Chat_ID（没有先留空）
TRADING_MODE=paper
```

> **先用 paper 模式！** `TRADING_MODE=paper` 是模拟交易，不会用真钱。确认一切正常后再改成 `live`。

## 第四步：（可选）配置 Telegram 通知

Telegram 可以让你在手机上收到交易通知、远程控制机器人。强烈推荐配置。

### 4.1 创建 Telegram Bot

1. 在 Telegram 搜索 **@BotFather**
2. 发送 `/newbot`
3. 按提示设置 bot 名字
4. 你会得到一个 **Bot Token**（类似 `123456789:ABCdefGHI...`）
5. 把它填到 `.env` 的 `TELEGRAM_BOT_TOKEN`

### 4.2 获取你的 Chat ID

1. 在 Telegram 搜索 **@userinfobot**
2. 发送任意消息
3. 它会回复你的 **Chat ID**（一串数字）
4. 把它填到 `.env` 的 `TELEGRAM_CHAT_ID`

### 4.3 常用 Telegram 命令

| 命令 | 说明 |
|------|------|
| `/status` | 查看系统状态、权益、持仓数 |
| `/positions` | 查看每个持仓的详情 |
| `/balance` | 查看 Binance 余额 |
| `/pnl` | 今日盈亏 |
| `/trades` | 最近交易记录 |
| `/pause` | 暂停开新仓（现有仓位继续监控） |
| `/resume` | 恢复交易 |
| `/close BTCUSDT` | 平掉 BTC 仓位 |
| `/closeall` | 平掉所有仓位 |
| `/stopall` | 停止一切（需 `/confirm` 确认） |
| `/help` | 查看所有命令 |

## 第五步：启动！

### 模拟交易（推荐先跑几天）

```bash
bash start.sh          # 默认 paper 模式
```

### 实盘交易

确认模拟没问题后：

```bash
# 方法 1: 改 .env 里的 TRADING_MODE=live，然后
bash start.sh

# 方法 2: 直接指定 live 模式
bash start.sh live
```

### 查看 Dashboard

```bash
bash start.sh dashboard
```

然后打开浏览器访问 http://localhost:8080

### 停止

```bash
bash start.sh stop
```

---

## 日常使用

### 查看状态

```bash
# 查看机器人日志（实时）
tail -f logs/bot.log

# 查看守护进程日志
tail -f logs/watchdog.log

# 查看当前持仓
sqlite3 crypto_beast.db "SELECT symbol, side, entry_price, quantity, leverage FROM trades WHERE status='OPEN'"
```

### 机器人的自动行为

启动后不需要你做任何事情，以下全部自动执行：

| 时间（UTC） | 自动任务 |
|-------------|---------|
| 每 5 秒 | 交易循环：分析行情 → 7 策略信号 → Ensemble 投票 → 风控过滤 → 执行 |
| 每 5 分钟 | 更新市场情绪（Fear & Greed + 多空比） |
| 每 30 分钟 | 更新资金费率 |
| 每 4 小时 | 山寨币雷达扫描（600+ 币种，$100M 流动性过滤） |
| 00:00 | 重置日计数器 |
| 00:05 | 内部交易复盘 |
| 00:10 | 策略进化优化（7 策略 × 多 symbol 回测，权重调整） |
| 00:30 | **Claude AI 每日复盘**（发到 Telegram） |
| 每周一 00:45 | 每周深度复盘 + ML 模型重训练 |
| 每月 1 号 01:00 | 每月战略评估 |

### 如果机器人崩了

**不用慌。** 三层防护会自动处理：

1. **Watchdog 守护进程** — 检测到崩溃 → 自动重启（5 秒内）
2. **Claude AI** — 反复崩溃 → 调用 Claude 分析日志修复代码
3. **macOS launchd** — 连 Watchdog 也崩了 → 系统自动重启 Watchdog

你的 **止损单在 Binance 交易所上**（Algo Order API），即使所有程序都停了，止损仍然会被交易所执行。

---

## 安全须知

### 资金安全

- **API Key 绝对不要分享给任何人**
- API 权限只开"读取"和"合约交易"，**关闭提现**
- 建议设置 IP 白名单
- 最大亏损 = 你放进合约账户的金额（Binance 不会倒欠）

### 风险提示

- 这是一个全自动交易程序，**有亏钱的风险**
- 过去的表现不代表未来收益
- 建议只用你**能接受全部亏完的金额**来交易
- 先用 Paper 模式跑至少 3 天，确认策略表现后再用真钱
- 数学专家共识：50 笔交易无法证明策略有效，需 200+ 笔才有统计显著性

### 文件安全

| 文件 | 敏感？ | 说明 |
|------|--------|------|
| `.env` | ⚠️ **极度敏感** | 包含你的 API Key，绝不能分享 |
| `crypto_beast.db` | 敏感 | 你的交易记录，不建议分享 |
| `models/*.pkl` | 安全 | ML 模型文件 |
| 代码文件 | 安全 | 不包含任何密钥 |

---

## 配置调整

如果你想调整参数，编辑 `config.py`：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `max_leverage` | 10 | 最大杠杆（实际根据信号质量 3-10x） |
| `max_concurrent_positions` | 3 | 最大同时持仓数 |
| `max_risk_per_trade` | 0.03 | 单笔最大风险（账户的 3%，连续缩放至 7.5%） |
| `max_daily_loss` | 0.10 | 日亏 10% 暂停 8 小时 |
| `max_total_drawdown` | 0.30 | 总回撤 30% 全部平仓 |
| `circuit_breaker_pct` | 0.75 | 钱包低于峰值 75% 紧急平仓 |
| `profit_protect_activation_pct` | 0.08 | 杠杆收益 8% 开始保护 |
| `profit_protect_drawback_pct` | 0.35 | 回吐 35% 平仓锁利 |
| `min_confidence` | 0.4 | 最低信号置信度 |
| `adaptive_lookback` | 10 | 自适应风控回顾交易数 |
| `adaptive_cooldown_hours` | 2 | 低胜率冷静期时长 |

> **不确定就不要改。** 默认参数已经过 5 位专家（3 位数学家 + 量化分析师 + 软件工程师）的理论验证。

---

## 目录结构

```
.
├── crypto_system.py      # 交易主程序（核心）
├── crypto_guardian.py     # 守护进程（监控+重启+复盘+ML训练）
├── config.py              # 配置参数
├── start.sh               # 启动/停止脚本
├── .env                   # 你的密钥（不会被上传到 GitHub）
├── strategy/              # 7 个交易策略
│   ├── trend_follower.py
│   ├── momentum.py
│   ├── breakout.py
│   ├── mean_reversion.py
│   ├── ichimoku_cloud.py      # Ichimoku Cloud（基于 FreqST ichiV1）
│   ├── enhanced_bb_rsi.py     # BB+RSI+MACD 震荡策略
│   ├── funding_rate_arb.py    # 资金费率方向性交易
│   └── strategy_engine.py     # 策略引擎（Regime权重 + Ensemble投票 + 去重）
├── analysis/              # 市场分析
│   ├── market_regime.py       # 行情识别（含 TRANSITIONING 转换期）
│   ├── multi_timeframe.py     # 多时间框架共振（梯度投票）
│   ├── ml_regime.py           # LightGBM ML regime 检测
│   ├── altcoin_radar.py       # 山寨币雷达（$100M+流动性筛选）
│   └── session_trader.py      # 交易时段权重
├── data/                  # 数据情报
│   ├── whale_tracker.py       # 大户追踪
│   ├── sentiment_radar.py     # 市场情绪
│   ├── liquidation_hunter.py  # 清算猎手
│   ├── orderbook_sniper.py    # 订单簿深度
│   ├── ws_manager.py          # WebSocket 实时数据
│   ├── user_data_stream.py    # 账户变动推送
│   └── historical_loader.py   # 历史 K 线缓存
├── defense/               # 风控防御
│   ├── risk_manager.py        # 风控（Adaptive + Kelly + 暴露上限）
│   ├── defense_manager.py     # 5 级防御状态机
│   └── anti_trap.py           # 陷阱信号过滤
├── execution/             # 下单执行
│   ├── executor.py            # Binance API（Algo Order SL/TP）
│   └── position_manager.py    # 仓位管理（利润保护+保本SL+超时+快速止损）
├── evolution/             # 自我进化
│   ├── evolver.py             # Optuna 参数优化 + 策略权重
│   ├── backtest_lab.py        # 回测框架（动态 regime）
│   ├── performance_analyzer.py # 指标计算（Sharpe/Sortino/Calmar）
│   └── compound_engine.py     # Kelly 仓位 + 复利增长
├── monitoring/            # 监控
│   ├── dashboard_app.py       # Web Dashboard
│   ├── notifier.py            # Telegram 通知
│   └── telegram_bot.py        # Telegram 命令
├── ipc/                   # 进程间通信
│   └── socket_ipc.py         # Unix domain socket（watchdog↔bot）
├── scripts/               # 脚本
│   ├── train_regime.py        # ML 模型训练
│   ├── daily-review.sh
│   ├── weekly-review.sh
│   └── monthly-review.sh
├── models/                # ML 模型文件
├── tests/                 # 459 个自动化测试
├── docs/                  # 设计文档 + 实施计划
└── logs/                  # 运行日志（自动创建）
```

---

## 版本历史

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| v1.7.3 | 2026-03-23 | 10 个 bug 修复（flip 安全、费用公式、altcoin 精度） |
| v1.7.2 | 2026-03-22 | 13 项专家面板优化（降费减频控风险） |
| v1.7.1 | 2026-03-22 | Adaptive grace、Kelly 修复、PnL 准确性 |
| v1.7.0 | 2026-03-22 | Adaptive Risk + Ichimoku/BB+RSI 策略 + 回测 + ML |
| v1.6.0 | 2026-03-21 | 18 项系统审查修复 |
| v1.5.x | 2026-03-19 | 基础架构完善 |
| v1.0 | 2026-03-16 | 初始版本 |

---

## 常见问题

### Q: Paper 模式和 Live 模式有什么区别？

Paper 模式模拟交易，不会在 Binance 下真实订单，用来测试策略。Live 模式下真实订单、用真钱。

### Q: 电脑关机了怎么办？

止损单在 Binance 交易所上（Algo Order），关机也会执行。但利润保护和快速止损是软件级的，关机后不工作。建议保持电脑开机。

### Q: 最少要多少钱？

Binance 合约最低名义价值：BTC $100，其他币 $20。加上杠杆，$20 USDT 可以开始，但 $100+ 更安全（有余量做风控）。

### Q: 手续费高怎么办？

1. 在 Binance 开启 **BNB 抵扣手续费**（省 10%）
2. 系统在低置信度时自动用 LIMIT+IOC 单（maker 费率 0.02% vs taker 0.04%）
3. 系统拒绝利润覆盖不了 3 倍手续费的交易
4. Ensemble 投票和 min_confidence=0.4 减少低质量交易

### Q: 我怎么知道它在赚钱还是亏钱？

- Telegram `/pnl` 看今日盈亏
- Telegram `/balance` 看总余额
- Dashboard http://localhost:8080 看全面数据
- 每天 00:30 UTC 会收到 AI 复盘报告

### Q: 它会亏完我所有钱吗？

最坏情况是亏完合约账户余额（Binance 不会倒欠）。系统有多层防护：
- 回撤 30% → 紧急全部平仓
- 钱包低于峰值 75% → 熔断平仓
- 连败 → 自动缩仓到 25%
- 胜率太低 → 暂停交易 2 小时

### Q: 出了问题找谁？

查看日志 `tail -f logs/bot.log`，大部分问题 Watchdog 会自动处理。如果需要手动干预，Telegram `/stopall` 停止一切。
