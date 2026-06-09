# Code Standards & Patterns

Architecture: Clean Architecture + DDD + CQRS + Dishka. Type checker: Pyright.

This document focuses on architectural patterns and conventions. For current startup commands and test commands, use [README](../README.md).

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
# Note: Handler registration in pocketquant/app/di/container.py via register_handlers(container)

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
# Handler registration in pocketquant/app/di/ (no separate register.py file)
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
- `packages/pocketquant-app/src/pocketquant/app/di/container.py` — `create_container()`, handler registration
- `packages/pocketquant-app/src/pocketquant/app/di/providers/` — 6 Provider classes
- `packages/pocketquant-app/src/pocketquant/app/main.py` — Lifespan: create container, `setup_dishka()`

**6 Providers (initialization order):**
1. **CoreProvider** - Settings, EventBus (max_history=50), Mediator
2. **PersistenceProvider** - Database, Cache, repositories
3. **InfrastructureProvider** - BrokerFactory, JobScheduler, IDataProvider, HealthCoordinator
4. **ExecutionProvider** - OrderAppService, PositionAppService, StrategyAppService, RiskCheckHandler
5. **MarketDataProvider** - BarAppService, QuoteAppService
6. **HandlerProvider** - All CQRS handlers

**Benefits:**
- Auto-resolution by type hint (no manual wiring)
- Scoped lifecycle (Scope.APP for singletons, Scope.REQUEST for per-request)
- Type-safe (IDE autocomplete, pyright validation)
- Centralized initialization order via PROVIDERS list

### 4. Repository Pattern (Instance-Based Data Access)

All data access through instance methods in `packages/pocketquant-infrastructure/src/pocketquant/infrastructure/persistence/repositories/`. `Database` injected via constructor. All repositories inherit from `BaseRepository`.

**12 Repositories:** BarRepository, OrderRepository, PositionRepository, SubscriptionRepository, BacktestRepository, BacktestOrderRepository, BacktestTradeRepository, OptimizationRepository, SymbolRepository, TrackedSymbolRepository, SyncStatusRepository, JobHistoryRepository

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
- No schemas/ directory

**`Database` public surface (in order of preference for app code):**
1. `get_collection(name)` — used by repositories / CQRS handlers (default).
2. `database` property — raw `AsyncDatabase` for migrations and admin ops
   (rename_collection, list_collection_names, drop_index, multi-collection
   aggregations). Avoid in repository or handler code.
3. `get_database()` — alias of `database` property, retained for backward
   compatibility. New code should prefer `database`.

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
# BinanceClient implements the IDataProvider port
class BinanceClient(IDataProvider):
    async def fetch_ohlcv(self, symbol: str, interval: Interval, n_bars: int = 1000) -> list[Bar]:
        # symbol is composite {code}:{exchange}; auto-paginates when n_bars > 1000
        ...
```

**Rationale:** Concrete adapter behind a core `IDataProvider` port (DIP) — isolates external I/O, clean error handling, easy to mock for testing.

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
        # 1. Fetch from infrastructure (symbol is composite {code}:{exchange})
        bars = await self.provider.fetch_ohlcv(
            cmd.symbol, cmd.interval, cmd.n_bars
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
2. Add to HandlerProvider in `packages/pocketquant-app/src/pocketquant/app/di/handlers.py` via `provide(HandlerClass, scope=Scope.APP)`
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

### 9.5. Integrity Repair Flow

Bar integrity repair: check → delete misaligned → resync gaps → verify.

**5-Step Process:**
1. **Check:** `check_integrity()` → list misaligned + missing bars
2. **Delete:** `bar_repo.delete_many_by_ids(misaligned_ids)`
3. **Resync:** `SyncSymbolCommand(..., skip_filter=True, n_bars=5000)` — bypasses filter to fill gaps
4. **Verify:** re-check integrity, capture `still_missing` count + ranges
5. **Log:** warn if gaps remain after repair

**Why skip_filter:** `filter_new_bars` queries `bar_repo.find_datetimes` to drop only records whose datetime already exists. Correct for sparse gaps. `skip_filter=True` is still useful for repair flows that want to force re-upsert (e.g., to refresh OHLCV values that may have shifted), bypassing both the existence check AND the wire-noise reduction.

**Usage:** Background job `sync_repair` (every 12h) or manual `/api/v1/market-data/integrity/repair` endpoint. Returns `RepairResult` with deleted count, gaps_resynced, still_missing, still_missing_ranges.

### 10. Schema Consolidation (Use Base Classes)

Eliminate redundant empty Create subclasses. Use base classes directly for repository operations.

**Rule:** One schema definition per domain concept (OHLCV, Symbol, Order, etc.). No Create subclasses.

**Consolidation:**
- No schemas directory — repositories use domain entities directly
- All entities have `to_mongo()` / `from_mongo()` for MongoDB persistence
- Factory methods: `Symbol.create()`, `OrderAggregate.create()`, `PositionAggregate.open()`

**Benefits:** Single schema (easier maintenance), simpler type hints, no duplication.

### 11. Strategy Implementation Pattern

Implement IStrategy interface for custom trading strategies:

```python
from pocketquant.core.domain.concepts.strategy.interfaces import IStrategy

