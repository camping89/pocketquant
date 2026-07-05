# Code Standards & Patterns

Architecture: Clean Architecture + DDD + Dishka. Type checker: Pyright.

This document focuses on architectural patterns and conventions. For current startup commands and test commands, use [README](../README.md).

## Clean Architecture Rules

### Dependency Direction (MANDATORY)
```
Features (routes, commands, queries, handlers)
  ↓ imports
Application (orchestrators: StrategyAppService, BacktestAppService, etc.)
  ↓ imports
Domain (aggregates, value objects, events)
  ↑ imports ← Adapters (brokers, providers, persistence in core.*)

CRITICAL: No reverse dependencies.
- Domain NEVER imports from Application, Features, or Adapters
- Enforced via test_domain_purity.py (AST check)
```

### Layer Responsibilities

| Layer | Responsibility | I/O |
|-------|---|---|
| **Domain** | Business rules, validation, events | NONE (zero I/O) |
| **Services** | Orchestrators, command/query services, coordination | Calls adapters |
| **Routes** | HTTP routing, request parsing, response formatting | Calls services |
| **Adapters** | DB, brokers, providers, scheduling, HTTP | All external I/O |
| **Common** | EventBus, middleware, utilities | Cross-cutting concerns |

## Architecture Patterns

### 0. Route Layer Rules

Routes are thin HTTP handlers. All business logic lives in services.

| Component | Location | Responsibility |
|-----------|----------|---|
| **Route** | `src/pocketquant/app/routes/{feature}.py` | Parse request → build Command/Query → call service → return DTO |
| **Command Service** | `src/pocketquant/{pkg}/{feature}_command_service.py` | Mutate state: validate, persist, publish events |
| **Query Service** | `src/pocketquant/{pkg}/{feature}_query_service.py` | Read-only: fetch, serialize, return DTO |

**Route signature pattern:**
```python
from dishka.integrations.fastapi import FromDishka, DishkaRoute

@router.post("/path", status_code=201, route_class=DishkaRoute)
async def endpoint_name(
    body: RequestBody,
    cmd_svc: FromDishka[SomeCommandService],
) -> dict:
    return await cmd_svc.method(SomeCommand(...))
```

**Key rules:**
- Never try/catch in routes or services (exceptions propagate → global handler)
- Use `FromDishka[ServiceType]`, never `Depends()`
- Pydantic validates input automatically
- Return status codes explicitly: `201` (created), `204` (no content), `404` (not found)

### 1. Route + Service Layer Architecture

Routes are thin HTTP layers. Services provide business logic via 5-step pattern: Fetch → Validate → Persist → Invalidate Cache → Publish Events.

**Structure:**
```
routes/{feature}.py                    # HTTP handlers
{pkg}/{feature}_command_service.py    # Write logic
{pkg}/{feature}_query_service.py      # Read logic (cached)
core/domain/{entity}/                  # Pure logic (no I/O)
core/persistence/repositories/         # Data access
```

**Example:** Route → BacktestCommandService → BarRepository + PerformanceCalculatorDomainService (domain, pure).

**Key Rules:**
1. Routes: parse, inject service, delegate, respond (no business logic)
2. Services: one method per command/query, accept Pydantic model, return DTO
3. Use `FromDishka[ServiceClass]` for DI (never `Depends()`)
4. NO try/catch in routes/services (propagate to global handler)
5. Service methods publish domain events for all state changes

### 2. Application Layer (Orchestrators & State Machines)

Stateful services orchestrating domain + adapters. Can call Adapters (unlike Domain). Called by service methods, often singletons.

**Examples:** StrategyAppService (market events → signals → orders), BarAppService (tick aggregation), OrderAppService (state machine), PositionAppService (P&L tracking).

**Rules:** Can import Domain + Adapters. Stateless (no decorators). Initialized in lifespan, injected by DI.

### 3. Dependency Injection (Dishka)

dishka resolves dependencies by type hint. Routes inject via `FromDishka[ServiceType]`. Providers in `src/pocketquant/app/di/` initialized in order: CoreProvider → PersistenceProvider → InfrastructureProvider → Services/AppServices. Setup in lifespan via `setup_dishka(app, container)`.

### 4. Repository Pattern (Instance-Based Data Access)

All data access via instance methods in `src/pocketquant/core/persistence/repositories/`. All repositories inherit from `BaseRepository`, use `_collection(name)` helper, inject `Database` via constructor. Domain entities serialize via `to_mongo()` / `from_mongo()`. No schemas/ directory. Benefits: testable, pure domain, single source of truth.

### 5. Service Pattern (Business Logic)

All dependencies via constructor (managed by DI). Stateful services initialized in lifespan with try/finally for clean shutdown. Example: `OrderAppService` calls `await load_pending_orders()` in lifespan before any handler uses it.

### 6. Provider Pattern (External Integrations)

Concrete adapter (e.g., `BinanceAdapter`) behind a core interface (e.g., `IDataProviderPort`). Isolates external I/O, clean error handling, testable.

