# PocketQuant: Project Changelog

**Last Updated:** 2026-05-28 | **Format:** Semantic Versioning

## [Unreleased] — 2026-05-28 — CI/CD: deploy moves into GitHub Actions (BREAKING for VPS deploys)

### Changed
- Workflow file renamed: `.github/workflows/ci.yml` → `cicd.yml`. Top-level `name: CI` → `name: CI/CD`. Adds `concurrency: deploy / cancel-in-progress: true`.
- Push to `master` or `develop` now auto-deploys via a new `deploy` job (needs `build-api` + `build-web`). No more `bash deploy/deploy.sh` from laptop.
- `deploy` job: setup SSH → write `deploy/.env` from `PROD_ENV` secret → rsync compose + .env + `deploy/vps/` to VPS → ssh `deploy.sh` → ssh `verify.sh` → upload `verify-report` artifact (30-day retention).

### Removed
- `deploy/deploy.sh` (operator wrapper)
- `deploy/deploy.conf.example` (and operator-local `deploy/deploy.conf` via `.gitignore` cleanup)
- `WAIT_FOR_CI` / `GITHUB_TOKEN` / `GITHUB_REPO` / `CI_BRANCH` / `CI_WORKFLOW` env handling — no longer needed.

### Operator action required
- Add 3 new GitHub Actions repo secrets: `VPS_HOST`, `VPS_SSH_KEY`, `PROD_ENV`. See `docs/deployment.md` → Prerequisites.

## [Unreleased] — 2026-05-26 — Strategy ID Disambiguation: `strategy_code` + `subscription_id` (REFACTOR)

### Refactor
- **BREAKING (API surface):** Route split `/strategies/{id}/symbols` → `/strategies/{strategy_code}/subscriptions` + `/subscriptions/{sub_id}/*`
- **BREAKING (Mongo):** Collection rename `strategy_subscriptions` → `subscriptions` (boot migration at startup, idempotent)
- **BREAKING (Field semantics):** 
  - Subscription doc: `strategy_id` (was template code) → `strategy_code`
  - Order/Position docs: `strategy_id` (was subscription ID) → `subscription_id`
  - Backtest doc: `strategy_id` (was template code) → `strategy_code`
- **BREAKING (Indexes):** Renamed: `ix_strategy_subscriptions_strategy_id` → `ix_subscriptions_strategy_code`; `ix_orders_strategy_id` → `ix_orders_subscription_id`; `ix_positions_strategy_id` → `ix_positions_subscription_id`; etc.
- **Repository methods renamed:** `list_by_strategy` → `list_by_strategy_code`, `find_by_strategy` → `find_by_subscription`, `get_by_strategy` → `get_by_subscription`, etc.
- **New response field:** Subscription list items now include `is_running: bool` (computed from live strategy state, closes bug where FE used backtest status)
- **Commits:** 95c64f8..c68c02c (7 commits)

### Migration
- **At boot:** `migrate_strategy_id_fields(container)` runs before `ensure_all_indexes`, idempotent (renames collection + fields + drops old indexes, aborts if both old+new coexist)
- **Hash stability:** `Subscription.deterministic_id()` input unchanged (still uses `strategy_code|symbol|interval` value); existing PKs unaffected
- **Backward-compat test:** `test_subscription_deterministic_id.py:test_back_compat_known_id_hitnrun2_btc_1m` verifies migration does not change IDs

### Notes
- Refactors away 5-year naming ambiguity: `strategy_id` meant different things in different contexts (template vs instance)
- HTTP routes now clearly separate template-level (`/strategies/{strategy_code}`) from instance-level (`/subscriptions/{sub_id}`)
- No data loss; all subscriptions, orders, positions migrated in-place

---

## [Unreleased] — 2026-05-25 — `scripts-to-deploy/` split + WEB_PORT public stance (BREAKING for VPS deploys)

