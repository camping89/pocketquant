# PocketQuant: Project Changelog

**Last Updated:** 2026-03-30 | **Format:** Semantic Versioning

## [Unreleased]

### Added
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
- **Monorepo:** 4 packages via uv workspace, 278 Python files, 13,641 LOC