### 7. Event Handler Auto-Discovery Pattern

Use `@event_handler` decorator on service methods. Auto-register at startup via `registry.register_instance(service, event_bus)`. Clear, scalable, type-safe.

### 8. Exception Handler Registration

Global exception handlers automatically map domain errors to HTTP responses. Register at startup in `src/pocketquant/app/main_extensions.py`:

```python
from pocketquant.core.common.exceptions import register_exception_handlers
from fastapi import Request
from fastapi.exceptions import RequestValidationError

register_exception_handlers(app, validation_error_cls=RequestValidationError)
```

**Automatic mapping:**
- `NotFoundError` → 404 JSON `{error: {code, message}}`
- `DomainError` → 400 JSON `{error: {code, message}}`
- `AppError` (base) → 500 JSON `{error: {code, message}}`

Services NEVER try/catch; exceptions propagate to the global handler.

### 8.5. Command/Query Service Pattern

One service method per command/query. Constructor receives dependencies (dishka auto-wires). Method: receive Pydantic Command/Query → fetch adapters → validate domain → persist → publish events → return DTO.

**Template:**
```python
class SomeCommandService:
    def __init__(self, repo: SomeRepository):
        self.repo = repo

    async def handle(self, cmd: SomeCommand) -> dict:
        # Fetch + Validate
        if not await self.repo.exists(cmd.id):
            raise NotFoundError("NOT_FOUND")
        # Persist + Publish
        result = await self.repo.upsert({...})
        await EventBus.publish(SomeEvent(...))
        return result.to_dto()
```

**Worked Example: POST `/api/v1/strategies/{strategy_code}/subscriptions`**

Route:
```python
@strategy_router.post("/{strategy_code}/subscriptions", status_code=201)
async def create_subscription(
    strategy_code: str,
    body: CreateSubscriptionBody,
    cmd_svc: FromDishka[StrategyCommandService],
) -> dict:
    return await cmd_svc.add_symbol(AddSymbolCommand(...))
```

Service:
```python
async def add_symbol(self, cmd: AddSymbolCommand) -> dict:
    if not await self.tracked_symbol_repo.exists(cmd.symbol):
        raise NotFoundError("SYMBOL_NOT_TRACKED")
    sub = Subscription(id=generate_id(), strategy_code=cmd.strategy_id, ...)
    await self.subscription_repo.add(sub)
    return sub.to_dto()
```

Flow: Route → Service → Repository → MongoDB. Exceptions propagate to global handler → 4xx/5xx JSON.

### 9. Service Extract-Method Pattern

For complex service methods exceeding ~30 lines with 8+ operations, extract private helper methods. Simple methods (1-3 ops) should NOT extract methods.

**Guideline:** Extract when the method becomes unreadable. Each helper does ONE logical operation. Reference: complex sync services may have 8 private helpers (_fetch_bars, _persist_bars, _fail, _success, etc.).

**Key Rules:**
- Prefix with `_` (private) to indicate internal use
- Keep `handle()` as readable checklist (no detailed logic)
- Each helper: single-responsibility, async or sync as needed
- Improves testability: easier to test 8 focused helpers than one giant method

### 9.5. Integrity Repair Flow

Bar integrity repair: check → delete misaligned → resync gaps → verify.

**5-Step Process:**
1. **Check:** `check_integrity()` → list misaligned + missing bars
2. **Delete:** `bar_repo.delete_many_by_ids(misaligned_ids)`
3. **Resync:** `SyncSymbolCommand(..., skip_filter=True, n_bars=5000)` — bypasses filter to fill gaps
4. **Verify:** re-check integrity, capture `still_missing` count + ranges
5. **Log:** warn if gaps remain after repair

**Why skip_filter:** `filter_new_bars` queries `bar_repo.find_datetimes` to drop only records whose datetime already exists. Correct for sparse gaps. `skip_filter=True` is still useful for repair flows that want to force re-upsert (e.g., to refresh OHLCV values that may have shifted), bypassing both the existence check AND the wire-noise reduction.

**Usage:** Background job `sync_repair` (every 12h) hoặc endpoint `/api/v1/market-data/integrity/repair`. `repair_integrity()` trả về `dict` gồm deleted count, gaps_resynced, still_missing, still_missing_ranges.

### 10. Schema Consolidation (Use Base Classes)

Eliminate redundant empty Create subclasses. Use base classes directly for repository operations.

**Rule:** One schema definition per domain concept (OHLCV, Symbol, Order, etc.). No Create subclasses.

**Consolidation:**
- No schemas directory — repositories use domain entities directly
- All entities have `to_mongo()` / `from_mongo()` for MongoDB persistence
- Factory methods: `Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`

**Benefits:** Single schema (easier maintenance), simpler type hints, no duplication.

### 11. Strategy Implementation Pattern

