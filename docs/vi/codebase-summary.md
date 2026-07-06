# PocketQuant Codebase Summary

**Generated:** 2026-07-06 | **Status:** AS-IS (phản ánh implementation R8)

## Tổng quan

PocketQuant là một nền tảng giao dịch hợp nhất, kết hợp **live trading** (OKX/Paper) + **backtesting** trong một app FastAPI. Kiến trúc: Clean Architecture + DDD + Dishka DI. Hai driver (live + backtest) trên một engine dùng chung (`src/pocketquant/engine/`).

**Stack:**
- Backend: Python 3.12, FastAPI, Pydantic, PyMongo, redis-py, APScheduler
- Frontend: React 19 + Vite + TypeScript
- Infrastructure: MongoDB, Redis, Binance REST/WS, OKX REST/WS, Docker Compose, Nginx

## Cấu trúc Codebase

### Tổ chức Python Package

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
│   │   ├── quote/                     # Non-persisted: Price, QuoteTick, quote events
│   │   ├── risk/                      # Non-persisted: RiskConfig, PositionCalculation, PositionCalculatorDomainService
│   │   ├── strategy/                  # Non-persisted: IStrategyService, signals, HitNRun2/Engulfing services
│   │   └── shared/                    # Cross-cutting (Interval, DomainEvent)
│   │
│   ├── infra/                         # External integrations (adapters)
│   │   ├── brokers/                   # Broker implementations (paper, OKX) + broker_factory.py
│   │   ├── binance/                   # Binance REST + WebSocket market-data adapters
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

### Cấu trúc Frontend

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

## Các Layer chính & Trách nhiệm

| Layer | Location | Purpose |
|-------|----------|---------|
| **Domain** | `core/domain/` | Business logic (zero I/O enforced by AST test) |
| **Application** | `engine/`, `app/` | Orchestrators, app services, command/query services |
| **Routes** | `app/routes/` | HTTP handlers (thin layer) |
| **Adapters** | `core/infra/`, `core/common/` | External I/O (DB, brokers, providers) |
| **Frontend** | `web/` | React SPA (Vite, TypeScript) |

## Khái niệm cốt lõi

### MongoDB Collections (13 total)

Tất cả `_id` đều là UUIDv7 (trừ `apscheduler_jobs`). Join keys: `subscription_id` (live), `run_id` (backtest), `symbol` (composite `CODE:EXCHANGE`).

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

### Vòng đời Strategy

1. **Create:** POST `/strategies/{code}/subscriptions` → persist Subscription với `desired_state="stopped"` (opt-in)
2. **Start:** POST `/subscriptions/{sub_id}/start` → ghi `desired_state="running"` vào Mongo
3. **Reconcile:** vòng lặp 5s (`StrategyReconcileAppService`) → so sánh desired vs actual, hội tụ live state
4. **Stop/Delete:** POST/DELETE → ghi state, reconcile loop tear down instance in-process

### Real-Time Streaming

**Inbound (WebSocket):**
- **Binance `@aggTrade`:** Singleton per app → `QuoteAppService` → Redis `quote:latest:{symbol}`
- **OKX private:** Per-broker instance → orders/positions/fills qua event callbacks

**Outbound (SSE):**
- **Bars:** Poll Redis 1s, emit khi bar_start đổi
- **Quotes:** Poll Redis 0.5s, emit khi price/volume đổi

**Live Trade Pipeline (R8):**
- `TradeClosedEvent` (position reduce/close) → `StrategyAppService._forward_trade_to_bus` → EventBus
- `LiveTradeCollector` (subscriber) → đóng dấu `run_id=subscription_id` + `strategy_code` → persist Trade
- `LiveMetricsQueryService.get_metrics(sub_id)` → tính M1 (Sharpe, Sortino, win_rate) từ trades
- Route: `GET /api/v1/subscriptions/{sub_id}/metrics`

### Backtest (Ad-hoc Single Run)

1. `POST /backtest/run` → cấp phát `run_id`, persist `BacktestResult` với `status=started`
2. Spawn `BacktestExecutionService.execute_and_persist()` dưới dạng `asyncio.create_task` (không queue)
3. Chạy trong `BacktestSandboxAppService` cô lập (per-run EventBus + broker)
4. Trades thu thập qua `BacktestReportAppService` → `trades` được persist với `run_id` + metrics
5. FE poll `GET /backtest/{run_id}` → trả về `status`, tùy chọn fetch `/trades`, `/stats`, `/equity`

