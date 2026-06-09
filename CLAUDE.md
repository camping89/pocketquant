# CLAUDE.md — PocketQuant

**Architecture:** 6-package monorepo (5 Python uv workspace + 1 Node frontend)

## Monorepo Structure

6 packages under `packages/`. The 5 Python packages share the `pocketquant.*` namespace and form the uv workspace. `pocketquant-web` is a separate Node/Vite SPA, **excluded from the uv workspace** (see `pyproject.toml` → `[tool.uv.workspace] exclude`).

```
packages/
├── pocketquant-core/           # 0 deps — pure domain, concepts, common, config, ports + DTOs, all persisted entities
├── pocketquant-infrastructure/ # → core — Database, Cache, all repositories, PaperBroker, binance, scheduler, http client
├── pocketquant-execution/      # → core + infrastructure — shared strategy/order/position/risk app-services
├── pocketquant-backtest/       # → core + infra + execution — backtest engine, optimization, backtest-run orchestration
├── pocketquant-trading/        # → core + infra + execution — live trading, OKX broker, strategy/subscription handlers
├── pocketquant-app/            # → all of the above — FastAPI, DI, composition root
└── pocketquant-web/            # Node/Vite SPA — TanStack Router, lightweight-charts; consumes pocketquant-app HTTP
```

**Dependency graph:** core ◁ infrastructure ◁ execution ◁ {backtest, trading} ◁ app ← web (HTTP only). `backtest` and `trading` are independent siblings — neither imports the other.

## Package Imports

```python
# Core domain + ports/DTOs (no concrete adapters, no repos)
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.backtest import BacktestResult, OptimizationResult
from pocketquant.core.domain.subscription.entities import Subscription
from pocketquant.core.domain.brokers.interfaces import IBroker, IBrokerFactory
from pocketquant.core.domain.brokers.value_objects import OrderResult, AccountBalance
from pocketquant.core.domain.market_data.interfaces import IDataProvider, IRealtimeQuoteProvider
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.config import Settings

# Infrastructure — persistence + concrete adapters
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.infrastructure.persistence.repositories.backtest_repository import BacktestRepository
from pocketquant.infrastructure.brokers.paper.paper_broker import PaperBroker
from pocketquant.infrastructure.scheduling.scheduler import JobScheduler

# Execution — shared strategy engine (used by both backtest + trading)
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.execution.app_services.order_app_service import OrderAppService
from pocketquant.execution.app_services.position_app_service import PositionAppService

# Backtest
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.optimization.models.backtest_config import BacktestConfig

# Trading
from pocketquant.trading.brokers.okx.okx_broker import OKXBroker

# API (composition root)
from pocketquant.app.di.container import create_container
from pocketquant.app.di.broker_factory import BrokerFactory
from pocketquant.app.market_data.app_services.bar_app_service import BarAppService
```

## Domain Structure (Three-Tier DDD)

All persisted domain entities live in `pocketquant-core`:
- **Top-level** (collection-backed): `domain/{bar,order,position,symbol,sync_status,backtest,subscription}/`
- **Ports + DTOs**: `domain/brokers/` (IBroker, IBrokerFactory, OrderResult, AccountBalance, OrderEvent), `domain/market_data/` (IDataProvider, IRealtimeQuoteProvider)
- **Concepts** (non-persisted logic): `concepts/{quote,risk,strategy}/`
- **Shared** (cross-cutting): `domain/shared/{enums,events,value_objects}.py` — `Interval` is the single enum in `enums.py`; `value_objects.py` holds only `INTERVAL_SECONDS`.

Backtest non-persisted services (e.g. `performance_calculator.py`) stay in `pocketquant-backtest/domain/services/`.

Standard file names per folder: `entities.py`, `events.py`, `value_objects.py`, `enums.py`, `interfaces.py`, `services/`

## DI Container (Dishka)

6 providers in `pocketquant.app.di/`:
- CoreProvider: Settings, EventBus, Mediator
- PersistenceProvider: Database, Cache, repositories
- InfrastructureProvider: BrokerFactory, JobScheduler, IDataProvider, HealthCoordinator
- ExecutionProvider: OrderAppService, PositionAppService, StrategyAppService, RiskCheckHandler
- MarketDataProvider: BarAppService, QuoteAppService, sync jobs
- HandlerProvider: All CQRS handlers

Routes use `FromDishka[Mediator]` + `DishkaRoute` (NOT `Depends()`)

## Key Architecture Decisions

