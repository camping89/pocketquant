# Code Standards & Patterns

**Last Updated:** 2026-03-22 | **Coverage:** 278 Python files, 13,641 LOC in packages/ | **Architecture:** Clean Architecture + DDD + CQRS + Dishka | **Type Checker:** Pyright | **Port:** 41920

## Clean Architecture Rules

### Dependency Direction (MANDATORY)
```
Features (routes, commands, queries, handlers)
  ↓ imports
Application (orchestrators: StrategyAppService, BacktestAppService, etc.)
  ↓ imports
Domain (aggregates, value objects, events)
  ↑ imports ← Infrastructure (brokers, providers, persistence)

CRITICAL: No reverse dependencies.
- Domain NEVER imports from Application, Features, or Infrastructure
- Enforced via test_domain_purity.py (AST check)
```

### Layer Responsibilities

| Layer | Responsibility | I/O |
|-------|---|---|
| **Domain** | Business rules, validation, events | NONE (zero I/O) |
| **Application** | Orchestrators, state machines, coordination | Calls infrastructure |
| **Features** | HTTP routes, request parsing, response formatting | Calls application handlers |
| **Infrastructure** | DB, brokers, providers, scheduling, HTTP | All external I/O |
| **Common** | Mediator, EventBus, middleware, utilities | Cross-cutting concerns |

## Architecture Patterns

### 1. Vertical Slice Architecture (Operation-First)

Features are thin HTTP routing layers. **Operations are primary organizational unit.** All business logic moved to Application layer.

```
features/
├── market_data/         (routes, commands, queries, handlers)
├── backtesting/         (routes, commands, queries, handlers)
├── strategy/            (routes, commands, queries, handlers)
├── trading/             (routes, commands, queries, handlers)
└── risk/                (routes, commands, queries, handlers)

Operation-First Structure:
├── operation_name/             # Each operation is a folder
│   ├── command.py or query.py  # Request definition (Pydantic)
│   ├── handler.py              # CQRS handler (@handles decorator)
│   ├── route.py                # FastAPI route (optional)
│   └── __init__.py
├── router.py                   # Feature router (aggregates all operations)
└── __init__.py
# Note: Handler registration in pocketquant/api/di/container.py via register_handlers(container)

IMPORTANT: No business logic in features/. All logic in:
- Application layer (orchestrators, state machines)
- Domain layer (aggregates, value objects, events)

Clean Architecture Example (backtesting):

**Features Layer (Thin routes):**
```
features/backtesting/
├── run/                        # Operation: Execute backtest
│   ├── command.py              # RunBacktestCommand
│   ├── handler.py              # RunBacktestHandler (calls Application-layer BacktestAppService)
│   └── route.py                # POST /api/v1/backtest/run
├── optimize/                   # Operation: Optimize parameters
│   ├── command.py
│   ├── handler.py              # Calls Application-layer GridOptimizationAppService
│   └── route.py
├── get_result/
│   ├── query.py
│   └── handler.py
├── list_results/
│   ├── query.py
│   └── handler.py
└── router.py                   # Aggregate all operation routes
# Handler registration in pocketquant/api/di/ (no separate register.py file)
```

**Application Layer (Orchestrators):**
```
application/backtesting/
├── backtest_app_service.py          # BacktestAppService (engine, execute backtest)
├── grid_optimization_app_service.py           # GridOptimizationAppService (parameter search)
├── historical_replay_app_service.py # HistoricalReplayAppService (inject bars)
├── result_collector.py         # ResultCollector (collect fills, metrics)
└── models/                     # DTOs, config models
```

**Domain Layer (Pure logic):**
```
domain/backtest/
└── services/
    └── performance_calculator.py  # Calculate Sharpe, Sortino, max drawdown (pure, no I/O)
