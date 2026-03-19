# Crypto Beast v1.5 — 全自动加密货币合约交易机器人

全自动 Binance USDT-M 永续合约交易系统。7 层架构，5 个交易策略，4 个情报模块，3 层守护防护，每 5 秒一个交易循环。

## 它能做什么

- **自动交易**：根据技术指标 + 市场情报自动开平仓，不需要盯盘
- **风险控制**：自动止损（交易所级别，崩溃也生效）、利润保护、日亏限制、回撤降杠杆
- **自我修复**：程序崩了自动重启，遇到未知错误调用 Claude AI 分析修复
- **每日复盘**：Claude AI 每天自动分析交易表现，生成报告，提出改进建议
- **Telegram 远程控制**：手机上随时查看状态、平仓、暂停交易
- **Dashboard 仪表板**：网页上看实时持仓、权益、策略表现

## 你需要准备什么

1. **一台 Mac 电脑**（需要 24 小时开着，或者用 Mac Mini/服务器）
2. **Binance 账户** + 合约交易已开通
3. **至少 $20 USDT** 在合约账户里（建议 $100+）
4. **（可选）Telegram 账号** — 用来接收交易通知和远程控制
5. **（可选）Claude Code CLI** — 用来启用 AI 自动修复和每日复盘

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

> **怎么知道装好了？** 运行 `python3 -m pytest -q`，看到 `409 passed` 就是成功了。

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
4. （可选）打开 **BNB 抵扣手续费**，可以省 25% 手续费

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

配置好后，你可以在 Telegram 给你的 bot 发这些命令：

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

| 时间（北京） | 自动任务 |
|-------------|---------|
| 每 5 秒 | 交易循环：分析行情 → 生成信号 → 过滤 → 执行 → 监控持仓 |
| 每 5 分钟 | 更新市场情绪（Fear & Greed 指数 + 多空比） |
| 每 30 分钟 | 更新资金费率 |
| 08:00 | 重置日计数器 |
| 08:05 | 内部交易复盘 |
| 08:10 | 策略进化优化（调整权重） |
| 08:15 | 山寨币雷达扫描（自动选出最活跃的山寨币加入交易） |
| 08:30 | **Claude AI 每日复盘**（19 模块全面分析，报告发到 Telegram） |
| 每周一 08:45 | 每周深度复盘 |
| 每月 1 号 09:00 | 每月战略评估 |

### 如果机器人崩了

**不用慌。** 三层防护会自动处理：

1. **Watchdog 守护进程** — 检测到崩溃 → 自动重启（5 秒内）
2. **Claude AI** — 反复崩溃 → 调用 Claude 分析日志修复代码
3. **macOS launchd** — 连 Watchdog 也崩了 → 系统自动重启 Watchdog

你的 **止损单在 Binance 交易所上**，即使所有程序都停了，止损仍然会被交易所执行。

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

### 文件安全

| 文件 | 敏感？ | 说明 |
|------|--------|------|
| `.env` | ⚠️ **极度敏感** | 包含你的 API Key，绝不能分享 |
| `crypto_beast.db` | 敏感 | 你的交易记录，不建议分享 |
| 代码文件 | 安全 | 不包含任何密钥 |

---

## 配置调整

如果你想调整参数，编辑 `config.py`：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `max_leverage` | 10 | 最大杠杆（实际根据信号质量 3-10x） |
| `max_concurrent_positions` | 3 | 最大同时持仓数 |
| `max_risk_per_trade` | 0.02 | 单笔最大风险（账户的 2%） |
| `max_daily_loss` | 0.10 | 日亏 10% 暂停 24 小时 |
| `max_total_drawdown` | 0.30 | 总回撤 30% 全部平仓 |
| `profit_protect_activation_pct` | 0.05 | 盈利 5% 开始保护 |
| `profit_protect_drawback_pct` | 0.50 | 回吐 50% 平仓锁利 |

> **不确定就不要改。** 默认参数已经过调优，适合 $100-$500 的小账户。

---

## 目录结构

```
.
├── crypto_system.py      # 交易主程序（核心）
├── crypto_guardian.py     # 守护进程（监控+重启+复盘）
├── config.py              # 配置参数
├── start.sh               # 启动/停止脚本
├── .env                   # 你的密钥（不会被上传到 GitHub）
├── strategy/              # 5 个交易策略
├── analysis/              # 市场分析（行情识别、多时间框架、时段权重）
├── data/                  # 数据情报（鲸鱼、情绪、清算、深度）
├── defense/               # 风控防御（止损、反陷阱、杠杆控制）
├── execution/             # 下单执行（Binance API、仓位管理）
├── evolution/             # 自我进化（参数优化、策略权重）
├── monitoring/            # 监控（Dashboard、Telegram、日志）
├── scripts/               # 复盘脚本（daily/weekly/monthly）
├── tests/                 # 409 个自动化测试
├── docs/                  # 详细文档
└── logs/                  # 运行日志（自动创建）
```

---

## 常见问题

### Q: Paper 模式和 Live 模式有什么区别？

Paper 模式模拟交易，不会在 Binance 下真实订单，用来测试策略。Live 模式下真实订单、用真钱。

### Q: 电脑关机了怎么办？

止损单在 Binance 交易所上，关机也会执行。但利润保护机制是软件级的，关机后不工作。建议保持电脑开机。

### Q: 最少要多少钱？

Binance 合约最低名义价值：BTC $100，其他币 $20。加上杠杆，$20 USDT 可以开始，但 $100+ 更安全（有余量做风控）。

### Q: 手续费高怎么办？

1. 在 Binance 开启 **BNB 抵扣手续费**（省 25%）
2. 系统会自动在低置信度时用限价单（手续费减半）
3. 系统会拒绝利润覆盖不了手续费的交易

### Q: 我怎么知道它在赚钱还是亏钱？

- Telegram `/pnl` 看今日盈亏
- Telegram `/balance` 看总余额
- Dashboard http://localhost:8080 看全面数据
- 每天早上 08:30 会收到 AI 复盘报告

### Q: 出了问题找谁？

查看日志 `tail -f logs/bot.log`，大部分问题 Watchdog 会自动处理。如果需要手动干预，Telegram `/stopall` 停止一切。
