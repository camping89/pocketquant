# PocketQuant: Project Changelog

**Last Updated:** 2026-05-23 | **Format:** Semantic Versioning

## [Unreleased] — 2026-05-23 — Exchange Encapsulation + Strategy Dashboard

### Breaking Changes
- **BREAKING:** Dropped standalone `exchange` field from domain entities (Bar, Order, Position, Symbol, SyncStatus, StrategySubscription, TrackedSymbol). Composite `{CODE}:{EXCHANGE}` (e.g. `BTCUSDT:BINANCE`) is now the single symbol identifier.
- **BREAKING:** API surface removes `?exchange=` query filters and `/{exchange}/{symbol}` path segments. New contract: `/{symbol}` (URL-encoded composite, `:` → `%3A`).
- **BREAKING:** Repos: `BarRepository.find(symbol, interval, ...)` drops exchange param. Indexes rebuilt: `(symbol, interval, datetime) unique`.
- **BREAKING:** Frontend URL param: `?exchange=X&symbol=Y` → `?symbol=Y:X` (single composite). localStorage key: `chart.interval.{composite}` (was `chart.interval.{exchange}.{code}`).

### Changed
- Cache keys updated: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`, `ohlcv:{symbol}:{interval}:{limit}`.
- Repositories: symbol field now composite; business logic never decomposes—exchange is opaque postfix.
- Database collections: all symbol references use composite identifier format.

### Added
- **New `/strategies` route:** 3-pane operator dashboard (list with start/stop, config+chart embed with entry/exit markers, positions/metrics panel). Reuses `backtest-panel/*` components.
- **Migration script:** `scripts/one_time_consolidate_exchange_into_symbol.py` (idempotent, dry-run safe, counts verified). Deploy after backend merge, before FE deploy.
- **Test coverage:** Composite symbol parsing + strategy page behavior.

### Notes
- Hard-cut API; no deprecation period for old `?exchange=` param.
- Composite format applied from day 1 (future-proofs for multi-exchange trading).
- Migration runs post-deploy, before FE ships; operator dashboard available immediately after.

---

## [v2.0.1] — 2026-05-08 — Hotfix: Binance in-progress bar capture

### Fixed
- **`BinanceClient.fetch_ohlcv` no longer returns the in-progress bar.** Window now caps at the last closed-bar boundary (`floor(now/duration)*duration - 1` ms, exclusive). A second-tier filter drops any kline whose `openTime >= cutoff` even under clock skew. Cron `sync_1m` previously persisted the in-progress kline (~2s of trades) and `filter_new_bars` then locked partial OHLCV in Mongo.
- **Backfill of regression window** `[2026-05-08T07:30Z → 2026-05-08T15:40Z]` for all tracked symbols (BTCUSDT@BINANCE): 627 partial bars deleted across 1m/5m/15m/1h/4h/1d, 490 fresh 1m bars re-synced via fixed code path, cascade rebuilt. Post-backfill audit: 0 partial bars (tick<50) on 1m; sample 1m@09:30Z matches Binance REST byte-for-byte.

### Changed
- **`sync_verify_cascade` hardened**: round-robin replaced with all-tracked-symbols loop; comparison now spans full OHLCV (price 0.01% relative threshold; volume 5% relative threshold) instead of close-only `$0.01` absolute. Alert fires when >5% of compared bars diverge on any field, with first-3 sample breakdown for debugging.

### Added
- `BinanceClient` debug-level event `binance.in_progress_bar_filtered` (count of klines dropped by the defense filter).
- `scripts/backfill_regression_window.py` — one-shot delete + re-sync + cascade tool, driven from `BarRepository.delete_many_by_range` (already shipped in v2.0.0).
- `tests/unit/infrastructure/binance/test_binance_client_in_progress_filter.py` (4 cases) and `tests/unit/market_data/test_sync_verify_cascade.py` (10 cases) lock the new behaviour.

## [v2.0.0] — 2026-05-08 — Binance Migration + TradingView Removal (BREAKING)

### Breaking Changes
- **BREAKING:** Removed `Settings.tradingview_username` and `Settings.tradingview_password` fields (Pydantic ignores stale env vars via `extra="ignore"`)
- **BREAKING:** Removed `TRADINGVIEW_USERNAME` and `TRADINGVIEW_PASSWORD` environment variables
- **BREAKING:** Deleted entire `pocketquant.core.infrastructure.tradingview/` module (no cold backup path)

### Changed
- **Market Data Path:** Switched crypto data source from TradingView to Binance public REST + WS (@aggTrade)
  - No authentication required (public API)
  - Rate limit: 1200 weight/min (typical: 10 weight per request)
  - Historical sync via `IDataProvider.fetch_ohlcv()` (current impl: BinanceClient)
  - Real-time quotes via `IRealtimeQuoteProvider` (@aggTrade WebSocket stream)
- **Data Quality Fix:** BarBuilder cumulative-volume aggregation bug fixed via delta-pass adapter
  - Bug: Cumulative volume from Binance was interpreted as delta, causing 8.9% flat bars + 8.9% zero-vol bars
  - Fix: Delta-pass adapter clamps negative deltas to 0, logs warnings for anomalies
  - Impact: 1m canonical TF flat_pct dropped from 8.9% → 0.0%, zerovol_pct from 8.9% → 0.0%
- **VPS Production Resync:** 2-year bar re-sync completed post-fix
  - Baseline: Pre-audit showed 8.9% flat + 8.9% zero-vol on 1m tf (from 2024-05-08)
  - Post-fix: All canonical timeframes (1m, 5m, 15m, 1h, 4h, 1d) verified clean (0.0% flat, 0.0% zero-vol)
  - Mongodump backup: `/tmp/pq-backup-260508/` (15M, 60,783 docs)
  - Audit reports: `plans/reports/audit-260508-bar-quality{,-post}.md`

### Added
- **IDataProvider + IRealtimeQuoteProvider Protocols**
  - Extension points for future market data sources (OKX, stocks, etc.)
  - `IDataProvider.fetch_ohlcv()` contract requires per-tick delta volumes (not cumulative)
  - `IRealtimeQuoteProvider` for alternative real-time quote streams

### Removed
- `infrastructure/tradingview/` folder: `provider.py`, `websocket.py`, tvdatafeed dependency
- All TradingView creds from documentation and deployment guide

### Notes
- No code changes to BarBuilder (bug was in data source, not aggregation logic)
- Delta-pass adapter validates incoming data at ingestion time (noisy log warnings for >5000-vol bars)
- Operator may safely delete stale `TRADINGVIEW_*` env vars from production `.env` (Pydantic ignores via `extra="ignore"`)

---

## [Unreleased]

### Fixed
- **Sync scheduler phase drift** (2026-05-05) — bar-aligned sync jobs (sync_5m/15m/hourly/swing/repair) now use UTC wall-clock `CronTrigger` instead of startup-anchored `IntervalTrigger`. Eliminates phase drift on container restart that caused up to 15-min lag and missed-bar gaps. Critical for strategy entry/exit signal timing. Regression guard: `tests/test_sync_jobs_phase.py`.

### Added
- **Strategy Subscriptions + Cached Backtest** (2026-05-05)
  - New `StrategySubscription` domain entity: 1 strategy ↔ N (symbol/exchange/interval) subscriptions
  - Deterministic 16-char SHA256 subscription IDs
  - New MongoDB collection `strategy_subscriptions` with index on `strategy_id`
  - Extended `BacktestRepository` with subscription-scoped methods + sparse unique index on `subscription_id`
  - Backtest docs now serve dual purpose: ad-hoc runs (legacy `_id=uuid`) and subscription cache (`_id=subscription_id`)
  - 6 new REST endpoints under `/api/v1/strategies/{strategy_id}`:
    - `POST /symbols`, `GET /symbols`, `DELETE /symbols/{sub_id}`
    - `POST /backtest/run-all` (async APScheduler fan-out jobs)
    - `GET /symbols/{sub_id}/backtest`
    - `DELETE /` (cascade unload + delete subs + delete backtest_runs)
  - Async job worker `pocketquant.trading.jobs.backtest_jobs:run_subscription_backtest`
  - Synthetic strategy id pattern (`{strategy_id}::bt::{sub_id}`) to prevent concurrent run collisions
  - Stale recovery: app startup marks `status='running'` docs older than 10 min as `failed`
  - Status vocabulary: `'running'` | `'completed'` | `'failed'`
  - Frontend subscription panel sidebar (280px) with polling, status badges, cascade delete UI
- **Bar Integrity System** - Data quality validation + automated repair
  - `is_bar_aligned()` + `filter_aligned_bars()` validators in `bar_builder.py`
  - `check_integrity()` detects misaligned bars + gaps (7-day lookback)
  - `repair_integrity()` deletes misaligned bars, resyncs gaps via standard sync
  - 2 new BarRepository methods: `find_datetimes()` (time-range query), `delete_many_by_ids()` (bulk delete)
  - 2 new endpoints: `POST /api/v1/market-data/integrity/check` and `/integrity/repair`
  - 2 daily cron jobs: `sync_integrity` (04:00 UTC) and `sync_repair` (04:30 UTC)
  - Total background jobs: 6 → 8
- **pocketquant-web package** - React 19 SPA for real-time charting
  - Vite 8 + TypeScript 5.9 build pipeline
  - TradingView-like candlestick chart (Lightweight Charts v5.1)
  - 5 technical indicators: SMA, EMA, RSI, MACD, Bollinger Bands
  - Symbol and interval selectors with real-time polling (TanStack Query)
  - API proxy to FastAPI backend at `:41920`
  - Static asset deployment via FastAPI server

### Changed
- Refreshed the root README and docs index for the 5-package repo shape
- Added `docs/run-and-test-guide.md` as the canonical local workflow doc
- Updated `just dev` to run through the project virtualenv instead of assuming global `uvicorn`

### Fixed
- Re-running sync against existing data no longer fails on naive vs aware Mongo datetimes
- Sync-related timestamps loaded from Mongo are normalized to UTC in domain entities

## [v1.0.0] — 2026-03-23

### Initial Release
- **pocketquant-core:** Domain layer, persistence (MongoDB/Redis), infrastructure (brokers, data providers)
- **pocketquant-backtest:** Backtesting engine, parameter optimization, historical bar injection
- **pocketquant-trading:** Order management, position tracking, strategy orchestration, OKX broker
- **pocketquant-api:** FastAPI REST server, CQRS handlers (27 operations), DI container (Dishka)
- **Architecture:** Clean Architecture + DDD + CQRS
- **Features:**
  - Historical data sync from TradingView (13 intervals)
  - Real-time quote streaming + multi-interval bar aggregation
  - Order execution (paper + OKX live)
  - Backtesting with Sharpe/Sortino metrics
  - Parameter grid optimization
  - MongoDB persistence, Redis caching
  - Health checks, structured logging, rate limiting, idempotency
- **Monorepo:** 4 backend packages via uv workspace, plus `pocketquant-web`