Implement `IStrategyService` interface. Implement `on_bar_completed(bar)` (mandatory), optionally `on_quote_received(tick)`, `on_order_filled(order, fill_price)`. Return `Signal | None`. Keep pure logic, no broker/database (StrategyAppService manages execution). Lifecycle: `on_start()` → `on_bar_completed()` / `on_quote_received()` / `on_order_filled()` → `on_stop()`.

### 12. Domain Layer Patterns (Pydantic BaseModel + MongoDB Persistence)

Domain entities use **Pydantic BaseModel** (not dataclasses) with built-in MongoDB persistence:
- **Entities (5):** `Bar`, `OrderAggregate`, `PositionAggregate`, `Symbol` (flattened), `SyncStatus`
- **Pattern:** Each aggregate has `to_mongo()` → dict and `@classmethod from_mongo(doc)` → entity
- **Benefits:** Validation, serialization, schema evolution via Pydantic
- **Value Objects:** Frozen via `field(frozen=True)` or `@dataclass(frozen=True)`
- **Events:** `@dataclass(frozen=True, eq=False)` with custom `__eq__` by event_id
- **Rules:** Use `generate_id()` (UUID7), immutable VOs/events, all aggregates extend BaseModel
- **Cache Keys:** `build_bar_cache_key()`
- **Collections:** `COLLECTION_BARS`

### 12.5. DDD Classification Guide (When to Use an Aggregate)

**When to use an Aggregate:**
- Entity has **invariants** to protect (e.g. `OrderAggregate` state machine)
- Entity has **lifecycle behavior** (e.g. `PositionAggregate` open → scale → close)
- Entity **owns other entities** within a consistency boundary
- Entity **emits domain events** from business operations

**When NOT to use an Aggregate:**
- Entity is a **data record** (e.g. `Bar` — just OHLCV data, serialization only)
- Class is an **event factory** with no state (anti-pattern)
- Class is **never instantiated** in practice
- Behavior is **CRUD-only** — use a plain entity or model

**Project Rules:**
1. Aggregates earn their complexity — no invariants, no aggregate.
2. Events can be created directly where needed — no wrapper aggregate required.
3. Value objects stay as frozen dataclasses — simple, immutable, no persistence.
4. DTOs live in the application layer — they're infrastructure, not domain.

### 12.6. Primary Key Rule — UUIDv7 Only (MANDATORY)

**Every persisted document we control MUST use a UUIDv7 `_id`.** No hash keys, no natural keys, no Mongo ObjectId, no composite-string keys.

**Rules:**
1. Generate every id via `generate_id()` (returns `UUID`) from `core/common/uuid.py`. Domain entities declare `id: UUID`; serialize with `"_id": str(self.id)` in `to_mongo()`. Never declare `id: str` for a persisted entity.
2. **Never** derive `_id` from business data (no `sha256(...)`, no composite-symbol-as-id, no slug).
3. **Never** rely on Mongo's default ObjectId — always set `_id` explicitly to a uuid7.
4. **Uniqueness and idempotency belong on secondary unique indexes, never on `_id`.** If a `(strategy_code, symbol, interval)` triple must be unique, enforce it with a unique compound index — not by making it the primary key.

