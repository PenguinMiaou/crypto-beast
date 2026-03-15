# Crypto Beast Trading Bot

## Environment
- Python 3.9.6 in venv at `crypto-beast/.venv/` — use `Optional[X]` not `X | None`, `Dict`/`List` not `dict`/`list` for type hints
- Activate: `cd crypto-beast && source .venv/bin/activate`
- Tests: `python -m pytest -q` (303 tests, ~9s)
- Bot entry: `python main.py` (paper) or `python main.py --live`
- Dashboard: `streamlit run monitoring/dashboard_app.py --server.port 8080`

## Architecture
- 7-layer, 33-module async trading system for Binance USDT-M Futures
- Design spec: `docs/superpowers/specs/2026-03-15-crypto-beast-design.md`
- Implementation plan: `docs/superpowers/plans/2026-03-15-crypto-beast-implementation.md`
- All code under `crypto-beast/` subdirectory

## Key Gotchas
- ccxt uses `BTC/USDT` format; internal code uses `BTCUSDT` — convert with `_to_ccxt_symbol()`
- `dotenv.load_dotenv()` crashes in inline python scripts — use `dotenv_values(".env")` instead
- Initial Binance API latency is 2-4s (SSL handshake) — don't use for health thresholds
- ORICO external drive has intermittent I/O errors for background Python processes — NEVER run bot directly from external drive
- Runtime dir: `~/briantiong/crypto-beast-runtime/` (code synced from external drive, runs on internal disk)
- SQLite DB at runtime dir `crypto_beast.db` — schema changes need ALTER TABLE migration for existing DBs
- Start bot: `bash crypto-beast/start.sh` (paper) / `bash crypto-beast/start.sh live` / `bash crypto-beast/start.sh dashboard`
- DB path resolved from `__file__` location, so always matches runtime dir
- Strategy confidence is multiplied by weights × session weights — can drop below risk thresholds
- Streamlit auto-refresh (`meta http-equiv`) resets active tab — use `st.sidebar.button("Refresh")` instead

## Code Patterns
- All strategies extend `BaseStrategy` with `generate(klines, symbol, regime) -> list[TradeSignal]`
- Data modules follow pattern: `process_event(data)` to feed, `get_signal(symbol)` to read
- Paper vs Live: controlled by `self.paper_mode` flag, affects executor, confidence thresholds
- Config defaults in `config.py` dataclass, overridable via `.env` and JSON overrides

## User Preferences
- Prefers Chinese communication
- Non-programmer, uses AI to write all code
- Risk-tolerant: $100 USDT starting capital, understands total loss possible
