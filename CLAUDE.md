# Crypto Beast Trading Bot

## Environment
- Python 3.9.6 — use `Optional[X]` not `X | None`, `Dict`/`List` not `dict`/`list`
- Source venv at `crypto-beast/.venv/` for development/tests
- Runtime venv at `~/briantiong/crypto-beast-runtime/.venv/` (LOCAL disk, independent)
- Tests: `cd crypto-beast && source .venv/bin/activate && python -m pytest -q` (319 tests)

## Running
- Start: `bash crypto-beast/start.sh` (paper) / `bash crypto-beast/start.sh live` / `bash crypto-beast/start.sh dashboard`
- start.sh syncs code to `~/briantiong/crypto-beast-runtime/`, kills old processes, uses local venv
- NEVER run bot directly from ORICO external drive — causes disk I/O errors in background processes
- After code changes: must `rsync` or re-run `start.sh` to sync to runtime dir
- DB at `~/briantiong/crypto-beast-runtime/crypto_beast.db`
- Dashboard at `~/briantiong/crypto-beast-runtime/monitoring/dashboard_app.py` must read DB from runtime dir

## Binance API
- Account uses **hedge mode (dual position)** — all orders need `positionSide: LONG/SHORT`
- ccxt high-level methods don't pass positionSide correctly — use `fapiPrivatePostOrder` direct API
- `reduceOnly` param NOT supported in hedge mode — positionSide handles it
- `STOP_MARKET` order type not supported via fapiPrivatePostOrder — use Algo Order API or let PositionManager handle SL
- BTC min notional: $100, ETH/SOL/others: $20
- Qty must be rounded UP (`math.ceil`) to meet min notional — rounding down causes rejection
- Small accounts (<$500): use single entry (urgency=1.0), no DCA split
- `fetch_positions()` returns NoneType for leverage in some positions — wrap with try/except
- Failed orders (rejected by Binance) don't charge fees, only filled orders do

## Telegram Bot
- Interactive commands in `monitoring/telegram_bot.py` — /help /status /positions /pnl /balance /trades /close /closeall /pause /resume /health
- `/pause` stops new trades but SL/TP monitoring continues
- Bot needs TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env

## Architecture
- 7-layer, 33-module async trading system for Binance USDT-M Futures
- Design spec: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`
- Implementation plan: `docs/superpowers/plans/2026-03-15-crypto-beast-implementation.md`
- All source under `crypto-beast/` subdirectory

## Key Gotchas
- `dotenv.load_dotenv()` crashes in inline scripts — use `dotenv_values(".env")`
- Initial API latency 2-4s (SSL handshake) — don't use for SystemGuard threshold
- SQLite schema changes need `ALTER TABLE ADD COLUMN` for existing DBs
- Strategy confidence × weights × session weights can drop below risk thresholds
- Multiple background `python main.py` processes = zombie DB locks → start.sh kills old ones first
- DB can get polluted if bot restarts and re-opens positions — clean with `DELETE FROM trades` and re-insert matching Binance state
- Streamlit `meta http-equiv` refresh resets active tab — use manual refresh button

## Code Patterns
- Strategies: `BaseStrategy.generate(klines, symbol, regime) -> list[TradeSignal]`
- Data modules: `process_event(data)` to feed, `get_signal(symbol)` to read
- LiveExecutor: `_place_order()` wraps `fapiPrivatePostOrder` for all order types
- Paper vs Live: `self.paper_mode` flag, affects executor + confidence thresholds
- Config: `config.py` dataclass, `.env` for credentials, JSON for overrides

## User
- Prefers Chinese communication
- Non-programmer, uses AI to write all code
- ~$98 USDT capital, risk-tolerant, max loss capped at account balance (no negative balance on Binance)