```

**Key:** Handler in features/ calls BacktestAppService in application/, which uses PerformanceCalculator from domain/. PerformanceCalculator has ZERO I/O imports.

**Key Rules:**
1. Each operation is a folder (command/query.py + handler.py + optional route.py)
2. Operations are self-contained use cases (no shared state between operations)
3. Handler 5-step pattern: Fetch Infrastructure → Validate Domain → Persist Infrastructure → Invalidate Cache → Publish Events
4. Routes are thin (parse, delegate, respond)
5. NO business logic in features/ (all in Application or Domain)
6. Operation folders may be nested (sync/sync_one/, sync/sync_bulk/)
7. No cross-feature dependencies (loose coupling via infrastructure singletons)

**Rationale:**
- Tight cohesion within feature (all operation code together)
- Loose coupling between features (no direct imports)
- Clean architecture (domain pure, application orchestrates, features delegate)
- Easy to add/remove operations without cascading changes

### 2. Application Layer (Orchestrators & State Machines)

Business logic that coordinates Domain + Infrastructure. Unlike Domain (pure logic), Application can call Infrastructure for I/O.

**Examples:**
- **StrategyAppService:** Listen to market events (bars, ticks), call strategy.on_bar(), check risk, submit orders via broker
- **BacktestAppService:** Load strategy, inject historical bars, collect fills, calculate metrics
- **BarAppService:** Aggregate incoming ticks into OHLCV bars at multiple intervals
- **OrderAppService:** Order state machine, recovery on startup
- **PositionAppService:** Track open/closed positions, calculate P&L

**No CQRS in this layer.** These are business orchestrators called by CQRS handlers.

```python
# Application-layer service (orchestrates domain + infrastructure)
class StrategyAppService:
    def __init__(self, broker: IBroker, event_bus: EventBus):
        self.broker = broker
        self.event_bus = event_bus

    async def on_bar(self, bar: OHLCVBar) -> None:
        # 1. Domain: Call strategy logic
        signal = await self.strategy.on_bar(bar)

        # 2. Infrastructure: Check risk
        approved = await risk_check(signal)

        # 3. Infrastructure: Execute via broker
        if approved:
            order = await self.broker.submit_order(approved.order)

        # 4. Infrastructure: Publish event
        await self.event_bus.publish(SignalGeneratedEvent(...))
```

**Rules:**
- Can import Domain and Infrastructure
- No CQRS decorators (@handles, @event_handler)
- Stateful (maintains runtime state)
- Called by CQRS handlers in features/ layer
- Often singletons (StrategyAppService, QuoteAppService) or per-request (DataSyncService)

### 3. Dependency Injection (Dishka)

**dishka** library with 6 providers + type-hint-based auto-resolution. Container resolves all dependencies automatically by matching `__init__` parameter types.

```python
# Routes use dishka FastAPI integration
from dishka.integrations.fastapi import FromDishka
from pocketquant.core.common.mediator import Mediator

@router.post("/sync")
async def sync(mediator: FromDishka[Mediator], cmd: SyncCommand):
    return await mediator.send(cmd)
```

**Key Files:**
- `packages/pocketquant-api/src/pocketquant/api/di/container.py` — `create_container()`, handler registration
- `packages/pocketquant-api/src/pocketquant/api/di/providers/` — 6 Provider classes
- `packages/pocketquant-api/src/pocketquant/api/main.py` — Lifespan: create container, `setup_dishka()`

**6 Providers (initialization order):**
1. **CoreProvider** - Settings, EventBus (max_history=100), Mediator
2. **PersistenceProvider** - Database, Cache, 7 repositories
3. **InfrastructureProvider** - Brokers, TradingView, Scheduler
4. **MarketDataProvider** - BarAppService, QuoteAppService
5. **TradingProvider** - OrderAppService, PositionAppService
6. **HandlerProvider** - All 27 CQRS handlers

**Benefits:**
- Auto-resolution by type hint (no manual wiring)
- Scoped lifecycle (Scope.APP for singletons, Scope.REQUEST for per-request)
- Type-safe (IDE autocomplete, pyright validation)
- Centralized initialization order via PROVIDERS list

### 4. Repository Pattern (Instance-Based Data Access)

All data access through instance methods in `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/`. `Database` injected via constructor. All repositories inherit from `BaseRepository`.

**7 Repositories:** BarRepository (renamed from OHLCVRepository), OrderRepository, PositionRepository, BacktestRepository, OptimizationRepository, SymbolRepository, SyncStatusRepository

**Key Pattern:**
```python
class BarRepository(BaseRepository):
    async def upsert_many(self, records: List[Bar]) -> int:
        collection = self._collection("bars")
        docs = [bar.to_mongo() for bar in records]  # Entity serialization
        # bulk upsert...
        return len(records)