**The one allowed exception — third-party library-owned collections.** Collections whose `_id` is written by an external library (e.g. APScheduler's MongoDBJobStore → `apscheduler_jobs`) are exempt. We do **not** patch or fork the library to force uuid7. This exception applies ONLY to collections we did not author; every collection our own code writes follows the rule with no exception.

**Rationale:** one id type across all code we own. Predictable, time-ordered, no special cases to remember, no representation drift — without coupling to third-party storage internals.

**Anti-patterns (all forbidden):**
```python
# ❌ hash / natural / objectid as primary key
_id = hashlib.sha256(f"{a}|{b}|{c}".encode()).hexdigest()[:16]
_id = symbol                       # composite string as id
id: str                            # persisted entity declaring str id
# (and: letting Mongo assign a default ObjectId)

# ✅ correct — every persisted entity
from pocketquant.core.common.uuid import UUID, generate_id
id: UUID = Field(default_factory=generate_id)
def to_mongo(self) -> dict: return {"_id": str(self.id), ...}
# uniqueness/idempotency → separate unique index, e.g.
await collection.create_index([("strategy_code", 1), ("symbol", 1), ("interval", 1)], unique=True)
```

## Composite Symbol Format

**Format:** `{CODE}:{EXCHANGE}` (e.g., `BTCUSDT:BINANCE`, `AAPL:NYSE`)

**Rules:**
- Single immutable `symbol: str` field replaces `(code: str, exchange: str)` pairs across domain entities
- Exchange is opaque postfix—business logic never decomposes `symbol` into parts
- URL-encoded: `:` serialized as `%3A` in path segments (e.g., `/api/v1/bar/BTCUSDT%3ABINANCE`)
- JSON/database: raw `:` preserved (no encoding inside payloads)
- Cache keys: `quote:latest:{symbol}`, `bar:current:{symbol}:{interval}`, etc.
- Affected entities: Bar, Order, Position, Symbol, SyncStatus, Subscription, TrackedSymbol

**Example Repository Usage:**
```python
# composite symbol (single field, no separate exchange param)
await bar_repo.find(symbol="BTCUSDT:BINANCE", interval="1d")
```

## Strategy ID Disambiguation

**CRITICAL DISTINCTION:** Three IDs must never be confused.

| ID | Type | Meaning | Example | Persistence | Notes |
|---|---|---|---|---|---|
| `strategy_code` | string | Template name registered in `STRATEGY_REGISTRY` | `"hitnrun2"` | Class name (immutable) | Identifies which strategy class to instantiate. Used to look up the class and load from persistent subscriptions. |
| `subscription_id` | string (uuid7) | ID of one (strategy_code, symbol, interval) binding | `"019ebe98-209c-71f2-af3d-981810e2d783"` | MongoDB `subscriptions._id` (immutable after creation) | Random uuid7 via `generate_id()`. Uniqueness of the triple is enforced by the unique compound index `ix_subscriptions_dedup_triple`, not the id. Keys in-memory strategy instance, order, position, backtest result docs. |
| `template_id` | **DEPRECATED** | Old name for path param that held strategy_code | was `"hitnrun2"` in URL | — | Not used. Use `strategy_code`; treat any legacy `template_id` reference as `strategy_code`. |

**Field Renames (Live Refactor):**
- MongoDB `strategy_subscriptions` → `subscriptions` (collection name)
- Subscription doc: `strategy_id: "{code}"` → `strategy_code: "{code}"` (field name + semantics)
- Order doc: `strategy_id: "{subscription_id}"` → `subscription_id: "{subscription_id}"` (field name + semantics)
- Position doc: `strategy_id: "{subscription_id}"` → `subscription_id: "{subscription_id}"` (field name + semantics)
- Backtest doc: `strategy_id: "{code}"` → `strategy_code: "{code}"`; `subscription_id` preserved

**Repository Method Renames:**
- `SubscriptionRepository.list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`
- `OrderRepository.find_by_strategy(strategy_id)` → `find_by_subscription(subscription_id)`
- `PositionRepository.get_by_strategy(strategy_id)` → `get_by_subscription(subscription_id)`
- `BacktestRepository.list_by_strategy(strategy_id)` → `list_by_strategy_code(strategy_code)`

**HTTP Route Semantics (Post-Refactor):**
- `POST /strategies/{strategy_code}/subscriptions` — create subscription for this template
- `POST /subscriptions/{sub_id}/start` — start this subscription instance
- `GET /subscriptions/?strategy_code=X` — filter subscriptions by template (optional)

**Dedup Invariant (CRITICAL):**
Subscription ids are random uuid7 — they say nothing about the triple. The only duplicate guard is the unique compound index:
```python
await collection.create_index(
    [("strategy_code", 1), ("symbol", 1), ("interval", 1)],
    unique=True, name="ix_subscriptions_dedup_triple",
)
```
`symbol` is normalized (`.upper()`) in `add_symbol` before store — the index is case-sensitive, so that normalization is load-bearing.
Concurrency test: `tests/core_test/infra/persistence/test_subscription_repository.py:test_concurrent_add_same_triple_one_doc_one_error`

## Code Organization Guidelines

### File Naming

Use kebab-case với tên mô tả mục đích (suffix trong tên file mã hóa layer):

```
quote_routes.py                      # QuoteRoute functions (API HTTP handlers)
quote_app_service.py                 # QuoteAppService (application orchestrator)
bar_builder_domain_service.py        # BarBuilderDomainService (domain logic)
engulfing_strategy_service.py        # EngulfingStrategyService (strategy impl)
strategy_service_interface.py        # IStrategyService (strategy interface)
bar_repository.py                    # BarRepository (data access)
data_provider_port.py                # IDataProviderPort (infra boundary)
binance_adapter.py                   # BinanceAdapter (infra impl)
okx_broker_adapter.py                # OKXBrokerAdapter (source + type → separate adapter)
```

### Class Naming by Layer

Tên class + file tự mã hóa layer/role. Suffix theo bảng dưới. Domain concepts (entities, VOs, enums) không có suffix — chúng là ngôn ngữ miền.

| Layer | Pattern | Class Suffix | File Suffix | Ví dụ |
|-------|---------|--------|--------|--------|
| Entities | `{Name}` hoặc `{Name}Aggregate` | None / `Aggregate` | `.py` | `Bar`, `Symbol`, `OrderAggregate` |
| Events | `{Entity}{PastTense}Event` | `Event` | `.py` | `OrderFilledEvent`, `BarCompletedEvent` |
| Enums | `{Concept}` | None | `.py` | `Interval`, `OrderType`, `OrderSide` |
| Value Objects | `{Concept}` | None | `.py` | `PnL`, `OHLCV`, `BarRange` |
| **Domain Services** | `{Name}DomainService` | `DomainService` | `*_domain_service.py` | `PositionSizerDomainService`, `BarBuilderDomainService`, `PerformanceCalculatorDomainService` |
| **Domain Strategy (Impl)** | `{Name}StrategyService` | `StrategyService` | `*_strategy_service.py` | `EngulfingStrategyService`, `HitNRun2StrategyService` |
| **Domain Strategy (Interface)** | `IStrategyService` | `IStrategyService` | `strategy_service_interface.py` | `IStrategyService` |
| Repositories | `{Entity}Repository` | `Repository` | `*_repository.py` | `BarRepository`, `OrderRepository` |
| **Infra Port (Interface)** | `I{Concept}Port` | `Port` | `*_port.py` (1 port/file) | `IBrokerPort`, `IBrokerFactoryPort`, `IDataProviderPort`, `IRealtimeQuoteProviderPort` |
| **Infra Adapter (Impl)** | `{Source}[{Type}]Adapter` | `Adapter` | `*_adapter.py` | `OKXBrokerAdapter`, `BinanceAdapter`, `PaperBrokerAdapter`, `OKXWebSocketAdapter` |
| **Helper** | `{Name}Helper` | `Helper` | `*_helper.py` | (utility pattern; follow naming rule when used) |
| **App Services** | `{Name}AppService` | `AppService` | `*_app_service.py` | `StrategyReconcileAppService`, `BacktestSandboxAppService`, `WsSubscriptionAppService`, `BacktestReportAppService` |
| Query Models | `{Get\|List}{Entity}Query` | `Query` | `*_query.py` | `GetOHLCVQuery`, `ListOrdersQuery` |
| Command Models | `{Action}{Entity}Command` | `Command` | `*_command.py` | `SyncSymbolCommand`, `StartStrategyCommand` |
| CQRS Services | `{Domain}{Command\|Query}Service` | `Service` | `*_service.py` | `StrategyCommandService`, `BacktestQueryService` |
| DTOs | `{Name}Response` | `Response` | `.py` | `SyncResponse`, `QuoteResponse` |
| Routes | (functions) | — | `*_routes.py` | `async def sync_symbol(...)` |
| Middleware | `{Name}Middleware` | `Middleware` | `*_middleware.py` | `RateLimitMiddleware` |
| Errors | `{Name}Error` | `Error` | `.py` | `AppError`, `NotFoundError`, `DomainError` |
| DI Providers | `{Domain}Provider` | `Provider` | `*_provider.py` | `CoreProvider`, `ExecutionProvider` |
| Configs | `{Name}Config` | `Config` | `*_config.py` | `BacktestConfig`, `RiskConfig` |
| Background Jobs | (functions) | — | `*_jobs.py` | `sync_1m()`, `sync_integrity()` |

### Naming Principles & Exemptions

**Ba nguyên tắc cốt lõi:**

1. **Tên class + file tự mã hóa layer/role.** Đọc `PositionSizerDomainService` hoặc `binance_adapter.py` biết ngay layer không cần xem folder.

2. **Không stack 2 doer-suffix generic (`-er`/`-or`) trong 1 tên.** Nếu bị dính (vd một class vừa mang `-Tracker` vừa `-Helper` → `*TrackerHelper`), dùng gerund: `*TrackingHelper`. **Ngoại lệ:** danh từ nghiệp vụ kết `-er` (vd `Broker`) không tính là doer-suffix → `BrokerAdapter` hợp lệ.

3. **Data class + role đã có suffix chuẩn → giữ nguyên.** Exempt list bên dưới.

**Exempt list** (giữ suffix hiện tại, KHÔNG ép convention):

| Nhóm | Ví dụ |
|---|---|
| CQRS | `*CommandService`, `*QueryService` (app layer, request-scoped ≠ orchestrator) |
| Persistence | `*Repository` |
| DI / cross-cutting | `*Provider`, `*Middleware` |
| App handler | `RiskCheckHandler`, `event_handler` (decorator) |
| Infra factory/scheduler | `BrokerFactory`, `JobScheduler` |
| Infra sub-component (OKX) | `OkxMessageParser`, `OkxOrderMapper`, `OkxPositionMapper`, `OkxReconnectionHandler`, `OkxStateReconciler`, `BrokerFactory`, `JobScheduler` |
| Data class | Entity, VO, enum, event, `*Command`/`*Query`/`*Response` |

### Module Size

Keep individual files under 200 LOC for optimal context management:

- If a file exceeds 200 LOC, split into focused modules
- Use composition (import and delegate) rather than inheritance
- Extract utility functions into separate modules
- Create dedicated service classes for complex logic

**Current Status:**
- All modules within limit
- Largest: `quote_aggregator.py` (368 LOC - exception due to complexity)
- Most: 150-250 LOC

### Import Organization

**Example (Features layer - Pydantic allowed):**
```python
# 1. Standard library
import asyncio
from datetime import datetime
from typing import Optional, List

# 2. Third-party
from pydantic import BaseModel  # OK in Features/Config layers
import structlog

# 3. Local
from pocketquant.core.common.database import Database
from pocketquant.core.common.logging import get_logger
from pocketquant.app.features.market_data.base.models import OHLCV
```

**Example (Domain layer - Stdlib dataclasses only):**
```python
# 1. Standard library
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, ClassVar

# 2. Local (no third-party, no I/O)
from pocketquant.core.domain.shared.domain_event import DomainEvent
from pocketquant.core.common.uuid import generate_id

# NOTE: No pydantic, pymongo, redis, aiohttp imports in domain/
```

## Comment Policy — Explain WHY, Not WHAT

Comments cost LOC and rot out of sync with code. Default: no comment. Add one only when the code cannot speak for itself. Applies to Python (`#`, `"""`) and TS/JS (`//`, `/** */`) alike.

### REMOVE / never write

- Comments restating the line (`# increment counter`, `# validate creds` over obvious validation)
- Banner / divider / count labels (`# Trading (4)`, `# ---- setup ----`, `# Market data (16)`)
- Docstrings echoing the symbol name (`"""Get bar."""` on `get_bar`)
- Filler Arrange/Act/Assert markers that add nothing
- Plan/phase/finding refs — explain the invariant, not the origin

### KEEP / write only for

- **WHY:** races, ordering/suspension constraints, publish-before-subscribe, await-preemption notes, invariants, trade-offs
- **Hacks / workarounds** + external-system quirks (OKX, Mongo, Redis, asyncio, APScheduler)
- `# type: ignore[...]` / `// @ts-expect-error` / `// eslint-disable` — always with their reason
- Warnings about non-obvious failure modes (`# benign — already dropped`)
- Docstrings documenting params / contracts / edge cases / non-obvious return semantics
- Test comments explaining scenario intent or non-obvious setup

### Examples

```python
# KEEP — load-bearing ordering note (see "Await Is Preemption")
# Wire the event bus before any handler can publish: container.get() awaits,
# so a subscriber resolved first would miss publish-before-subscribe events.

# REMOVE — restates the call
# Get the bar from the repository
bar = await repo.get(bar_id)
```

**Route docstrings:** name-echo docstrings on FastAPI routes are removed even though OpenAPI summaries may blank — only docstrings carrying param/contract/edge-case content survive.

**Docstrings:** Minimal. Let type hints carry the heavy lifting. Module-level: brief purpose statement only when non-obvious.

## Type Hints

Use full type hints on all public APIs: functions, class attributes, complex types. Tools: `pyright` for type checking (scopes from `pyrightconfig.json`).

## Error Handling

**Try-Except:** Catch specific exceptions, never bare `except`. Use structured logging with context.

**Propagation:** Routes catch/return 4xx-5xx, Services catch/log/return error dicts, Repositories propagate.

## Testing Standards

Minimum 80% code coverage (Service methods, repository methods, error paths, integration points):

```bash
pytest --cov=src --cov-report=term-missing
pytest tests/test_market_data.py::test_sync --pdb  # Run + debug
```

Use pytest fixtures + monkeypatch for mocking:

```python
@pytest.fixture
async def mock_database(monkeypatch):
    mock_db = AsyncMock()
    monkeypatch.setattr("src.common.database.Database._database", mock_db)
    return mock_db
```

## Code Quality Tools

### Linting (ruff)

```bash
ruff check .              # Lint check
ruff check . --fix        # Auto-fix issues
```

**Rules enforced:**
- Unused imports (no imports of old class names like `BinanceAdapter`, `IStrategyService`, `PaperBrokerAdapter`)
- Undefined names
- Syntax errors
- Duplicate code
- Complexity metrics

### Formatting (ruff)

```bash
ruff format .             # Auto-format code
```

### Type Checking (Pyright)

We use **Pyright** (via Pylance in VSCode), not mypy:
- **3-5x faster** than mypy for large codebases
- **Native VSCode integration** via Pylance extension
- **Better type inference** for complex patterns
- **Pydantic v2 native support** (no plugin needed)

```bash
pyright                                 # Type check (scopes from pyrightconfig.json)
pyright src/pocketquant/engine/backtest/  # Check specific module
```

## Performance Considerations

### Blocking I/O

Run blocking operations in thread pool to avoid blocking event loop:

```python
# Good: native async I/O (Binance via BinanceAdapter/aiohttp)
bars = await self.provider.fetch_ohlcv(symbol, interval, n_bars)

# Bad: blocking call on the event loop
bars = some_sync_client.get_bars(symbol)  # Blocks!
# If a sync lib is unavoidable, isolate it:
#   await loop.run_in_executor(self.executor, sync_fn, symbol)
```

### Bulk Operations

Use bulk upserts instead of individual inserts:

```python
# Good: Single bulk operation
await BarRepository.upsert_many(records)  # One round trip to DB

# Bad: Loop of individual inserts
for record in records:
    await BarRepository.insert_one(record)  # N round trips!
```

### Cache Invalidation

Use pattern-based deletion for correctness (vs selective):

```python
# Good: Pattern-based deletion (simple, correct)
await Cache.delete_pattern("bar:AAPL:*")

# Bad: Selective deletion (easy to miss keys)
await Cache.delete(f"bar:AAPL:NYSE:1d:100")
```

### Concurrency

Use asyncio.Lock for shared state:

```python
# Good: Lock protects bar builder state
async with self._lock:
    self._bar_builders[interval].update_ohlc(tick)

# Bad: No protection against race conditions
self._bar_builders[interval].update_ohlc(tick)
```

### Async Suspension Points — "Await Is Preemption"

**One-line rule:** every `await` is a preemption point. The event loop may resume any other ready coroutine here. State another coroutine reads must be valid **before** the suspension point that lets it run.

Mental shortcut: `await` ≈ `Thread.yield()`. If you wouldn't trust a value across `Thread.yield()` in a threaded program, don't trust it across an `await`.

**What counts as a suspension point (including the non-obvious ones):**

| Construct | Suspension? | Notes |
|---|---|---|
| `await coro()` | Yes | The obvious one. |
| `await asyncio.sleep(0)` | Yes | Explicit yield even with 0. |
| `yield x` inside `async def` | **Yes** | Easy to miss. Async generators + `@asynccontextmanager` use this. |
| `async for x in iterable` | Yes | Calls `await iterable.__anext__()` each loop. |
| `async with cm:` | Yes (entry & exit) | Calls `await cm.__aenter__()` and `__aexit__()`. |
| `await asyncio.gather(...)` | Yes | Children interleave between each other's awaits. |
| `await container.get(X)` | Yes if provider does I/O | Dishka `AsyncIterator` factories hide awaits. |
| Plain assignment, `if`, arithmetic | No | Synchronous between awaits — use this for atomic regions. |

**Six sub-patterns to apply.** Same root cause, different shapes:

**1. Publish-before-subscribe** — wire deps BEFORE the call that starts a worker (scheduler, queue consumer, websocket reader, background task). After the call returns, the worker is observable to the event loop and may dispatch at the next `await`.

```python
# Anti-pattern (racy)
register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),  # scheduler now LIVE
)
# set_sync_container() inside register_sync_jobs runs AFTER scheduler may dispatch

# Fix
set_sync_container(container)   # wire global FIRST
register_sync_jobs(
    container=container,
    job_scheduler=await container.get(JobScheduler),
)
```

Why it bites: APScheduler persists `next_run_time` across restarts. First tick dispatches anything due within `misfire_grace_time` (per-job setting, e.g. 120s for sync_1m, 3600s for daily jobs). If module-level globals not yet set → `RuntimeError` on first line of every dispatched job. Orphan recovery runs at startup via `recover_orphan_jobs()` to catch jobs stuck in `running` state (crash resilience).

**2. Initialize-before-first-await** — never `await` on something that exposes a half-built object to other tasks. Construct fully, then publish.

```python
# Anti-pattern
async def make_session():
    sess = Session()
    REGISTRY[sess.id] = sess          # published
    sess.user = await load_user()     # other tasks see sess with no user

# Fix
async def make_session():
    user = await load_user()           # all I/O first
    sess = Session(user=user)          # construct atomically
    REGISTRY[sess.id] = sess           # publish fully-formed
```

**3. TOCTOU across `await`** — the classic race condition, async edition.

```python
# Anti-pattern
if user.balance >= amount:        # CHECK
    await db.debit(user, amount)  # USE — balance may have changed → double-spend

# Fix A: storage-layer atomicity (preferred)
result = await db.try_debit(user, amount)  # WHERE balance >= amount

# Fix B: per-key async lock
async with user_locks[user.id]:
    if user.balance >= amount:
        await db.debit(user, amount)
```

General rule: re-read shared state after every `await`, hold a lock across the `await`, or push the invariant into the storage layer.

**4. Atomic blocks must have no `await`** — between paired reads/writes of shared state, no suspension.

```python
# Anti-pattern: lost increment
counter = counters[key]
await some_io()
counters[key] = counter + 1   # another coroutine may have done the same → lost update

# Fix: atomic between awaits
counters[key] = counters[key] + 1
await some_io()
```

`dict[key] += 1` is atomic in CPython between awaits (single bytecode region under GIL). **Not** atomic across an `await`.

**5. `yield` in `@asynccontextmanager` / `AsyncIterator` factory IS a suspension point.** All setup before `yield`, cleanup in `try/finally` after.

```python
# Anti-pattern (Dishka factory)
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    GLOBAL_HANDLE = svc          # published before initialized
    yield svc                    # caller now has svc and may use it
    await svc.connect()          # NEVER runs at the right time

# Fix
@provide(scope=Scope.APP)
async def my_service(self) -> AsyncIterator[Service]:
    svc = Service()
    await svc.connect()          # all setup BEFORE yield
    try:
        yield svc
    finally:
        await svc.aclose()       # cleanup in finally — survives cancellation
```

**6. Cancellation lands at any `await`.** `asyncio.CancelledError` may be raised at the next `await` after `task.cancel()`. Cleanup not in `try/finally` may not run.

```python
# Anti-pattern: money disappears if cancelled between debit and credit
async def transfer():
    await db.debit(src, amount)
    await network.notify()        # cancellation here → credit never runs
    await db.credit(dst, amount)

# Fix: transactional storage (preferred)
async with db.transaction():
    await db.debit(src, amount)
    await db.credit(dst, amount)

# Or: try/finally + compensating action
async def transfer():
    debited = False
    try:
        await db.debit(src, amount)
        debited = True
        await db.credit(dst, amount)
    except (asyncio.CancelledError, Exception):
        if debited:
            await db.credit(src, amount)  # compensate
        raise
```

**Symmetry check:** when two adjacent subsystems do similar wiring (e.g. `backtest_jobs` and `sync_jobs`), diff their startup sequences. Asymmetric ordering is almost always a bug.

**Pre-`await` checklist.** Before every `await`, ask:
- Does this publish a handle / register a callback / start a worker? If yes, is the object fully initialized?
- What invariants am I leaving in some intermediate state?
- Did I just read a value that another coroutine could modify before my next line uses it?
- If `CancelledError` lands here, will cleanup run? Should this be in a `try/finally` or `asyncio.shield`?
- Does this `async for` / `async with` / `gather` hide more suspension points than I'm thinking about?

**Worked-example reference:** `plans/reports/debugger-260524-1324-sync-jobs-container-race.md`

## Configuration & Secrets

Never hardcode. Use `.env` (local) and environment variables (prod). Never commit `.env` or secrets. Define in `src/pocketquant/core/config.py::Settings` with Pydantic.



## Clean Architecture Rules (MANDATORY)

| Layer | Rules |
|-------|-------|
| **Domain** | ❌ No I/O imports (pymongo, redis, aiohttp) ✅ Pydantic BaseModel with to_mongo/from_mongo ✅ Validation in __post_init__ ✅ Pure logic only |
| **Services** | ❌ No decorators ✅ Orchestrate domain + adapters ✅ Stateful services ✅ Called by routes |
| **Routes** | ❌ No business logic ✅ Thin HTTP handlers ✅ Inject services via FromDishka ✅ Call service methods |
| **Adapters** | ❌ Never imported by Domain ✅ Brokers, persistence, scheduling ✅ All external I/O |

## Datetime Serialization (API Responses)

When serializing `datetime` to JSON for frontend consumption, **always use `to_utc_iso()`**:

```python
from pocketquant.core.common.time import to_utc_iso

# Good: consistent UTC, JavaScript-safe
"next_run": to_utc_iso(job.next_run_time)   # → "2026-04-14T01:43:57Z" or None

# Bad: malformed if datetime has tz offset (e.g. +07:00Z)
"next_run": dt.isoformat() + "Z"

# Bad: missing Z suffix, JS parses as local time
"next_run": dt.isoformat()
```

**Internal use** (logging, cache keys): bare `.isoformat()` is fine.

## Deprecated Patterns (DO NOT USE)

- Business logic in features/ → move to Application layer
- Direct DB calls outside persistence/ → use repository pattern
- Pydantic BaseModel in domain/ → use stdlib dataclasses (domain must be zero I/O)
- Bare `except:` clauses → catch specific exceptions
- Synchronous blocking I/O in async code → use ThreadPoolExecutor
- UUID4 for IDs → use UUID7 (time-ordered, B-tree friendly)
- Manual DI wiring → use Dishka providers
- Direct Database.get_collection() outside persistence/ → use BaseRepository._collection()
- Handwritten schema classes → use domain entities with to_mongo/from_mongo

## Import Contracts (Dependency Boundaries)

Enforce via `import-linter` in `pyproject.toml`. Common surface:

| From | To | Via |
|------|----|----|
| Routes | Command/Query Service | `FromDishka[ServiceType]` |
| Services | Repository | Constructor DI |
| Services | Exceptions | `raise NotFoundError`, `raise DomainError` |
| Routes | Exception Handler | Global registration |
| Repositories | MongoDB | `Database.get_collection()` |

No reverse deps (routes ← services, services ← repositories). Domain never imports from Adapters/Application/Features.

## Quality Checklist

- [ ] All type hints present | [ ] No syntax errors (ruff check passes)
- [ ] Code formatted (ruff format) | [ ] Type checking passes (pyright)
- [ ] Tests pass (pytest) | [ ] Coverage ≥80%
- [ ] No blocking I/O in async | [ ] Error paths tested
- [ ] Environment variables used | [ ] No secrets in code/config
