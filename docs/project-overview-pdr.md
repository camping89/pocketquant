# PocketQuant: Project Overview and Requirements

What PocketQuant is for and what it must do. How it is built: [system-architecture.md](./system-architecture.md). How to run it: [README](../README.md). The live route list is the OpenAPI page at `/api/v1/docs`.

## Vision

PocketQuant is a personal algorithmic trading platform. It keeps reliable market-data history for crypto, index futures and CFDs, runs strategies against it in backtests and forward tests, and can trade live through a broker.

## Goals

1. **Reliable data:** complete, aligned bar history per symbol, with gaps detected and repaired.
2. **One engine for backtest and live:** a strategy behaves the same in replay and in forward testing.
3. **Safe live trading:** live brokers are opt-in, and every order passes risk checks.
4. **Small, ownable code:** one process, few layers, rules a human can check (see [code-standards.md](./code-standards.md)).

## Functional Requirements

### F1: Historical data sync

- Fetch bars from the provider the symbol's suffix names: Binance (crypto spot), TradingView (index futures), Exness (CFDs).
- Intervals: 1m, 5m, 15m, 1h, 4h, 1d, 1w.
- Upsert; never duplicate a bar.
- Track sync status per symbol and interval.
- Routes: `POST /api/v1/market-data/sync`, `/sync/background`, `/sync/bulk`; `GET /api/v1/market-data/sync-status[/{symbol}]`.

### F2: Real-time quotes

- Stream ticks from the provider WebSocket for every tracked symbol; reconnect with backoff.
- Keep the latest quote and the in-progress bar in Redis.
- Routes: `GET /api/v1/quotes/latest/{symbol}`, `/quotes/current-bar/{symbol}`, `/quotes/stream/{symbol}` (SSE).

### F3: Bar aggregation

- Closed bars come from the `sync_1m` job: 1m from the provider, then an in-process cascade to 5m, 15m, 1h and 4h (and 1d on 24/7 calendars).
- Bars align to each symbol's trading calendar; closed-market minutes are not gaps.

### F4: Data retrieval

- `GET /api/v1/market-data/ohlcv/{symbol}/{interval}` with a `limit`, cached in Redis.
- `GET /api/v1/market-data/bars/stream/{symbol}` streams the in-progress bar (SSE).

### F5: Symbol registry

- Tracked symbols are created, updated, backfilled and deleted under `/api/v1/market-data/tracked-symbols`. These mutations need the admin token when one is configured.
- Deleting a tracked symbol deletes all its data, including subscriptions and backtests.

### F6: Scheduled jobs and integrity

- Sync every minute, verify the cascade hourly, backfill and check integrity daily, repair every 12 h.
- Missed daily or 12 h runs are caught up at boot.
- Report data lag per symbol, and tell a delayed feed from a stuck one.
- Job history: `GET /api/v1/system/jobs/{job_id}/runs` and `/stats`.

### F7: Strategy engine

- Strategies are registered in code in `STRATEGY_REGISTRY` (`core/domain/strategy/services/__init__.py`) and implement `IStrategyService`.
- A subscription binds `(strategy_code, symbol, interval)`. It starts stopped; start and stop are declarative.
- Routes: `GET /api/v1/strategies`, `POST /api/v1/strategies/{strategy_code}/subscriptions`, `POST /api/v1/subscriptions/{sub_id}/start` and `/stop`.

### F8: Backtesting

- Run one ad-hoc backtest per request, isolated from the live engine.
- Report equity, trades, markers, stats and orders; support a constant bid/ask spread.
- Routes: `POST /api/v1/backtest/run` (202) and `GET /api/v1/backtest/{run_id}` with sub-routes.

### F9: Orders and positions

- Persist live orders, positions and closed trades per subscription.
- Report per-subscription metrics: `GET /api/v1/subscriptions/{sub_id}/metrics`.
- Read routes under `/api/v1/trading/orders` and `/api/v1/trading/positions`.

### F10: Live trading (OKX, Exness off)

- OKX: live broker with HMAC auth, reconnect with backoff and a circuit breaker.
- Exness: broker built and off by default (`EXNESS_LIVE_TRADING=false`). It needs a stop loss on every order, a daily loss cap and a reconciled account snapshot before any order.
- Paper is the default broker.

## Non-Functional Requirements

### NF1: Timeliness

- A closed 1m bar is stored within about a minute of the close (`sync_1m` runs at second 2 of each minute).
- SSE streams deliver changes within about 1.2 s.

### NF2: Reliability

- WebSockets reconnect with exponential backoff and a circuit breaker.
- One failing symbol never stops a job for the others.
- Startup marks orphan backtests and job runs as failed, so nothing polls forever.

### NF3: Observability

- Structured logs (structlog), JSON in prod. Log level follows frequency, not importance (rule in the project `CLAUDE.md`).
- `/health` reports database, cache and per-provider session state.

### NF4: Security

- Secrets live only in the `pocketquant-config` repo, never in this one, and are never logged.
- Mongo and Redis require auth in prod.
- Live trading is opt-in per venue.

### NF5: Maintainability

- Rules and limits: the project `CLAUDE.md` and [code-standards.md](./code-standards.md).
- Import contracts and a code metric ratchet run in CI.
- Tests run under three host timezones; nothing may depend on the host zone.

### NF6: Scale

- One process, one uvicorn worker. Scale vertically.
- Several processes may share one database only with jobs enabled in exactly one of them (`ENABLE_JOBS=false` elsewhere).
