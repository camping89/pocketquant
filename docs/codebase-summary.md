# PocketQuant Codebase Summary

**Generated:** 2026-07-06 | **Status:** AS-IS (reflects R8 implementation)

## Overview

PocketQuant is a unified trading platform combining **live trading** (OKX/Paper) + **backtesting** in one FastAPI app. Architecture: Clean Architecture + DDD + Dishka DI. Two drivers (live + backtest) on one shared engine (`src/pocketquant/engine/`).

**Stack:**
- Backend: Python 3.12, FastAPI, Pydantic, PyMongo, redis-py, APScheduler
- Frontend: React 19 + Vite + TypeScript
- Infrastructure: MongoDB, Redis, Binance REST/WS, OKX REST/WS, Docker Compose, Nginx

## Codebase Structure

### Python Package Organization

```
src/pocketquant/
├── core/                              # Domain + Infrastructure (zero external I/O in domain/)
│   ├── domain/                        # Pure business logic (entities, value objects, events, domain services)
│   │   ├── backtest/                  # Backtest results modeling
│   │   ├── bar/                       # OHLCV candle domain
│   │   ├── order/                     # Order aggregate + lifecycle
│   │   ├── position/                  # Position tracking + P&L
│   │   ├── symbol/                    # Tradeable instruments
│   │   ├── sync_status/               # Data sync progress tracking
│   │   ├── trading/                   # Universal trading contracts (Trade, Fill, metrics, commission)
│   │   ├── concepts/                  # Non-persisted domain (quote, risk, strategy)
│   │   └── shared/                    # Cross-cutting (Interval, DomainEvent)
│   │
│   ├── infra/                         # External integrations (adapters)
│   │   ├── brokers/                   # Broker implementations (paper, OKX)
│   │   ├── market_data/               # Market data providers (Binance, OKX)
│   │   ├── persistence/               # MongoDB/Redis access
│   │   │   ├── repositories/          # 12 repository classes (instance methods via DI)
│   │   │   ├── mongodb.py             # PyMongo singleton
│   │   │   └── redis.py               # Redis singleton
│   │   ├── scheduling/                # APScheduler integration
│   │   └── ...
│   │
│   └── common/                        # Cross-cutting concerns (utilities, middleware, exceptions)
│       ├── messaging.py               # EventBus (in-memory, 50 max history)
│       ├── middleware/                # Rate limit, idempotency, logging
│       ├── exceptions.py              # Domain error types + HTTP mapping
│       ├── health.py                  # Health checks
│       └── ...
│
├── engine/                            # Shared engine (used by backtest + live)
│   ├── strategy/                      # Strategy application services
│   │   ├── strategy_app_service.py    # Instance manager (in-RAM strategy pool)
│   │   ├── strategy_command_service.py # Command handlers (start/stop/add/remove)
│   │   └── strategy_query_service.py  # Read-only queries (list, get)
│   │
│   ├── execution/                     # Order + Position orchestrators
│   │   ├── order_app_service.py       # Order state machine
│   │   ├── position_app_service.py    # Position tracking + P&L
│   │   └── risk_check.py              # Risk validation
│   │
│   ├── market_data/                   # Market data aggregation
│   │   └── app_services/              # BarAppService, QuoteAppService, sync jobs
│   │
│   ├── backtest/                      # Backtest driver (isolated per run)
│   │   ├── backtest_app_service.py    # Main orchestrator
│   │   ├── backtest_sandbox_app_service.py # Isolated instance per run
│   │   ├── backtest_execution_service.py   # AsyncTask wrapper
│   │   └── ...
│   │
│   └── live/                          # Live trading driver
│       ├── strategy_reconcile_app_service.py # 5s poll loop + bootstrap()
│       ├── live_trade_collector.py    # EventBus subscriber → persists trades
│       └── live_metrics_query_service.py # On-demand M1 metrics from trades
│
└── app/                               # FastAPI application layer
    ├── main.py                        # Lifespan + app setup
    ├── main_extensions.py             # DI container, startup hooks
    ├── routes/                        # HTTP endpoints (thin routing layer)
    │   ├── strategy.py                # /strategies, /subscriptions (strategy mgmt)
    │   ├── backtest.py                # /backtest (single-run backtester)
    │   ├── market_data.py             # /market-data (bars, quotes, sync)
    │   └── ...
    ├── di/                            # Dependency injection providers
    │   ├── core.py                    # CoreProvider (Settings, EventBus)
    │   ├── persistence.py             # PersistenceProvider (DB, repos)
    │   ├── infrastructure.py          # InfrastructureProvider (brokers, scheduler)
    │   ├── market_data.py             # MarketDataProvider (bar, quote services)
    │   ├── execution.py               # ExecutionProvider (orchestrators + live services)
    │   └── container.py               # Composite container
    └── ...
```

### Frontend Structure