class HitNRun2Strategy(IStrategy):
    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.entry_lookback_bars = self.get_parameter("entry_lookback_bars", 240)
        self.sl_lookback_bars = self.get_parameter("sl_lookback_bars", 480)
        self.tp_lookback_bars = self.get_parameter("tp_lookback_bars", 60)
        self.max_loss_pct = self.get_parameter("max_loss_pct", 0.01)
        self.min_profit_pct = self.get_parameter("min_profit_pct", 0.02)

    async def on_bar(self, bar: dict) -> Signal | None:
        """Breakdown buy / breakup sell on 1m closed bars."""
        prev_lows = list(self._lows)[-self.entry_lookback_bars:]
        self._lows.append(bar["low"])
        if len(prev_lows) < self.sl_lookback_bars:
            return None  # warmup

        if bar["close"] < min(prev_lows):
            sl = max(min(prev_lows), bar["close"] * (1 - self.max_loss_pct))
            tp = max(max(prev_highs_tp), bar["close"] * (1 + self.min_profit_pct))
            return Signal(direction=Direction.LONG, entry_price=bar["close"],
                          stop_loss_price=sl, take_profit_price=tp, ...)
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
| `subscription_id` | string (16-char hex) | Deterministic ID of one (strategy_code, symbol, interval) binding | `"a1b2c3d4e5f6g7h8"` | MongoDB `subscriptions._id` (immutable after creation) | Computed as `sha256(f"{strategy_code}\|{symbol}\|{interval}")[:16]`. Uniquely keys in-memory strategy instance, order, position, backtest result docs. |
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

**Hash Stability Invariant (CRITICAL):**
The deterministic subscription ID is computed from the **value**, not the parameter name:
```python
subscription_id = sha256(f"{strategy_code}|{symbol.upper()}|{interval_val}")[:16]
```
Renaming `strategy_id` → `strategy_code` does NOT change existing subscription IDs.
Existing subscriptions with hash `a1b2c3...` continue to use that hash even after migration.
Backward-compatibility test: `tests/trading_test/test_subscription_deterministic_id.py:test_back_compat_known_id_hitnrun2_btc_1m`

## Code Organization Guidelines

### File Naming

Use kebab-case with descriptive names that indicate purpose:

```
quote_routes.py                # FastAPI routes for quotes
quote_app_service.py           # QuoteAppService business logic
bar_builder.py                 # BarBuilder domain service
bar_repository.py              # BarRepository data access
binance_client.py              # BinanceClient (IDataProvider) for REST API
binance_websocket_client.py    # BinanceWebSocketClient for @aggTrade WebSocket
```

### Class Naming by Layer

Suffixes encode architectural role. Domain concepts (entities, VOs, enums, domain services) get NO suffix — they ARE the domain language. CQRS handlers live in `{feature}/{operation}/` with `command.py`|`query.py` + `handler.py` + `route.py` + `__init__.py`.

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
pyright packages/pocketquant-backtest/src/pocketquant/backtest/handlers/  # Check specific module
```

## Performance Considerations

### Blocking I/O

Run blocking operations in thread pool to avoid blocking event loop:

```python
# Good: native async I/O (Binance via aiohttp)
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

### Environment Variables

Never hardcode configuration. Use `.env` for local development:

```python
# In packages/pocketquant-core/src/pocketquant/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongodb_url: MongoDsn
    redis_url: RedisDsn
    log_format: str = "json"  # or "console"
    okx_api_key: Optional[str] = None       # live trading only (Binance market data needs no auth)
    okx_secret_key: Optional[str] = None
    okx_passphrase: Optional[str] = None

    class Config:
        env_file = ".env"
```

### Secrets (Production)

- Use environment variable in production (from secret management)
- Never commit `.env` or `.env.example` with secrets
- Use `.env.example` as template with dummy values

```bash
# .env.example (dummy values)
MONGODB_URL=mongodb://localhost:52017
OKX_API_KEY=api_key_placeholder
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

## Quality Checklist

- [ ] All type hints present | [ ] No syntax errors (ruff check passes)
- [ ] Code formatted (ruff format) | [ ] Type checking passes (pyright)
- [ ] Tests pass (pytest) | [ ] Coverage ≥80%
- [ ] No blocking I/O in async | [ ] Error paths tested
- [ ] Environment variables used | [ ] No secrets in code/config
