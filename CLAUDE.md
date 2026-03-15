# Crypto Beast Trading Bot

## Environment
- Python 3.9.6 — use `Optional[X]` not `X | None`, `Dict`/`List` not `dict`/`list`
- Venv at `crypto-beast/.venv/`
- Tests: `cd crypto-beast && source .venv/bin/activate && python -m pytest -q` (323 tests)
- Entry point: `crypto_system.py` (NOT main.py — renamed to avoid conflict with other projects)

## Running
- Start: `bash crypto-beast/start.sh live` / `bash crypto-beast/start.sh` (paper) / `bash crypto-beast/start.sh dashboard` / `bash crypto-beast/start.sh stop`
- Runs directly from ORICO external drive (I/O errors were from zombie processes, not drive)
- DB at `crypto-beast/crypto_beast.db`
- Logs at `crypto-beast/logs/bot.log`

## Process Management (CRITICAL)
- Process name is `crypto_system.py` — other projects may use `main.py`, don't `pkill main.py`
- Kill command: `ps aux | grep crypto_system | grep -v grep` then `kill -9 <pid>`
- start.sh auto-kills old `crypto_system.py` processes before starting
- Zombie processes holding SQLite DB lock cause "disk I/O error" — always verify 1 process
- `nohup` + `disown` required for background execution (plain `&` dies with shell)
- `caffeinate` subprocess is normal (1 per bot instance)

## Binance API
- Account uses **hedge mode (dual position)** — all orders need `positionSide: LONG/SHORT`
- Entry orders: use `fapiPrivatePostOrder` direct API (ccxt doesn't handle hedge mode)
- SL/TP: use Algo Order API `/fapi/v1/algoOrder` with `algoType=CONDITIONAL` (mandatory since 2025-12-09)
- Old `/fapi/v1/order` rejects STOP_MARKET/TAKE_PROFIT_MARKET with error -4120
- `reduceOnly` NOT supported in hedge mode
- BTC min notional: $100, ETH/SOL/others: $20
- Qty round UP (`math.ceil`) to meet min notional
- Small accounts (<$500): single entry (urgency=1.0), no DCA split
- `fetch_positions()` — use `fapiPrivateV2GetAccount` (ccxt wrapper has NoneType issues)

## Reconciliation
- On startup: `reconcile_with_exchange()` syncs DB with Binance
- Preserves SL/TP/strategy if position already in DB — only updates qty/entry
- NEVER delete crypto_beast.db on restart — reconciliation handles sync
- datetime: always `datetime.now(timezone.utc)` (aware), never `datetime.utcnow()` (naive)

## Telegram Bot
- Commands: /help /status /positions /pnl /balance /trades /close /closeall /pause /resume /health
- `/pause` stops new trades but SL/TP + profit protection monitoring continues
- `_reply()` falls back to plain text if Markdown fails ($ chars break Telegram Markdown)
- Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env

## Position Management
- Static SL/TP: checked every 5 seconds by PositionManager
- Profit protection: activates at 2% profit, closes when 50% of peak profit given back
- Exchange-level SL/TP via Algo Order API (survive bot crash)
- Config: `profit_protect_activation_pct` (0.02), `profit_protect_drawback_pct` (0.50)

## Architecture
- 7-layer, 33-module async trading system for Binance USDT-M Futures
- Design spec: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`
- All source under `crypto-beast/`

## Code Patterns
- Strategies: `BaseStrategy.generate(klines, symbol, regime) -> list[TradeSignal]`
- Data modules: `process_event(data)` to feed, `get_signal(symbol)` to read
- LiveExecutor: `_place_order()` wraps `fapiPrivatePostOrder`, `_place_algo_order()` for SL/TP
- Dashboard: Positions/Orders/Trade History read live from Binance API; Strategies tab reads from local DB (only shows CLOSED trades)
- Config: `config.py` dataclass, `.env` for credentials

## User
- Prefers Chinese communication
- Non-programmer, uses AI to write all code
- ~$99 USDT capital, risk-tolerant, max loss = account balance (no negative on Binance)