- **IBrokerFactory protocol** in core — StrategyAppService depends on the protocol; BrokerFactory (api) implements it
- **Ports + DTOs in core** — IBroker/IBrokerFactory/IDataProvider/IRealtimeQuoteProvider + OrderResult/AccountBalance/OrderEvent live in `core.domain.{brokers,market_data}`; concrete adapters live in infrastructure (DIP)
- **PaperBroker in infrastructure** — `infrastructure.brokers.paper.paper_broker`; shared by backtest engine and paper trading mode
- **All repositories in infrastructure** — every repo (core entities + backtest + trading + job_history) lives in `infrastructure.persistence.repositories`; zero repos in backtest/trading
- **Shared engine in execution** — StrategyAppService/OrderAppService/PositionAppService/RiskCheckHandler in `pocketquant-execution`; both backtest and trading consume it, breaking the old backtest↔trading cycle
- **Strategy injection** — backtest paths inject prepared strategies via the public `StrategyAppService.inject_prepared_strategy()` (connects broker + calls `on_start()` inside the lock); no private-member access
- **Backtest-run orchestration in backtest** — `backtest.jobs.subscription_backtest_jobs` + `backtest.handlers.run_all_backtests` run backtests; trading reads backtest *results* via the infra repo only
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
| DI Providers | `{Domain}Provider` | `Provider` | `CoreProvider`, `ExecutionProvider` |
| Configs | `{Name}Config` | `Config` | `BacktestConfig`, `WebhookConfig` |
| Background Jobs | (functions) | — | `sync_5m()`, `sync_integrity()` |

## Known Issues

Post-migration notes and unresolved questions were retired from the docs tree; see git history (`git log -- docs/migration-doubts-and-notes.md`) if needed.

## [IMPORTANT] Comment Policy — Explain WHY, Not WHAT

Comments cost LOC and rot. Default: no comment. Add one only when code can't speak for itself.

REMOVE / never write:
- Comments restating the line (`# increment counter`, `# validate creds` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`)
- Docstrings echoing the symbol name (`"""Get bar."""` on `get_bar`)
- Filler Arrange/Act/Assert markers that add nothing

KEEP / write only for:
- WHY: races, ordering/suspension constraints, invariants, trade-offs, await-preemption notes
- Hacks / workarounds + external-system quirks (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` / `// @ts-expect-error` / `// eslint-disable` — always with its reason
- Warnings about non-obvious failure modes
- Docstrings documenting params / contracts / edge cases (not name restatement)
- Test comments explaining scenario intent or non-obvious setup

No plan/phase/finding refs in comments — explain the invariant, not the origin.
Applies to Python (`#`, `"""`) and TS/JS (`//`, `/** */`) alike. Full policy + examples: `docs/code-standards.md` → "Comment Policy".

## Documentation Policy

Applies to every `.md` file under `docs/`, `README.md`, and this file.

### Format & language
- All docs are Markdown (`.md`). Use bullet lists and tables over paragraphs. Add a Mermaid v11 or ASCII diagram when a concept has 2+ interacting parts (see monorepo tree + dependency graph above).
- Prose tiếng Việt. Giữ nguyên tiếng Anh, không dịch: tên trong code (`StrategyAppService`, `bar_repository.py`), thuật ngữ kỹ thuật (`dependency injection`, `CQRS handler`, `uv workspace`), định danh ngoài (`PEP 420`, `OKX`, `MongoDB`).
- Không tạo cụm nửa Việt nửa Anh ("cái handler", "service xử lý") — là thuật ngữ thì để nguyên cả cụm tiếng Anh. Từ có bản dịch tiếng Việt rõ nghĩa, không nhầm thì dịch (`database` → "cơ sở dữ liệu"); dịch ra mà phải chú thích tiếng Anh mới hiểu thì giữ tiếng Anh.
- Mỗi câu nói một ý: chủ ngữ → động từ → đối tượng → lý do. Không dùng lượng từ mơ hồ (`some`, `vài`, `thường`) — ghi con số/tập chính xác. Không dùng đại từ mơ hồ (`it`, `nó`, `cái này`) — gọi thẳng tên.

### AS-IS only — describe the current system, not its history

Docs describe the system **as it currently is**. They are NOT a historical record. Git is the history.

**NEVER add to any doc:**
- Changelogs or version-history sections (no `project-changelog.md`, no `## Version History`, no `## Appendix: Notable Refactors`).
- Doc banners / metadata lines: `**Last Updated:**`, `**Version:**`, `**Status:** ... as of <date>`, "Living document", etc.
- Change narratives: "What changed", "Previously…", "Updated (date):", "Refreshed X", "now / no longer", before/after framing.
- Dated migration entries describing a past one-time change (e.g. "Dishka DI Migration (2026-03-13)").

**OK to keep / write:**
- Current behavior, even if implemented by an idempotent boot migration that still runs at startup (describe what it does now, not when it was introduced — drop the date).
- Current "Known Issues", "Limitations & Tech Debt", "Unresolved Questions" — these are present-state facts.
- Stable external IDs (RFC, CVE, SQLSTATE) and in-code symbol names.

**When editing:** if you change behavior, edit the doc to match the new behavior in place. Do not append a "changed" note. State the end state as if it were always true.

**When asked "do we need this doc?":** if it duplicates another doc, fold the unique content into the canonical doc, delete the duplicate, and fix all inbound links. Prefer one source of truth over cross-referencing siblings.
