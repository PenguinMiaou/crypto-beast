# Crypto Beast Trading Bot

## Environment
- Python 3.9.6 — use `Optional[X]` not `X | None`, `Dict`/`List` not `dict`/`list`
- Source venv at `crypto-beast/.venv/` for development/tests
- Runtime venv at `/var/tmp/crypto-beast/.venv/` (local disk, independent)
- Tests: `cd crypto-beast && source .venv/bin/activate && python -m pytest -q` (323 tests)

## Running
- Start: `bash crypto-beast/start.sh` (paper) / `bash crypto-beast/start.sh live` / `bash crypto-beast/start.sh dashboard`
- Runtime dir: `/var/tmp/crypto-beast/` — code synced from external drive, runs on local disk
- NEVER run bot directly from ORICO external drive — causes disk I/O errors in background processes
- `~/briantiong/crypto-beast-runtime/` also has I/O issues — use `/var/tmp/` instead
- After code changes: `cp <file> /var/tmp/crypto-beast/<path>` or re-run `start.sh`
- DB at `/var/tmp/crypto-beast/crypto_beast.db`

## Zombie Process Prevention (CRITICAL)
- `pkill -9 -f python` does NOT reliably kill all processes — use `ps aux | grep main.py` and kill by PID
- Always verify `ps aux | grep main.py | grep -v grep` shows only 1 process after start
- Old processes hold SQLite DB lock → new process gets "disk I/O error"
- start.sh kills by PID file + stray grep, but manual verification recommended
- `caffeinate` subprocess is normal (1 per bot instance)

## Binance API
- Account uses **hedge mode (dual position)** — all orders need `positionSide: LONG/SHORT`
- ccxt high-level methods don't pass positionSide correctly — use `fapiPrivatePostOrder` direct API
- `reduceOnly` param NOT supported in hedge mode — positionSide handles it
- SL/TP: use Algo Order API `/fapi/v1/algoOrder` with `algoType=CONDITIONAL` (mandatory since 2025-12-09)
- Old `/fapi/v1/order` endpoint rejects STOP_MARKET/TAKE_PROFIT_MARKET with error -4120
- BTC min notional: $100, ETH/SOL/others: $20
- Qty must be rounded UP (`math.ceil`) to meet min notional
- Small accounts (<$500): use single entry (urgency=1.0), no DCA split
- `fetch_positions()` — use `fapiPrivateV2GetAccount` not ccxt `fetch_positions` (NoneType issues)
- Failed orders (rejected by Binance) don't charge fees

## Reconciliation
- On startup: `reconcile_with_exchange()` syncs DB with Binance actual positions
- Preserves existing SL/TP/strategy if position already in DB
- Only adds new positions or removes stale ones — doesn't wipe and re-insert
- NEVER delete crypto_beast.db on restart — reconciliation handles sync, deleting loses SL/TP data
- datetime: always use `datetime.now(timezone.utc)` (aware), never `datetime.utcnow()` (naive)

## Telegram Bot
- Commands: /help /status /positions /pnl /balance /trades /close /closeall /pause /resume /health
- `/pause` stops new trades but SL/TP + profit protection monitoring continues
- Needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env

## Position Management
- Static SL/TP: checked every 5 seconds by PositionManager
- Profit protection: activates at 2% profit, closes when 50% of peak profit given back
- Config: `profit_protect_activation_pct` (0.02), `profit_protect_drawback_pct` (0.50)
- Exchange-level SL/TP orders placed on Binance after entry (survive bot crash)

## Architecture
- 7-layer, 33-module async trading system for Binance USDT-M Futures
- Design spec: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`
- All source under `crypto-beast/` subdirectory

## Code Patterns
- Strategies: `BaseStrategy.generate(klines, symbol, regime) -> list[TradeSignal]`
- Data modules: `process_event(data)` to feed, `get_signal(symbol)` to read
- LiveExecutor: `_place_order()` wraps `fapiPrivatePostOrder` for all order types
- Dashboard: reads live from Binance API (not just local DB)
- Config: `config.py` dataclass, `.env` for credentials, JSON for overrides

## User
- Prefers Chinese communication
- Non-programmer, uses AI to write all code
- ~$99 USDT capital, risk-tolerant, max loss capped at account balance (no negative balance on Binance)