```

**Centralized Persistence (in `pocketquant-core`):**
- Database (PyMongo, NOT Motor) and Cache (Redis) managed by dishka
- BaseRepository: `_collection()` helper, `Database` injected
- Domain entities handle serialization via `to_mongo()` / `from_mongo()`
- No schemas/ directory (deleted 2026-03-15)

**Benefits:** Instance-based design, easy to test, domain purity, single source of truth

### 5. Service Pattern (Business Logic)

All services receive dependencies via constructor, managed by DI container:

#### Stateful Services

```python
# QuoteAppService - constructed in lifespan, stored in Services dataclass
class QuoteAppService:
    def __init__(self, settings: Settings, cache: Cache, bar_manager: BarAppService):
        self._settings = settings
        self._cache = cache
        self._bar_manager = bar_manager
```

#### Lifecycle-Managed Services (Async Init/Shutdown)

```python
# OrderAppService - async init in lifespan, explicit shutdown in finally block
class OrderAppService:
    def __init__(self, event_bus: EventBus, order_repository: OrderRepository):
        self._event_bus = event_bus
        self._order_repo = order_repository

# In lifespan:
order_manager = OrderAppService(event_bus, order_repo)
await order_manager.load_pending_orders()  # async init
```

**Rationale:** All dependencies explicit in constructor. Lifespan manages lifecycle with try/finally for clean shutdown.

### 6. Provider Pattern (External Integrations)

Encapsulate external API calls with clean interface:

```python
# TradingViewClient
class TradingViewClient:
    def __init__(self, username: Optional[str], password: Optional[str]):
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def get_bars(self, symbol: str, exchange: str, interval: str, n_bars: int):
        # Run blocking tvdatafeed in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._fetch_bars, ...)
```

**Rationale:** Isolates blocking I/O from async event loop, clean error handling, easy to mock for testing.

### 7. Event Handler Auto-Discovery Pattern

Register event subscribers automatically using the `@event_handler` decorator:

```python
from pocketquant.core.common.messaging.event_registry import event_handler

class PositionAppService:
    @event_handler(OrderFilledEvent)
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        """Called when order is filled (auto-registered)."""
        await self.update_position(event)

    @event_handler(BarCompletedEvent, QuoteReceivedEvent)
    async def _on_market_event(self, event: DomainEvent) -> None:
        """Called on market data events (auto-registered)."""
        pass
```

Auto-registration during startup:
```python
from pocketquant.core.common.messaging.event_registry import get_event_registry

registry = get_event_registry()
count = registry.register_instance(position_tracker, event_bus)
# All @event_handler methods now subscribed to EventBus
```

**Benefits:**
- Decorative, self-documenting: Clear which methods handle which events
- Auto-discovery: No manual subscribe() calls
- Scalable: Add new handlers without modifying mediator
- Type-safe: Event types checked at decorator definition

### 8. CQRS Handler Pattern (Auto-Discovery)

Separate request handlers for commands (mutate state) and queries (read-only). All handlers extend `Handler[TRequest, TResponse]` and use `@handles(RequestType)` for auto-discovery.

**Rule: One handler per command/query.** `DuplicateHandlerError` thrown at startup if two handlers claim the same request type.

```python
from pocketquant.core.common.mediator import Handler, handles

# Command Handler (mutates state)
@handles(SyncSymbolCommand)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResultDTO]):
    def __init__(self, provider: IDataProvider, bar_repo: BarRepository):
        self.provider = provider
        self.bar_repo = bar_repo

    async def handle(self, cmd: SyncSymbolCommand) -> SyncResultDTO:
        # 1. Fetch from infrastructure
        bars = await self.provider.fetch_ohlcv(
            cmd.symbol, cmd.exchange, cmd.interval, cmd.n_bars
        )

        # 2. Validate via domain (Bar.from_mongo)
        validated_bars = [Bar.from_mongo(bar.to_mongo()) for bar in bars]

        # 3. Persist via infrastructure
        await self.bar_repo.upsert_many(validated_bars)

        # 4. Publish domain events
        await EventBus.publish(HistoricalDataSyncedEvent(...))

        # 5. Return DTO (never return entities)
        return SyncResultDTO(bars_synced=len(bars), status="completed")

