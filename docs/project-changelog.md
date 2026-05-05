# PocketQuant: Project Changelog

**Last Updated:** 2026-04-10 | **Format:** Semantic Versioning

## [Unreleased]

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
