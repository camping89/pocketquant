# CLAUDE.md — PocketQuant

**Last Updated:** 2026-05-25 | **Status:** v2.0.1 production | **Architecture:** 5-package monorepo (4 Python uv workspace + 1 Node frontend)

## Monorepo Structure

5 packages under `packages/`. The 4 Python packages share the `pocketquant.*` namespace and form the uv workspace. `pocketquant-web` is a separate Node/Vite SPA, **excluded from the uv workspace** (see `pyproject.toml` → `[tool.uv.workspace] exclude`).

```
packages/
├── pocketquant-core/       # 0 deps — domain, common, persistence, infra ports
├── pocketquant-backtest/   # → core — backtest engine, optimization, PaperBroker
├── pocketquant-trading/    # → core — live trading, OKX broker, strategy orchestration
├── pocketquant-api/        # → core + backtest + trading — FastAPI, DI, composition root
└── pocketquant-web/        # Node/Vite SPA — TanStack Router, lightweight-charts; consumes pocketquant-api HTTP
```

**Dependency graph:** core ← {backtest, trading} ← api ← web (HTTP only)

## Package Imports

```python
# Core domain
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.persistence.repositories import BarRepository
from pocketquant.core.infrastructure.brokers import IBroker, PaperBroker, IBrokerFactory
from pocketquant.core.config import Settings

# Backtest
from pocketquant.backtest.domain.entities import BacktestResult, OptimizationResult
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository

# Trading
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.app_services.order_app_service import OrderAppService
from pocketquant.trading.brokers.okx.okx_broker import OKXBroker

# API (composition root)
from pocketquant.api.di.container import create_container
from pocketquant.api.di.broker_factory import BrokerFactory
from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
```

## Domain Structure (Three-Tier DDD)

Domain entities live in `pocketquant-core`:
- **Top-level** (collection-backed): `domain/{bar,order,position,symbol,sync_status}/`
- **Concepts** (non-persisted logic): `concepts/{quote,risk,strategy}/`
- **Shared** (cross-cutting): `domain/shared/{enums,events,value_objects}.py`

Backtest domain lives in `pocketquant-backtest/domain/`.

Standard file names per folder: `entities.py`, `events.py`, `value_objects.py`, `enums.py`, `interfaces.py`, `services/`

## DI Container (Dishka)

6 providers in `pocketquant.api.di/`:
- CoreProvider: Settings, EventBus, Mediator
- PersistenceProvider: Database, Cache, repositories
- InfrastructureProvider: BrokerFactory, TradingView, JobScheduler
- MarketDataProvider: BarAppService, QuoteAppService, sync jobs
- TradingProvider: OrderAppService, PositionAppService, StrategyAppService
- HandlerProvider: All CQRS handlers

Routes use `FromDishka[Mediator]` + `DishkaRoute` (NOT `Depends()`)

## Key Architecture Decisions

- **IBrokerFactory protocol** in core — StrategyAppService depends on protocol, BrokerFactory (api) implements it
- **PaperBroker in core** — shared by backtest engine and paper trading mode
- **Backtest repos in backtest package** — `backtest_repository.py`, `optimization_repository.py` live in backtest, not core (avoid circular deps)
- **Namespace packages** — no `__init__.py` at `pocketquant/` level (PEP 420)
- **Async suspension points** — every `await` is a preemption point (also `yield` in async generators, hidden awaits in `container.get()`, `async for` / `async with` / `gather`). Wire deps before consumers (publish-before-subscribe), finish setup before `yield` in `AsyncIterator` factories, no `await` inside atomic blocks, cleanup in `try/finally`. See `docs/code-standards.md` → "Async Suspension Points — Await Is Preemption" for the 6 sub-patterns.

## Schema Consolidation

No empty subclasses. Use base classes directly:
- Repository methods work with domain entities directly (Bar.to_mongo(), Bar.from_mongo())

## Naming Conventions

**Principle:** Suffixes encode architectural role. Domain concepts (entities, VOs, enums, domain services) get NO suffix — they ARE the domain language.

### Files & Directories

- **Python files:** `snake_case.py` — e.g., `bar_builder.py`, `sync_jobs.py`, `bar_repository.py`
- **Directories:** `snake_case/` — e.g., `sync_one/`, `get_ohlcv/`, `bar/`
- **Standard domain files:** `entities.py`, `events.py`, `value_objects.py`, `enums.py`, `interfaces.py`
- **CQRS handlers:** `{feature}/{operation}/` with `command.py`|`query.py` + `handler.py` + `route.py` + `__init__.py`

### Class Naming by Layer

| Layer | Pattern | Suffix | Examples |
|-------|---------|--------|----------|
| Entities | `{Name}` or `{Name}Aggregate` | None / `Aggregate` (complex only) | `Bar`, `Symbol`, `OrderAggregate` |
| Events | `{Entity}{PastTense}Event` | `Event` | `OrderFilledEvent`, `BarCompletedEvent` |
| Enums | `{Concept}` | None | `Interval`, `OrderType`, `OrderSide` |
| Value Objects | `{Concept}` | None | `PnL`, `OHLCV`, `BarRange` |
| Domain Services | `{DescriptiveName}` | None | `BarBuilder`, `PerformanceCalculator` |
| Repositories | `{Entity}Repository` | `Repository` | `BarRepository`, `OrderRepository` |
| Infra Interfaces | `I{Concept}` | `I` prefix | `IBroker`, `IDataProvider`, `IBrokerFactory` |
| Infra Impls | `{Source}{Type}` | None (source-prefixed) | `OkxBroker`, `TradingViewClient`, `PaperBroker` |
| App Services | `{Entity}AppService` | `AppService` | `BarAppService`, `StrategyAppService` |
| CQRS Queries | `{Get\|List}{Entity}Query` | `Query` | `GetOHLCVQuery`, `ListOrdersQuery` |
| CQRS Commands | `{Action}{Entity}Command` | `Command` | `SyncSymbolCommand`, `StartStrategyCommand` |
| CQRS Handlers | `{MatchingRequest}Handler` | `Handler` | `SyncSymbolHandler`, `ListOrdersHandler` |
| DTOs | `{Name}Response` | `Response` | `SyncResponse`, `QuoteResponse` |
| Routes | (functions) | — | `async def sync_symbol(...)` |
| Middleware | `{Name}Middleware` | `Middleware` | `RateLimitMiddleware`, `IdempotencyMiddleware` |
| Errors | `{Name}Error` | `Error` | `AppError`, `NotFoundError`, `DomainError` |
| DI Providers | `{Domain}Provider` | `Provider` | `CoreProvider`, `TradingProvider` |
| Configs | `{Name}Config` | `Config` | `BacktestConfig`, `WebhookConfig` |
| Background Jobs | (functions) | — | `sync_5m()`, `sync_integrity()` |

## Known Issues

Post-migration notes and unresolved questions were retired from the docs tree; see git history (`git log -- docs/migration-doubts-and-notes.md`) if needed.