# Query Handler (read-only)
@handles(GetBarsQuery)
class GetBarsHandler(Handler[GetBarsQuery, BarsDTO]):
    def __init__(self, bar_repo: BarRepository, cache: Cache):
        self.bar_repo = bar_repo
        self.cache = cache

    async def handle(self, query: GetBarsQuery) -> BarsDTO:
        cache_key = f"bar:{query.symbol}:{query.interval}"

        # 1. Check cache first
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        # 2. Query database
        bars = await self.bar_repo.get_bars(
            query.symbol, query.exchange, query.interval, query.limit
        )

        # 3. Cache result (300s TTL)
        result = BarsDTO(bars=bars, count=len(bars))
        await self.cache.set(cache_key, result, ttl=300)

        # 4. Return DTO
        return result
```

**Handler Responsibilities (5-step pattern):**
1. Receive Command/Query from Mediator
2. Fetch data from Infrastructure (Database, Cache, Providers)
3. Execute domain logic via Domain layer (validation, calculations)
4. Persist results via Infrastructure (Database writes, Cache invalidation)
5. Publish DomainEvents to EventBus (for subscribers to react)
6. Return DTO (never return domain entities)

**Key Rules:**
- Every handler MUST use `@handles(RequestType)` decorator
- One handler per command/query (enforced at startup via `DuplicateHandlerError`)
- Constructor receives dependencies (dishka auto-wires via type hints)
- `handle()` method must be async or sync as needed
- Return DTOs, never domain entities
- Publish domain events for all state changes

**Registration Pattern:**
Handlers auto-discovered at container build time:
1. Implement handler with `@handles(RequestType)` decorator
2. Add to HandlerProvider in `packages/pocketquant-api/src/pocketquant/api/di/handlers.py` via `provide(HandlerClass, scope=Scope.APP)`
3. `register_handlers(container)` in container.py resolves all handlers and registers with Mediator at startup
4. Dependencies resolved by dishka via __init__ type hints (no manual injection)

### 9. Handler Extract-Method Pattern

For complex handlers exceeding ~30 lines with 8+ operations, extract private helper methods. Simple handlers (1-3 ops) should NOT extract methods.

**Guideline:** Extract when handle() becomes unreadable. Each helper does ONE logical operation. Reference: `SyncSymbolHandler` has 8 private helpers (_fetch_bars, _persist_bars, _fail, _success, etc.). See `docs/handler-pipelines.md` for full examples.

**Key Rules:**
- Prefix with `_` (private) to indicate internal use
- Keep `handle()` as readable checklist (no detailed logic)
- Each helper: single-responsibility, async or sync as needed
- Improves testability: easier to test 8 focused helpers than one giant method

### 10. Schema Consolidation (Use Base Classes)

Eliminate redundant empty Create subclasses. Use base classes directly for repository operations.

**Rule:** One schema definition per domain concept (OHLCV, Symbol, Order, etc.). No Create subclasses.

**Applied Changes (2026-03-15):**
- Schemas directory deleted — repositories use domain entities directly
- All entities have `to_mongo()` / `from_mongo()` for MongoDB persistence
- Factory methods: `Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`

**Benefits:** Single schema (easier maintenance), simpler type hints, no duplication.

### 11. Strategy Implementation Pattern

Implement IStrategy interface for custom trading strategies:

```python
from pocketquant.core.domain.concepts.strategy.interfaces import IStrategy