### Refactor
- **New folder:** `deploy/scripts-to-deploy/` for all VPS-bound shell scripts. Moved into it: `deploy.sh`, `verify.sh`, `cleanup.sh`, `server-setup.sh`, `patches/`.
- **Repurposed:** `deploy/scripts/` is now reserved for LOCAL operator-side helpers (see `deploy/scripts/README.md`). Empty by default.
- **Updated:** `deploy.sh` + `verify.sh` `cd "$(dirname "$0")/.."` so `.env` and `compose.prod.yml` still resolve relatively after the move.
- **Updated:** `server-setup.sh` line 101 stale path `deploy/scripts/patches` → `deploy/scripts-to-deploy/patches`.
- **Docs:** `docs/deployment-guide.md` — `.env` example now `WEB_PORT=80` (matches prod). Port Map note clarifies: `WEB_PORT` is public; obscure-port rule applies only to `APP_PORT`/`MONGO_PORT`/`REDIS_PORT`/`PORTAINER_PORT`.
- **Docs:** "Updating" section adds explicit re-scp step for `scripts-to-deploy/*.sh` (closes a silent-failure mode where CI doesn't push shell scripts).

### Migration Required
- **VPS (BREAKING):** see [`docs/deployment-guide.md` → "VPS Migration Runbook"](./deployment-guide.md#vps-migration-runbook) — Step 2 idempotent `mv` block covers both 2026-05-24 and 2026-05-25 migrations in one pass.

---

## [Unreleased] — 2026-05-24 — Deployment Layout Consolidation (BREAKING for VPS deploys)

### Refactor
- **Consolidated** all deployment assets into `deploy/`:
  - Moved from repo root: `Dockerfile`, `deploy.sh`, `verify.sh`, `.env`, `.env.example`
  - Moved from `docker/`: `compose.yml`, `compose.prod.yml`
  - Moved from `docker/scripts/`: `cleanup.sh`, `server-setup.sh`
  - **Deleted:** `docker/` folder (empty after moves; stale empty `docker/mongo-init.js/` dir also removed)
- **New folder:** `deploy/scripts/patches/` for future one-time `one_time_*` migrations (placeholder README explains convention)
- **Updated:** `justfile` (4 compose paths), `.github/workflows/ci.yml` (added `file: deploy/Dockerfile`), `.dockerignore` (`docker/` → `deploy/`)
- **Unchanged:** root `.dockerignore` location, `scripts/` data-ops Python (not deployment), `packages/pocketquant-web/Dockerfile` (lives with package)

### Migration Required

- **Local dev:** Pull this change, then verify `deploy/.env` exists (file was moved from repo root). If your local copy lost it, `cp deploy/.env.example deploy/.env` and re-fill secrets.
- **VPS (BREAKING):** see [`docs/deployment-guide.md` → "VPS Migration Runbook"](./deployment-guide.md#vps-migration-runbook) — requires one-time `mv` on `/opt/pocketquant`. Rollback runbook published.

---

## [Unreleased] — 2026-05-24 — Scheduler Resilience: Orphan Recovery + Configurable Misfire Grace Time

### Changed
- **JobScheduler error reporting:** `_on_error()` now emits structured error messages (was bare `""` for exceptions without message text).
- **JobScheduler.add_cron_job():** Accepts optional `misfire_grace_time: int | None` kwarg to tune grace window per job (default: 300s global).
- **Sync job configuration:** Per-job `misfire_grace_time` tuned by sync frequency:
  - `sync_1m`: 120s (tight grace for frequent syncs)
  - `sync_verify_cascade`: 600s (aggregate job, loose grace)
  - `sync_backfill`, `sync_integrity`, `sync_repair`: 3600s (daily jobs, allow 1h skew)
- **FastAPI lifespan:** Added `recover_orphan_jobs()` call between `recover_stale_backtests()` and `seed_tracked_symbols()` to catch jobs stuck in running state.

### Added
- **JobHistoryRepository.reconcile_orphan_running():** Detect and reset jobs marked `status='running'` for >grace_time (e.g., crash during job execution).
- **JobHistoryRepository.get_last_successful_started_at():** Query last successful job start time (for startup catch-up logic).
- **Startup catch-up for stale daily/12h jobs:** `register_sync_jobs()` enqueues immediate async catch-up for `CATCHUP_TARGETS` (daily/12h syncs) if last successful run >grace window.
- **CLI audit tool:** `scripts/audit_bar_gaps.py` — standalone script to audit bar gaps by symbol/interval/date range with CSV export.

### Notes
- Misfire grace times prevent cascading failures when scheduler restarts during grace window (e.g., job 09:05 skipped if restart 09:04–09:06).
- Orphan recovery runs at startup; no manual intervention needed for stuck jobs.
- Catch-up jobs fire immediately on startup if due (no waiting for next cron), then normal schedule resumes.

---

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
