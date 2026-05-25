# Codebase Summary

**Last Updated:** 2026-05-24 | **Codebase Stats:** 334 files, ~16,815 LOC across 5 packages (core: 5.9k, backtest: 2.4k, trading: 3.5k, api: 3.1k, web: 2.0k) | **Market Data Provider:** Binance public REST/WS (no auth required)

Quick package map for PocketQuant monorepo. For architectural depth, see [system-architecture.md](./system-architecture.md).

---

## Package Overview

### `packages/pocketquant-core`

Shared backend foundation — consumed by all other backend packages.

Contains: domain entities and value objects; CQRS mediator, event bus, middleware; infrastructure adapters (Binance, OKX, HTTP); MongoDB and Redis persistence abstractions; UUID7 utilities, structured logging, APScheduler wrapper.

Key source roots:
- `src/pocketquant/core/domain/` — pure business logic (zero I/O)
- `src/pocketquant/core/common/` — CQRS, event bus, middleware, tracing
- `src/pocketquant/core/infrastructure/` — brokers, data providers, scheduling, webhooks
- `src/pocketquant/core/persistence/` — repositories, MongoDB/Redis connections

### `packages/pocketquant-backtest`

Backtest feature package. Owns backtest and optimization execution logic.

Contains: `BacktestAppService` (execute strategy on historical bars), `GridOptimizationAppService` (multiprocessing parameter search), `HistoricalReplayAppService`, `ResultCollector`, `PerformanceCalculator`.

Key source roots:
- `src/pocketquant/backtest/handlers/` — CQRS handlers for backtest operations
- `src/pocketquant/backtest/persistence/` — `BacktestRepository`, `OptimizationRepository`
- `src/pocketquant/backtest/domain/` — backtest domain concepts

### `packages/pocketquant-trading`

Trading and live strategy runtime package.

Contains: strategy load/start/stop handlers; subscription handlers (add/list/delete symbols, run-all backtest, cascade delete); `OrderAppService`, `PositionAppService`, `StrategyAppService`; YAML strategy loading; broker integration; async backtest job worker via APScheduler.

Key source roots:
- `src/pocketquant/trading/handlers/` — CQRS handlers
- `src/pocketquant/trading/app_services/` — order, position, strategy orchestration
- `src/pocketquant/trading/persistence/` — trading-specific repositories
- `src/pocketquant/trading/jobs/` — `backtest_jobs.py` (subscription backtest worker)

### `packages/pocketquant-api`

FastAPI composition root. Wires everything together — no business logic here.

Contains: `main.py` (app creation), `main_extensions.py` (middleware, routes, health, jobs, SPA serving), `di/` (Dishka container with 6 providers), `market_data/` (sync, OHLCV, quote, status handlers).

Route groups:
- `/health`
- `/api/v1/market-data/*` (sync, bars, integrity, status)
- `/api/v1/quotes/*`
- `/api/v1/strategies/*` (CRUD + subscriptions)
- `/api/v1/trading/*` (orders, positions)
- `/api/v1/backtest/*`
- `/api/v1/system/jobs`

### `packages/pocketquant-web`

React 19 + Vite frontend. Three routes: `/` (Charts), `/strategies` (Operator Dashboard), `/monitor` (System Monitoring).

Tech stack: Vite 8, React 19, TypeScript 5.9, TanStack Router (file-based), TanStack Query 5.95, Lightweight Charts 5.1.

Key files:
- `src/App.tsx`, `src/main.tsx`
- `src/components/chart/trading-chart.tsx` — candlestick + volume + 5 indicators
- `src/components/subscription-panel.tsx`
- `src/api/market-data-api.ts`, `src/api/backtest-api.ts`, `src/api/strategy-subscription-api.ts`
- `src/hooks/useSubscriptions.ts`, `src/hooks/useOHLCV.ts`, `src/hooks/useBacktest.ts`
- `vite.config.ts` — proxies `/api/*` to `http://localhost:41920`

---

## Cross-Package Dependency Graph

```
pocketquant-core
    ↑               ↑
pocketquant-backtest  pocketquant-trading
    ↑               ↑
       pocketquant-api
              ↑
       pocketquant-web  (HTTP only, no Python imports)
```