class MACrossoverStrategy(IStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = self.get_parameter("fast_period", 10)
        self.slow_period = self.get_parameter("slow_period", 20)

    async def on_bar(self, bar: dict) -> Signal | None:
        """Called on each new bar."""
        # Update moving averages
        self.fast_ma = calculate_ma(self.recent_bars, self.fast_period)
        self.slow_ma = calculate_ma(self.recent_bars, self.slow_period)

        # Generate signal
        if self.fast_ma > self.slow_ma and self.prev_fast_ma <= self.prev_slow_ma:
            return StrategySignal(action="buy", symbol=bar.symbol, quantity=100)
        elif self.fast_ma < self.slow_ma and self.prev_fast_ma >= self.prev_slow_ma:
            return StrategySignal(action="sell", symbol=bar.symbol, quantity=100)

        return None  # No signal

    async def on_tick(self, quote: QuoteTick) -> Optional[StrategySignal]:
        """Called on each tick (optional)."""
        return None

    async def on_fill(self, fill: Fill) -> None:
        """Called when order is filled (optional)."""
        pass
```

**Strategy guidelines:**
- Implement only methods you need (on_bar is mandatory)
- Return StrategySignal or None
- Keep logic pure (use domain layer for calculations)
- Store state as instance variables
- No direct broker/database access (StrategyAppService manages execution)

### 12. Domain Layer Patterns (Pydantic BaseModel + MongoDB Persistence)

Domain entities use **Pydantic BaseModel** (not dataclasses) with built-in MongoDB persistence:
- **Entities (5):** `Bar`, `OrderAggregate`, `PositionAggregate`, `Symbol` (flattened), `SyncStatus`
- **Deleted Aggregates (Dead Code):** `OHLCVAggregate`, `QuoteAggregate`, `SymbolAggregate`, `SymbolInfo` VO
- **Pattern:** Each aggregate has `to_mongo()` → dict and `@classmethod from_mongo(doc)` → entity
- **Benefits:** Validation, serialization, schema evolution via Pydantic
- **Value Objects:** Frozen via `field(frozen=True)` or `@dataclass(frozen=True)`
- **Events:** `@dataclass(frozen=True, eq=False)` with custom `__eq__` by event_id
- **Rules:** Use `generate_id()` (UUID7), immutable VOs/events, all aggregates extend BaseModel
- **Cache Keys:** Use `build_bar_cache_key()` (renamed from `build_ohlcv_cache_key()`)
- **Collections:** Use `COLLECTION_BARS` (renamed from `COLLECTION_OHLCV`)

## Code Organization Guidelines

### File Naming

Use kebab-case with descriptive names that indicate purpose:

```
quote_routes.py           # FastAPI routes for quotes
quote_app_service.py          # QuoteAppService business logic
quote_aggregator.py       # QuoteAggregator bar building
ohlcv_repository.py       # OHLCVRepository data access
tradingview.py            # TradingViewClient for REST API
tradingview_ws.py         # TradingViewWebSocketClient for WebSocket
```

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
from pocketquant.api.features.market_data.base.models import OHLCV
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

## Commenting & Documentation

**Comments:** Write for WHY (non-obvious logic, workarounds, API quirks). Skip WHAT (obvious code is self-documenting).

**Docstrings:** Minimal. Use type hints to carry heavy lifting. Module-level: brief purpose statement.

## Type Hints

Use full type hints on all public APIs: functions, class attributes, complex types. Tools: `pyright packages/` for type checking.

## Error Handling

**Try-Except:** Catch specific exceptions, never bare `except`. Use structured logging with context.

**Propagation:** Routes catch/return 4xx-5xx, Services catch/log/return error dicts, Repositories propagate.

## Testing Standards

### Test Structure

```
tests/
├── conftest.py              # Pytest fixtures
├── test_market_data.py      # Feature tests
└── integration/
    └── test_sync_service.py
```

### Mocking Singletons

Use pytest fixtures and monkeypatch:

```python
@pytest.fixture
async def mock_database(monkeypatch):
    """Fixture to mock Database singleton."""
    mock_db = AsyncMock()
    monkeypatch.setattr("src.common.database.Database._database", mock_db)
    return mock_db

@pytest.mark.asyncio
async def test_sync_symbol(mock_database):
    mock_database.get_collection.return_value.find_one.return_value = None
    result = await service.sync_symbol("AAPL", "NASDAQ", "1d", 500)
    assert result["status"] == "completed"
```

### Test Coverage

Minimum 80% code coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

Focus on:
- Service methods (business logic)
- Repository methods (data access)
- Error paths (exceptions and edge cases)
- Integration points (API contracts)

### Running Tests

```bash
pytest                                    # All tests
pytest tests/test_market_data.py         # Single file
pytest tests/test_market_data.py::test_sync  # Single test
pytest -v --tb=short                     # Verbose output
pytest --pdb                             # Drop into debugger on failure
```

## Code Quality Tools

### Linting (ruff)

```bash
ruff check .              # Lint check
ruff check . --fix        # Auto-fix issues
```

**Rules enforced:**
- Unused imports
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
pyright packages/                 # Type check entire packages
pyright packages/pocketquant-api/src/pocketquant/api/features/backtesting/  # Check specific module
```

## Performance Considerations

### Blocking I/O

Run blocking operations in thread pool to avoid blocking event loop:

```python
# Good: Thread pool isolation
loop = asyncio.get_event_loop()
bars = await loop.run_in_executor(self.executor, self._fetch_bars, symbol)

# Bad: Blocking event loop
bars = tvdatafeed_client.get_bars(symbol)  # Blocks!
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

## Configuration & Secrets

### Environment Variables

Never hardcode configuration. Use `.env` for local development:

```python
# In packages/pocketquant-core/src/pocketquant/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_url: MongoDsn
    redis_url: RedisDsn
    log_format: str = "json"  # or "console"
    tradingview_username: Optional[str] = None
    tradingview_password: Optional[str] = None

    class Config:
        env_file = ".env"
```

### Secrets (Production)

- Use environment variable in production (from secret management)
- Never commit `.env` or `.env.example` with secrets
- Use `.env.example` as template with dummy values

```bash
# .env.example (dummy values)
MONGODB_URL=mongodb://localhost:27018
TRADINGVIEW_USERNAME=username_placeholder
```

## File Size Targets

| Component | Current | Target |
|-----------|---------|--------|
| quote_aggregator.py | 368 LOC | <400 (complex algorithm exception) |
| quote_app_service.py | 236 LOC | <200 (consider split if modified) |
| data_sync_service.py | 244 LOC | <200 |
| handler.py (operation) | <150 LOC | <200 (single operation per file) |
| router.py (feature) | <300 LOC | <400 (all operations for one feature) |

**Current largest files (acceptable but monitor):**
- `quote_aggregator.py` - 368 LOC (core algorithm, complexity justified)
- Individual `router.py` files - <300 LOC each (operation-centric routes)

## UUID Generation (Time-Ordered IDs)

All aggregates use UUID7 (time-ordered) for better database indexing:

```python
from pocketquant.core.common.uuid import generate_id, generate_id_str

# Generate UUID v7 (timestamp-based, sortable)
order_id = generate_id()        # UUID object
order_id_str = generate_id_str() # "550e8400-e29b-41d4-a716-446655440000"
```

**Migration from UUID4:**
- Old: Random UUID4 (bad for B-tree indexes, cluster keys)
- New: UUID7 (timestamp-based, naturally sorts chronologically)
- Benefit: Better MongoDB shard key performance, faster range queries

All aggregates migrated:
- OHLCVAggregate, OrderAggregate, PositionAggregate, etc.
- All repositories use UUID7 for _id generation

## Clean Architecture Rules (MANDATORY)

| Layer | Rules |
|-------|-------|
| **Domain** | ❌ No I/O imports (pymongo, redis, aiohttp) ✅ Pydantic BaseModel with to_mongo/from_mongo ✅ Validation in __post_init__ ✅ Pure logic only |
| **Application** | ❌ No CQRS decorators ✅ Orchestrate domain + infrastructure ✅ Stateful services ✅ Called by feature handlers |
| **Features** | ❌ No business logic ✅ Thin routes ✅ @handles decorator ✅ Call Application services |
| **Infrastructure** | ❌ Never imported by Domain ✅ Brokers, persistence, scheduling ✅ All external I/O |

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

## Quality Checklist

- [ ] All type hints present | [ ] No syntax errors (ruff check passes)
- [ ] Code formatted (ruff format) | [ ] Type checking passes (pyright)
- [ ] Tests pass (pytest) | [ ] Coverage ≥80%
- [ ] No blocking I/O in async | [ ] Error paths tested
- [ ] Environment variables used | [ ] No secrets in code/config