```
web/
├── src/
│   ├── api/                           # REST client layer
│   ├── hooks/                         # Custom React hooks (useBacktest, useQuote, etc.)
│   ├── components/
│   │   ├── chart/                     # Candlestick chart + indicators
│   │   ├── backtest/                  # Backtest form + results
│   │   ├── layout/                    # Navigation, theme toggle, timezone picker
│   │   └── ...
│   ├── lib/                           # Context (theme, timezone), utilities
│   └── index.css                      # CSS tokens (theme-aware)
└── ...
```

## Key Layers & Responsibilities

| Layer | Location | Purpose |
|-------|----------|---------|
| **Domain** | `core/domain/` | Business logic (zero I/O enforced by AST test) |
| **Application** | `engine/`, `app/` | Orchestrators, app services, command/query services |
| **Routes** | `app/routes/` | HTTP handlers (thin layer) |
| **Adapters** | `core/infra/`, `core/common/` | External I/O (DB, brokers, providers) |
| **Frontend** | `web/` | React SPA (Vite, TypeScript) |

## Core Concepts

### MongoDB Collections (13 total)

All `_id` are UUIDv7 (except `apscheduler_jobs`). Join keys: `subscription_id` (live), `run_id` (backtest), `symbol` (composite `CODE:EXCHANGE`).

| Collection | Repository | Purpose |
|-----------|-----------|---------|
| `symbols` | SymbolRepository | Symbol metadata + exchange |
| `bars` | BarRepository | Historical OHLCV |
| `sync_status` | SyncStatusRepository | Market-data sync progress |
| `tracked_symbols` | TrackedSymbolRepository | Symbols to sync |
| `subscriptions` | SubscriptionRepository | Strategy subscriptions + control plane |
| `orders` | OrderRepository | Live orders (subscription_id FK) |
| `positions` | PositionRepository | Live positions (subscription_id FK) |
| `trades` | TradeRepository | Live round-trip trades (subscription_id FK, run_id=sub_id) |
| `backtest_runs` | BacktestRepository | Single-run results (run_id PK) |
| `backtest_orders` | BacktestOrderRepository | Backtest fills (run_id FK) |
| `backtest_trades` | BacktestTradeRepository | Backtest round-trips (run_id FK) |
| `job_history` | JobHistoryRepository | APScheduler job execution logs |
| `apscheduler_jobs` | (APScheduler) | Serialized scheduled jobs |

### Strategy Lifecycle

1. **Create:** POST `/strategies/{code}/subscriptions` → persists Subscription with `desired_state="stopped"` (opt-in)
2. **Start:** POST `/subscriptions/{sub_id}/start` → writes `desired_state="running"` to Mongo
3. **Reconcile:** 5s loop (`StrategyReconcileAppService`) → compares desired vs actual, converges live state
4. **Stop/Delete:** POST/DELETE → writes state, reconcile loop tears down in-process instance

### Real-Time Streaming

**Inbound (WebSocket):**
- **Binance `@aggTrade`:** Singleton per app → `QuoteAppService` → Redis `quote:latest:{symbol}`
- **OKX private:** Per-broker instance → orders/positions/fills via event callbacks

**Outbound (SSE):**
- **Bars:** Poll Redis 1s, emit on bar_start change
- **Quotes:** Poll Redis 0.5s, emit on price/volume change

**Live Trade Pipeline (R8):**
- `TradeClosedEvent` (position reduce/close) → `StrategyAppService._forward_trade_to_bus` → EventBus
- `LiveTradeCollector` (subscriber) → stamps `run_id=subscription_id` + `strategy_code` → persists Trade
- `LiveMetricsQueryService.get_metrics(sub_id)` → calculates M1 (Sharpe, Sortino, win_rate) from trades
- Route: `GET /api/v1/subscriptions/{sub_id}/metrics`

### Backtest (Ad-hoc Single Run)

1. `POST /backtest/run` → allocates `run_id`, persists `BacktestResult` with `status=started`
2. Spawns `BacktestExecutionService.execute_and_persist()` as `asyncio.create_task` (no queue)
3. Runs in isolated `BacktestSandboxAppService` (per-run EventBus + broker)
4. Trades collected via `BacktestReportAppService` → `trades` persisted with `run_id` + metrics
5. FE polls `GET /backtest/{run_id}` → returns `status`, optionally fetches `/trades`, `/stats`, `/equity`

### Dependency Injection (Dishka)

6 providers initialized in order:

```
CoreProvider (Settings, EventBus)
  ↓
PersistenceProvider (Database, Cache, 12 repos)
  ↓
InfrastructureProvider (BrokerFactory, WS, JobScheduler)
  ↓
MarketDataProvider (BarAppService, QuoteAppService, sync jobs)
  ↓
ExecutionProvider (OrderAppService, PositionAppService, StrategyAppService,
                   LiveTradeCollector, LiveMetricsQueryService, StrategyReconcileAppService)
```

All services injected into routes via `FromDishka[ServiceType]` (no `Depends()`).

## Key Services

### Application Services