### Dependency Injection (Dishka)

6 provider được khởi tạo theo thứ tự:

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

Tất cả service được inject vào routes qua `FromDishka[ServiceType]` (không `Depends()`).

## Các Service chính

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

## Cấu hình & Startup

### Environment Variables (`.env`)

```
MONGODB_URL=mongodb://...
REDIS_URL=redis://...
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
OKX_DEMO_MODE=true|false
PAPER_INITIAL_BALANCE=10000
PAPER_COMMISSION_BPS=5.0
PAPER_SLIPPAGE_BPS=5.0
ENABLE_JOBS=true|false
LOG_LEVEL=DEBUG|INFO|WARNING
ENVIRONMENT=dev|prod
```

### Startup Sequence

1. Load settings từ `.env`
2. Setup structured logging (structlog)
3. Tạo Dishka container với providers
4. `ensure_all_indexes()` → MongoDB indexes
5. `recover_orphan_backtests()` → đánh dấu stale runs là failed
6. `recover_orphan_jobs()` → đánh dấu stale scheduler jobs là failed
7. `seed_tracked_symbols()` → đảm bảo ≥1 symbol
8. `bootstrap_live_instances()` → load per-subscription instances
9. (Gated on `ENABLE_JOBS`) `start_background_jobs()` → register sync + reconcile
10. `setup_dishka(container, app)` → tích hợp DI với FastAPI
11. Server sẵn sàng trên `:41921`

## Chiến lược Testing

- **Domain purity:** AST check (`tests/core_test/unit/domain/test_domain_purity.py`) — cấm import I/O trong `core/domain/`
- **Unit tests:** mục tiêu coverage ~80% (services, repositories, domain logic)
- **Integration tests:** End-to-end backtest + API routes
- **Test utilities:** Fixtures cho mock brokers, trade data, v.v.

## Deployment

**Local:** `uvicorn pocketquant.app.main:app --host 0.0.0.0 --port 41921`

**Production:**
- Docker Compose stack 4 service: web (nginx), app (FastAPI), mongodb, redis
- Cloudflare proxy → pocketquant.xyz → nginx reverse-proxy `/api/*` tới app:41921
- Config: Git repo `pocketquant-config` (secret boundary) → `.env` được sync khi deploy
- Ràng buộc single-worker-only: scheduler + WS feed + broker singletons

## Ràng buộc & Quy ước chính

- **Single process only:** `--workers N` nhân đôi reconcile loop + live broker
- **Dependency direction:** features ← app ← engine ← core (enforced by import-linter)
- **Domain purity:** zero I/O trong `core/domain/` (enforced by AST)
- **Naming conventions:** encoding theo suffix (DomainService, AppService, Repository, Adapter, v.v.)
- **UUIDv7 only:** tất cả primary keys (no natural keys, no ObjectId)
- **Publish-before-subscribe:** wire EventBus trước khi bất kỳ subscriber nào resolve (an toàn preemption point)
- **Timezone context:** Frontend dùng IANA tzdata, backend UTC timestamps

## Recent Changes (R8 — Live Run Extraction)

1. **Relocated services:** `BrokerFactory` → `core/infra/brokers/`; QuoteAppService, WsSubscriptionAppService → `engine/market_data/app_services/`
2. **StrategyReconcileAppService:** thêm method `bootstrap()` để load instance khi boot
3. **TradeRepository:** collection mới cho live trading (`core/infra/persistence/repositories/trade_repository.py`)
4. **LiveTradeCollector:** EventBus subscriber → persist trades theo mỗi TradeClosedEvent
5. **LiveMetricsQueryService:** tính M1 metrics on-demand từ bảng trades
6. **Metrics route:** `GET /api/v1/subscriptions/{sub_id}/metrics` trả về performance metrics

---

Để xem tài liệu chi tiết, xem:
- **Architecture & Design:** `docs/system-architecture.md`
- **Code Standards & Naming:** `docs/code-standards.md`
- **Deployment & CI/CD:** `docs/deployment.md`
- **Setup & Development:** `README.md`