Enforced dependency rule: `core ← {backtest, trading} ← api`. No reverse dependencies. Domain layer never imports from features or infrastructure.

---

## Runtime Model

### Backend Startup

```bash
just install   # uv sync all packages
just up        # docker compose (MongoDB + Redis)
just dev       # uvicorn on :41920 with --reload
```

Startup sequence (full detail in [system-architecture.md § Startup Sequence](./system-architecture.md#startup-sequence)):
1. Load `.env` settings
2. Connect MongoDB + Redis
3. Build Dishka container (6 providers: Core → Persistence → Infrastructure → MarketData → Trading → Handler)
4. Register all 27 CQRS handlers with Mediator
5. Ensure MongoDB indexes
6. Recover orphan jobs and stale backtests
7. Start 8 background sync/integrity jobs (if `ENABLE_JOBS=true`)
8. Mount built SPA from `packages/pocketquant-web/dist` if present

### Frontend Startup

Dev: `cd packages/pocketquant-web && npm run dev` (Vite HMR, proxies API to :41920).
Prod: `npm run build` → `dist/` served as static assets by FastAPI.

UI assumptions: backend on `:41920`, at least one symbol synced, interval buttons derived from sync statuses.
If UI looks empty: check `GET /api/v1/market-data/sync-status` and `GET /api/v1/market-data/symbols`.

---

## Where Does X Live?

| Topic | Location |
|-------|----------|
| Domain entities (Bar, Order, Position, Symbol) | `core/domain/{bar,order,position,symbol}/entities.py` |
| Value objects (OHLCV, Signal, PnL, QuoteTick) | `core/domain/{bar,concepts}/value_objects.py` |
| Domain events (11 events) | `core/domain/{bar,order,position,concepts}/events.py` |
| Enums (OrderStatus, Interval, Direction, etc.) | `core/domain/{bar,order,position,shared}/enums.py` |
| CQRS Mediator + Handler base | `core/common/mediator/` |
| Event bus + @event_handler decorator | `core/common/messaging/` |
| Middleware (correlation, rate limit, idempotency) | `core/common/middleware/` |
| MongoDB connection | `core/persistence/mongodb.py` |
| Redis connection | `core/persistence/redis.py` |
| All 8 repositories | `core/persistence/repositories/` |
| Binance REST + WS clients | `core/infrastructure/binance/` |
| OKX broker + WS + reconnection | `core/infrastructure/brokers/okx/` |
| PaperBroker (simulation) | `core/infrastructure/brokers/paper/` |
| APScheduler wrapper | `core/infrastructure/scheduling/` + `core/common/jobs.py` |
| Dishka DI container (6 providers) | `api/di/` |
| FastAPI app + middleware wiring | `api/main.py`, `api/main_extensions.py` |
| All CQRS feature operations | `api/features/{backtesting,market_data,strategy,trading,risk}/` |
| Backtest execution engine | `backtest/app_services/backtest_app_service.py` |
| Grid optimization engine | `backtest/app_services/grid_optimization_app_service.py` |
| Strategy runtime dispatch | `trading/app_services/strategy_app_service.py` |
| Order state machine | `trading/app_services/order_app_service.py` |
| Position tracking + P&L | `trading/app_services/position_app_service.py` |
| YAML strategy loader | `trading/app_services/strategy_loader.py` |
| HitNRun2 strategy (hitnrun2) | `core/domain/concepts/strategy/services/hitnrun2.py` |
| Background sync job registration | `api/main_extensions.py` → `register_sync_jobs()` |
| Subscription backtest job worker | `trading/jobs/backtest_jobs.py` |
| UUID7 generation | `core/common/uuid.py` |
| Cache keys, TTLs, constants | `core/common/constants.py` |
| Frontend API client layer | `web/src/api/` |
| Frontend custom hooks | `web/src/hooks/` |
| Chart + indicator components | `web/src/components/chart/` |
| Domain purity test (AST check) | `core/tests/unit/domain/test_domain_purity.py` |

---

## Dishka DI Providers (Quick Ref)

| Provider | Provides |
|----------|----------|
| `CoreProvider` | Settings, EventBus (50-event history), Mediator |
| `PersistenceProvider` | Database (PyMongo), Cache (Redis), 8 repositories |
| `InfrastructureProvider` | PaperBroker, OKXBroker, BinanceClient, BinanceWebSocketClient, JobScheduler, HTTP client, WebhookDispatcher |
| `MarketDataProvider` | BarAppService, QuoteAppService, 8 sync/integrity background jobs |
| `TradingProvider` | OrderAppService, PositionAppService, StrategyAppService |
| `HandlerProvider` | All 27 CQRS handlers (market data ×13, trading ×4, strategy ×5, backtesting ×5) |

For full provider details see [system-architecture.md § Dependency Injection](./system-architecture.md#dependency-injection-dishka).

---

## Configuration

Environment variables (`.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URL` | MongoDB DSN | — |
| `REDIS_URL` | Redis DSN | — |
| `LOG_FORMAT` | `json` (prod) or `console` (dev) | — |
| `LOG_LEVEL` | `debug`, `info`, `warning`, `error` | — |
| `ENVIRONMENT` | `development` or `production` | — |
| `APP_PORT` | Host-mapped port (container always 41920) | `58921` |
| `ENABLE_JOBS` | Enable background sync/integrity jobs | `false` |
| `OKX_API_KEY` | OKX live trading credential (optional) | — |
| `OKX_API_SECRET` | OKX live trading credential (optional) | — |
| `OKX_PASSPHRASE` | OKX live trading credential (optional) | — |
| `OKX_DEMO_MODE` | OKX sandbox mode | `true` |

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `pydantic` | Settings + Features layer (commands/queries); domain uses stdlib dataclasses |
| `pymongo` | MongoDB driver — native async API (NOT Motor) |
| `redis` | Async Redis client (redis-py) |
| `structlog` | Structured logging |
| `apscheduler` | Job scheduling |
| `aiohttp` | Async HTTP + WebSocket (Binance REST/WS) |
| `dishka` | Dependency injection |
| `pytest` | Testing framework |
| `ruff` | Linting and formatting |
| `pyright` | Type checking |

---

## Test Assets

Commands:
```bash
just test           # all packages
just test-pkg core  # single package
just lint
just types
```

Test locations:
- `packages/pocketquant-core/tests/`
- `packages/pocketquant-backtest/tests/`
- `packages/pocketquant-trading/tests/`
- `packages/pocketquant-api/tests/`

Manual smoke tests: `tests/http/` (Bruno), `tests/manual/api-test.http` (curl).

Frontend validation:
```bash
cd packages/pocketquant-web && npm run lint && npm run build
```

---

## Entry Points

| Mode | Command | Notes |
|------|---------|-------|
| Development | `just dev` | uvicorn on `:41920`, hot reload |
| Production | `docker compose up` | `APP_PORT` maps to container `:41920` |
| API docs | `http://localhost:41920/api/v1/docs` | Swagger UI |
| Health check | `http://localhost:41920/health` | Aggregate status |

---

## Current Strategies

| ID | Description |
|----|-------------|
| `hitnrun2` | 1m breakdown-buy / breakup-sell with SL/TP capped by `max_loss_pct` (1% default) and `min_profit_pct` (2% default). PaperBroker auto-fills on `BarCompletedEvent`. |

---

## Known Limitations

- In-memory EventBus — events lost on crash; suitable for non-critical events only
- In-memory APScheduler job store — jobs reschedule on startup; no persistent history beyond `job_history` MongoDB collection
- No persistent outbox pattern — consider for mission-critical event delivery
- Rate limiting state lost on Redis restart — acceptable for burst protection
- Single-threaded strategy execution — one strategy per process
- Domain purity enforced via AST check — I/O imports forbidden in `domain/`

---

## Deep Dives

| Topic | Doc |
|-------|-----|
| Layer-by-layer architecture, CQRS flows, request lifecycle | [system-architecture.md](./system-architecture.md) |
| All 27 handler pipelines in detail | [handler-pipelines.md](./handler-pipelines.md) |
| Local run steps, canonical route names | [run-and-test-guide.md](./run-and-test-guide.md) |
| Project history and version notes | [project-changelog.md](./project-changelog.md) |
| Code standards, naming, file-size rules | [code-standards.md](./code-standards.md) |