| Service | Role | File |
|---------|------|------|
| `StrategyAppService` | Instance manager + event dispatch | `engine/strategy/strategy_app_service.py` |
| `StrategyReconcileAppService` | 5s poll loop + `bootstrap()` on boot | `engine/live/strategy_reconcile_app_service.py` |
| `OrderAppService` | Order state machine | `engine/execution/order_app_service.py` |
| `PositionAppService` | Position tracking + realized P&L | `engine/execution/position_app_service.py` |
| `BarAppService` | Bar aggregation + TTL caching | `engine/market_data/app_services/bar_app_service.py` |
| `QuoteAppService` | Tick aggregation + real-time quotes | `engine/market_data/app_services/quote_app_service.py` |
| `BacktestAppService` | Backtest orchestrator | `engine/backtest/backtest_app_service.py` |
| `BacktestSandboxAppService` | Isolated instance per run | `engine/backtest/backtest_sandbox_app_service.py` |
| `LiveTradeCollector` | EventBus subscriber → persist trades | `engine/live/live_trade_collector.py` |
| `LiveMetricsQueryService` | On-demand M1 metrics | `engine/live/live_metrics_query_service.py` |

### Brokers

| Broker | Role | File |
|--------|------|------|
| `PaperBrokerAdapter` | Simulation (futures/margin 1× leverage) | `core/infra/brokers/paper/paper_broker_adapter.py` |
| `OKXBrokerAdapter` | Live trading (HMAC auth, 1s→30s backoff) | `core/infra/brokers/okx/okx_broker_adapter.py` |
| `BrokerFactory` | Concrete broker construction | `core/infra/brokers/broker_factory.py` |

## Configuration & Startup

### Environment Variables (`.env`)

```
MONGODB_URL=mongodb://...
REDIS_URL=redis://...
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
OKX_DEMO_MODE=true|false
PAPER_INITIAL_BALANCE=10000
PAPER_COMMISSION_PERCENT=0.0004
ENABLE_JOBS=true|false
LOG_LEVEL=DEBUG|INFO|WARNING
ENVIRONMENT=dev|prod
```

### Startup Sequence

1. Load settings from `.env`
2. Setup structured logging (structlog)
3. Create Dishka container with providers
4. `ensure_all_indexes()` → MongoDB indexes
5. `recover_orphan_backtests()` → mark stale runs as failed
6. `recover_orphan_jobs()` → mark stale scheduler jobs as failed
7. `seed_tracked_symbols()` → ensure ≥1 symbol
8. `bootstrap_live_instances()` → load per-subscription instances
9. (Gated on `ENABLE_JOBS`) `start_background_jobs()` → register sync + reconcile
10. `setup_dishka(container, app)` → integrate DI with FastAPI
11. Server ready on `:41921`

## Testing Strategy

- **Domain purity:** AST check (`tests/core_test/unit/domain/test_domain_purity.py`) — forbids I/O imports in `core/domain/`
- **Unit tests:** ~80% coverage target (services, repositories, domain logic)
- **Integration tests:** End-to-end backtest + API routes
- **Test utilities:** Fixtures for mock brokers, trade data, etc.

## Deployment

**Local:** `uvicorn pocketquant.app.main:app --host 0.0.0.0 --port 41921`

**Production:**
- Docker Compose 4-service stack: web (nginx), app (FastAPI), mongodb, redis
- Cloudflare proxy → pocketquant.xyz → nginx reverse-proxy `/api/*` to app:41921
- Config: Git repo `pocketquant-config` (secret boundary) → `.env` synced at deploy
- Single-worker-only constraint: scheduler + WS feed + broker singletons

## Key Constraints & Conventions

- **Single process only:** `--workers N` duplicates reconcile loop + live broker
- **Dependency direction:** features ← app ← engine ← core (enforced by import-linter)
- **Domain purity:** zero I/O in `core/domain/` (enforced by AST)
- **Naming conventions:** Suffix-based encoding (DomainService, AppService, Repository, Adapter, etc.)
- **UUIDv7 only:** All primary keys (no natural keys, no ObjectId)
- **Publish-before-subscribe:** Wire EventBus before any subscriber resolves (preemption point safety)
- **Timezone context:** Frontend uses IANA tzdata, backend UTC timestamps

## Recent Changes (R8 — Live Run Extraction)

1. **Relocated services:** `BrokerFactory` → `core/infra/brokers/`; QuoteAppService, WsSubscriptionAppService → `engine/market_data/app_services/`
2. **StrategyReconcileAppService:** Added `bootstrap()` method for boot instance loading
3. **TradeRepository:** New collection for live trading (`core/infra/persistence/repositories/trade_repository.py`)
4. **LiveTradeCollector:** EventBus subscriber → persists trades per TradeClosedEvent
5. **LiveMetricsQueryService:** On-demand M1 metrics calculation from trades table
6. **Metrics route:** `GET /api/v1/subscriptions/{sub_id}/metrics` returns performance metrics

---

For detailed documentation, see:
- **Architecture & Design:** `docs/system-architecture.md`
- **Code Standards & Naming:** `docs/code-standards.md`
- **Deployment & CI/CD:** `docs/deployment.md`
- **Setup & Development:** `README.md`
