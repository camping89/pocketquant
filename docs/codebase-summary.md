# Codebase Summary

Where things live. Why they are shaped this way: [system-architecture.md](./system-architecture.md). Naming rules: [code-standards.md](./code-standards.md).

## Stack

- Backend: Python 3.14 (`.python-version`), FastAPI, Pydantic, PyMongo (native async), redis-py, APScheduler, Dishka, structlog. Dependencies: `pyproject.toml`.
- Frontend: React 19, Vite, TypeScript, TanStack Router and Query, Lightweight Charts. Dependencies: `web/package.json`.
- Runtime: MongoDB, Redis, Docker Compose (`deploy/`), nginx in front of the app.

## Package Map

```text
src/pocketquant/
├── core/
│   ├── domain/          # entities, value objects, events, domain services, strategies, ports + DTOs (no I/O)
│   ├── infra/
│   │   ├── persistence/ # Database, Cache, BaseRepository, every repository
│   │   ├── brokers/     # paper/, okx/, exness/, broker_factory.py
│   │   ├── binance/     # REST + @aggTrade WS
│   │   ├── tradingview/ # tvDatafeed scraper client + adapters
│   │   ├── exness/      # signed REST + WS client, data and quote adapters
│   │   ├── market_data/ # routing data/quote adapters, provider health
│   │   ├── calendars/   # trading calendars (CME Globex, Exness sessions)
│   │   ├── scheduling/  # JobScheduler (APScheduler)
│   │   └── http_client/ # retrying HTTP client
│   ├── common/          # event bus, middleware, tracing, logging, health, exceptions, UUIDv7
│   └── config.py        # Settings (every env var)
├── engine/
│   ├── strategy/        # StrategyAppService + strategy command/query services
│   ├── execution/       # orders, positions, risk check
│   ├── market_data/     # sync, OHLCV, quotes, status, data lag, tracked symbols; app_services/ holds jobs and feeds
│   ├── backtest/        # backtest driver
│   └── live/            # reconcile loop, live trade collector, live metrics
└── app/
    ├── main.py          # create_app() + lifespan
    ├── main_extensions.py # startup steps, middleware, routes, /health, SPA serving
    ├── di/              # three Dishka providers
    ├── routes/          # HTTP routes
    └── middleware/      # admin token check
web/src/                 # api/, hooks/, components/, routes/, lib/
scripts/                 # operator scripts (see scripts/README.md)
deploy/                  # Dockerfile, compose files, VPS scripts
tests/                   # core_test/, engine_test/, backtest_test/, app_test/, scripts/
```

## Find It Fast

| Topic | Location |
|---|---|
| Settings and env vars | `core/config.py` |
| Composite symbol validation | `core/domain/symbol/entities.py` |
| Provider routing and defaults | `core/domain/market_data/provider_routing_domain_service.py` |
| Strategy registry | `core/domain/strategy/services/__init__.py` |
| Strategy implementations | `core/domain/strategy/services/` |
| Position sizing | `core/domain/risk/services/position_calculator_domain_service.py` |
| Performance metrics | `core/domain/trading/performance_calculator_domain_service.py`, `trade_stats.py` |
| Repositories | `core/infra/persistence/repositories/` |
| Broker construction | `core/infra/brokers/broker_factory.py` |
| Calendar per symbol | `core/infra/calendars/trading_calendar_factory.py` |
| Background jobs | `engine/market_data/app_services/sync_jobs.py` (`register_sync_jobs`) |
| Bar cascade | `engine/market_data/app_services/cascade_aggregator.py` |
| WS subscription diff | `engine/market_data/app_services/ws_subscription_app_service.py` |
| Symbol removal cascade | `engine/market_data/tracked_symbols_service.py` |
| Strategy engine | `engine/strategy/strategy_app_service.py` |
| Reconcile loop | `engine/live/strategy_reconcile_app_service.py` |
| Backtest task body | `engine/backtest/backtest_execution_service.py` |
| Backtest sandbox | `engine/backtest/backtest_sandbox_app_service.py` |
| Startup order | `app/main.py` (`lifespan`) |
| Middleware and route wiring | `app/main_extensions.py` |
| DI providers | `app/di/` |
| SPA API client | `web/src/api/` |
| Domain purity test | `tests/core_test/unit/domain/test_domain_purity.py` |
| Code metric script | `scripts/code_metrics.py` |

## Key Services

| Service | Role | File |
|---|---|---|
| `StrategyAppService` | Holds strategy instances, routes events, executes signals | `engine/strategy/strategy_app_service.py` |
| `StrategyReconcileAppService` | Reconcile loop and boot load | `engine/live/strategy_reconcile_app_service.py` |
| `OrderAppService` | Order state machine | `engine/execution/order_app_service.py` |
| `PositionAppService` | Position tracking and realized P&L | `engine/execution/position_app_service.py` |
| `BarAppService` | In-progress bars from ticks | `engine/market_data/app_services/bar_app_service.py` |
| `QuoteAppService` | Quote feed and tick handling | `engine/market_data/app_services/quote_app_service.py` |
| `BacktestAppService` | Backtest replay | `engine/backtest/backtest_app_service.py` |
| `BacktestReportAppService` | Collects trades and equity into metrics | `engine/backtest/backtest_report_app_service.py` |
| `LiveTradeCollector` | Stores live trades from the event bus | `engine/live/live_trade_collector.py` |
| `LiveMetricsQueryService` | Per-subscription metrics on demand | `engine/live/live_metrics_query_service.py` |

## Tests

- Tests mirror the package (`tests/core_test/`, `tests/engine_test/`, `tests/backtest_test/`, `tests/app_test/`, `tests/scripts/`).
- Integration tests use testcontainers, so Docker must be running.
- `tests/core_test/conftest.py` refuses to run against the prod database.
- Gate commands: "Quality Gate" in [code-standards.md](./code-standards.md#quality-gate).
