# Python Mastery Guide for C# Developers
## Learning from PocketQuant: A Production Trading Platform

**Target Audience:** Senior C# developer (10+ years) learning Python
**Learning Style:** Deep foundational understanding with real code, trade-offs, and architectural reasoning

---

# Part 1: Python Syntax Through C# Lens

## 1.1 Type System Philosophy

### C# Mindset: "Compile-time Safety"
```csharp
// C# - Types enforced at compile time
string name = "John";
int age = GetAge();  // Must return int or compile error
```

### Python Mindset: "Duck Typing + Optional Type Hints"
```python
# Python - Types checked at runtime (unless using type checker)
name = "John"        # No type declaration needed
name = 123           # Valid! Python doesn't care at runtime

# Modern Python with type hints (what this project uses)
name: str = "John"   # Type hint - NOT enforced by Python itself
age: int = get_age() # Pyright/mypy checks this at "compile time"
```

### Why This Matters (From This Project)

**From `src/domain/shared/value_objects.py:25-39`:**
```python
@dataclass(frozen=True)
class Symbol:
    """Value object representing a tradeable symbol."""
    code: str          # Type hint tells Pyright "this must be str"
    exchange: str

    def __post_init__(self) -> None:
        # Runtime validation (Python doesn't check types at runtime!)
        if not self.code:
            raise ValueError("Symbol code is required")
        if not self.exchange:
            raise ValueError("Exchange is required")
```

**Key Insight:** Python type hints are for **tooling** (Pyright, IDE IntelliSense), not runtime. You MUST add runtime validation for critical invariants.

### ❌ BAD: Trusting Type Hints at Runtime
```python
@dataclass
class Symbol:
    code: str
    exchange: str
    # No validation - caller could pass None, empty string, or int!

# This would "work" but corrupt your system:
bad_symbol = Symbol(code=None, exchange=123)  # No error at runtime!
```

### ❌ WORST: No Type Hints + No Validation
```python
class Symbol:
    def __init__(self, code, exchange):
        self.code = code
        self.exchange = exchange
# Impossible to understand, impossible to validate, impossible to refactor
```

### ✅ GOOD: Type Hints + Runtime Validation (This Project's Pattern)
```python
@dataclass(frozen=True)  # frozen=True makes it immutable
class Symbol:
    code: str
    exchange: str

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Symbol code is required")
```

---

## 1.2 Class Structure & `self`

### C# Implicit `this`
```csharp
public class OrderService {
    private readonly ILogger _logger;

    public OrderService(ILogger logger) {
        _logger = logger;  // "this" is implicit
    }

    public void Process() {
        _logger.Log("Processing");  // Accessing member without "this"
    }
}
```

### Python Explicit `self`
```python
class OrderService:
    def __init__(self, logger: Logger) -> None:
        self._logger = logger  # "self" is ALWAYS explicit

    def process(self) -> None:
        self._logger.log("Processing")  # Must use "self"
```

### Why Python Requires Explicit `self`

**Technical reason:** Python methods are actually functions. When you call `obj.method()`, Python translates it to `ClassName.method(obj)`. The `self` parameter receives the instance.

**From `src/features/strategy/handlers/command_handlers.py:13-28`:**
```python
class LoadStrategyHandler(Handler[LoadStrategyCommand, str]):
    def __init__(self, engine: StrategyEngine) -> None:
        self._engine = engine  # Store as instance variable

    async def handle(self, request: LoadStrategyCommand) -> str:
        if request.config:
            config = request.config
        elif request.path:
            config = StrategyLoader.load(request.path)
        else:
            raise ValueError("Either config or path must be provided")

        return await self._engine.load_strategy(config)  # Access via self
```

### Private by Convention (No Access Modifiers)

```python
class MyClass:
    def __init__(self):
        self.public = "anyone can access"
        self._protected = "convention: internal use"  # Single underscore
        self.__private = "name-mangled"  # Double underscore (rare)
```

**C# comparison:**
| C# | Python | Enforcement |
|----|--------|-------------|
| `public` | No prefix | None |
| `protected` | `_prefix` | Convention only |
| `private` | `__prefix` | Name mangling (rarely used) |
| `internal` | `_prefix` | Convention only |

---

## 1.3 Dataclasses vs C# Records

### C# 9+ Record
```csharp
public record OHLCV(float Open, float High, float Low, float Close, float Volume);

// Automatically gets: constructor, Equals, GetHashCode, ToString, with-expression
var bar = new OHLCV(100, 110, 95, 105, 1000000);
var modified = bar with { Close = 106 };  // Immutable copy
```

### Python Dataclass

**From `src/domain/shared/domain_event.py:8-21`:**
```python
@dataclass(frozen=True)  # frozen=True = immutable (like C# record)
class DomainEvent:
    """Base class for all domain events."""

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
```

### Decorator Breakdown

| Parameter | Effect | C# Equivalent |
|-----------|--------|---------------|
| `@dataclass` | Auto-generates `__init__`, `__repr__`, `__eq__` | `record` |
| `frozen=True` | Makes instance immutable | `record` (default immutable) |
| `eq=False` | Don't generate `__eq__` (custom identity) | Override `Equals()` |
| `field(default_factory=...)` | Lazy default value | No direct equivalent |

### ❌ BAD: Mutable Domain Events
```python
@dataclass  # No frozen=True
class OrderCreatedEvent:
    order_id: str
    amount: float

# Events should be immutable - this allows corruption:
event = OrderCreatedEvent("123", 100.0)
event.amount = 0  # Bug: Someone mutated the event!
```

### ❌ WORST: Manual `__init__` for Data Classes
```python
class OrderCreatedEvent:
    def __init__(self, order_id, amount):
        self.order_id = order_id
        self.amount = amount

    def __eq__(self, other):
        # Manually implementing what @dataclass gives you free
        return self.order_id == other.order_id and self.amount == other.amount

    def __hash__(self):
        return hash((self.order_id, self.amount))

    def __repr__(self):
        return f"OrderCreatedEvent(order_id={self.order_id}, amount={self.amount})"
# 15 lines vs 5 lines with @dataclass(frozen=True)
```

### ✅ GOOD: Frozen Dataclass (This Project's Pattern)
```python
@dataclass(frozen=True)
class OrderCreatedEvent(DomainEvent):
    order_id: str
    amount: float
    # Automatically immutable, hashable, comparable
```

---

## 1.4 The `field()` Function — Avoiding Mutable Default Trap

### The Python Gotcha (Critical!)

```python
# ❌ DANGEROUS - Same list shared across ALL instances!
@dataclass
class Aggregate:
    events: list = []  # DEFAULT EVALUATED ONCE AT CLASS DEFINITION!

a1 = Aggregate()
a2 = Aggregate()
a1.events.append("event1")
print(a2.events)  # ["event1"] - SHARED! Bug!
```

### Why This Happens

In Python, default argument values are evaluated **once** when the function/class is defined, not when called. For mutable objects (list, dict, set), this means all instances share the same object.

### ✅ CORRECT Pattern (From This Project)

**From `src/domain/ohlcv/aggregate.py:12-19`:**
```python
@dataclass(eq=False)
class OHLCVAggregate:
    """Aggregate root for OHLCV data operations."""

    id: UUID = field(default_factory=uuid4)  # New UUID for each instance
    symbol: str = ""
    exchange: str = ""
    _events: list[DomainEvent] = field(default_factory=list)  # New list for each!
```

**`field(default_factory=list)` creates a NEW empty list for each instance.**

### C# Comparison
```csharp
// C# doesn't have this problem - each "new" creates fresh instance
public class Aggregate {
    public List<DomainEvent> Events { get; } = new();  // Fresh list per instance
}
```

---

# Part 2: Asyncio Deep Dive — The Python Concurrency Model

## 2.1 Event Loop vs Thread Pool (Mental Model Shift)

### C# Async Model: Thread Pool Based
```
┌────────────────────────────────────────┐
│             ThreadPool                  │
│  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐   │
│  │ T1  │  │ T2  │  │ T3  │  │ T4  │   │
│  └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘   │
│     │        │        │        │       │
│  Task A   Task B   Task C   Task D    │
│  (parallel execution on multiple CPUs) │
└────────────────────────────────────────┘
```

### Python Asyncio Model: Single-Threaded Cooperative
```
┌────────────────────────────────────────┐
│         Event Loop (1 Thread)          │
│                                        │
│  ┌──────────────┐                      │
│  │ Coroutine A  │                      │
│  │   await ──────┼──────→ I/O (DB)    │
│  └──────────────┘                      │
│         ↓ switch                       │
│  ┌──────────────┐                      │
│  │ Coroutine B  │ ← runs while A waits │
│  │   await ──────┼──────→ I/O (HTTP)  │
│  └──────────────┘                      │
│         ↓ switch                       │
│  ┌──────────────┐                      │
│  │ Coroutine C  │ ← runs while A,B wait│
│  └──────────────┘                      │
│                                        │
│   NEVER parallel, always cooperative   │
└────────────────────────────────────────┘
```

### Key Difference

| Aspect | C# async/await | Python asyncio |
|--------|---------------|----------------|
| **Threads** | ThreadPool (multiple) | Single thread |
| **Parallelism** | True parallel on multi-core | No parallelism, only concurrency |
| **Blocking** | Blocking one task doesn't affect others | Blocking blocks EVERYTHING |
| **CPU-bound** | Can use multiple cores | Must use multiprocessing |
| **I/O-bound** | Efficient | Very efficient |

## 2.2 The Lock Pattern — Protecting Shared State

### Why Locks in Single-Threaded asyncio?

Even in single-threaded asyncio, **race conditions** can occur because `await` creates suspension points where another coroutine can run.

**From `src/features/market_data/managers/bar_manager.py:141-161`:**
```python
class BarManager:
    """Aggregates real-time ticks into OHLCV bars at multiple intervals."""

    def __init__(self, intervals: list[Interval] | None = None):
        self._intervals = intervals or [...]
        self._bars: dict[str, dict[Interval, BarBuilder]] = defaultdict(dict)
        self._lock = asyncio.Lock()  # ← Protect shared state

    async def add_tick(self, tick: QuoteTick) -> None:
        symbol_key = f"{tick.exchange}:{tick.symbol}".upper()

        async with self._lock:  # ← Only one coroutine at a time
            for interval in self._intervals:
                await self._process_tick_for_interval(tick, symbol_key, interval)
```

### Race Condition Without Lock

```
Without Lock:
────────────────────────────────────────────────────────
Tick1 arrives → reads self._bars["AAPL"] = None
                              ↓
                    Tick2 arrives → reads self._bars["AAPL"] = None
                              ↓
Tick1 creates BarBuilder, sets self._bars["AAPL"] = builder1
                              ↓
                    Tick2 creates BarBuilder, sets self._bars["AAPL"] = builder2
                              ↓
                    builder1 is LOST! Tick1 data disappeared!
────────────────────────────────────────────────────────

With Lock:
────────────────────────────────────────────────────────
Tick1 arrives → acquires lock → reads → creates → sets → releases
                                                              ↓
                    Tick2 arrives → waits... → acquires → reads existing → updates → releases
────────────────────────────────────────────────────────
```

### C# Equivalent
```csharp
private readonly SemaphoreSlim _lock = new(1, 1);

public async Task AddTickAsync(QuoteTick tick) {
    await _lock.WaitAsync();
    try {
        // protected code
    } finally {
        _lock.Release();
    }
}
```

### Python's `async with` Advantage
```python
async with self._lock:
    # Automatically acquires on enter, releases on exit (even on exception)
    await self._process_tick_for_interval(...)
# Lock released here automatically
```

### ❌ BAD: No Lock on Shared Mutable State
```python
class BarManager:
    async def add_tick(self, tick: QuoteTick) -> None:
        # No lock - race condition possible!
        await self._process_tick_for_interval(tick, symbol_key, interval)
```

### ❌ WORST: Using threading.Lock in asyncio
```python
import threading

class BarManager:
    def __init__(self):
        self._lock = threading.Lock()  # WRONG - blocks event loop!

    async def add_tick(self, tick):
        with self._lock:  # Blocks entire event loop!
            await self._process_tick()  # Can't even await inside!
```

### ✅ GOOD: asyncio.Lock with async with
```python
self._lock = asyncio.Lock()

async def add_tick(self, tick):
    async with self._lock:  # Cooperative - other coroutines can run while waiting
        await self._process_tick()
```

## 2.3 The Blocking I/O Problem

### Python's Achilles Heel

**If you call blocking I/O, the ENTIRE event loop freezes:**

```python
# ❌ DISASTER - Freezes everything for 5 seconds
async def fetch_data():
    import requests
    response = requests.get("https://slow-api.com")  # BLOCKING!
    return response.json()

# While this runs, NO other coroutine can execute
# WebSocket disconnects, HTTP requests timeout, everything dies
```

### Solutions

**1. Use async libraries:**
```python
# ✅ Non-blocking
import aiohttp

async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://slow-api.com") as response:
            return await response.json()
```

**2. Run blocking code in thread pool:**

**From `src/infrastructure/tradingview/provider.py` (conceptual):**
```python
# TradingView library is synchronous, must run in thread pool
async def fetch_ohlcv(self, symbol: str, ...) -> list[OHLCVCreate]:
    # Run blocking call in separate thread
    data = await asyncio.to_thread(
        self._tv.get_hist,  # Blocking function
        symbol, exchange, interval, n_bars
    )
    return self._convert_to_ohlcv(data)
```

### C# Comparison
```csharp
// C# handles this automatically - await doesn't block ThreadPool
var response = await httpClient.GetAsync("https://slow-api.com");

// For CPU-bound work:
var result = await Task.Run(() => HeavyComputation());
```

---

# Part 3: Architectural Patterns — DDD/CQRS in Python

## 3.1 CQRS Pattern — Command Query Responsibility Segregation

### The Problem CQRS Solves

Without CQRS, you get "fat controllers" or "fat services":

```python
# ❌ BAD: God service that does everything
class MarketDataService:
    async def sync_symbol(self, symbol, exchange, interval):
        # Validation
        # Fetch from provider
        # Transform data
        # Save to database
        # Invalidate cache
        # Publish events
        # Return response
        # 500 lines of code...

    async def get_ohlcv(self, symbol, exchange):
        # Query logic mixed with command logic
        # Hard to test, hard to scale reads vs writes
```

### CQRS Solution — Separate Read/Write Paths

**From `src/common/mediator/handler.py:1-16`:**
```python
"""Base handler for CQRS commands and queries."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

TRequest = TypeVar("TRequest")
TResponse = TypeVar("TResponse")


class Handler(ABC, Generic[TRequest, TResponse]):
    """Base handler for commands and queries."""

    @abstractmethod
    async def handle(self, request: TRequest) -> TResponse:
        """Handle the request and return a response."""
        ...
```

**From `src/common/mediator/mediator.py:9-28`:**
```python
class Mediator:
    """CQRS dispatcher - routes requests to handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type, Handler] = {}

    def register(self, request_type: type, handler: Handler) -> None:
        """Register a handler for a request type."""
        self._handlers[request_type] = handler

    async def send(self, request: Any) -> Any:
        """Dispatch request to registered handler."""
        handler = self._handlers.get(type(request))
        if not handler:
            raise HandlerNotFoundError(type(request))
        return await handler.handle(request)
```

### How It's Used (From `src/main.py:119-123`)
```python
# Registration (at startup)
sync_handler = SyncSymbolHandler(tv_provider, event_bus)
mediator.register(SyncSymbolCommand, sync_handler)        # Command
mediator.register(BulkSyncCommand, BulkSyncHandler(...))  # Command
mediator.register(GetOHLCVQuery, GetOHLCVHandler())       # Query

# Usage (in routes)
result = await mediator.send(SyncSymbolCommand(symbol="AAPL", ...))
```

### C# MediatR Comparison
```csharp
// C# with MediatR
public class SyncSymbolHandler : IRequestHandler<SyncSymbolCommand, SyncResult> {
    public async Task<SyncResult> Handle(SyncSymbolCommand request, CancellationToken ct) {
        // Same pattern
    }
}

// Registration (via DI container)
services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(typeof(Program).Assembly));

// Usage
var result = await _mediator.Send(new SyncSymbolCommand { Symbol = "AAPL" });
```

### Why This Pattern?

| Benefit | Explanation |
|---------|-------------|
| **Single Responsibility** | Each handler does ONE thing |
| **Testability** | Test handlers in isolation |
| **Scalability** | Scale reads/writes independently |
| **Traceability** | Know exactly what code handles what request |
| **Flexibility** | Add middleware, logging, validation per-handler |

### ❌ BAD: Direct Service Calls
```python
# Routes directly call services
@router.post("/sync")
async def sync_symbol(request: SyncRequest):
    service = MarketDataService()  # Creates new instance each time
    return await service.sync_symbol(request.symbol, ...)
```

### ❌ WORST: Logic in Routes
```python
@router.post("/sync")
async def sync_symbol(request: SyncRequest):
    # All logic in route handler
    records = await provider.fetch(...)
    await database.insert_many(...)
    await cache.delete_pattern(...)
    # 200 lines of code in route...
```

### ✅ GOOD: CQRS Mediator Pattern
```python
@router.post("/sync")
async def sync_symbol(request: SyncRequest, mediator: Mediator = Depends(get_mediator)):
    command = SyncSymbolCommand(symbol=request.symbol, ...)
    return await mediator.send(command)  # Delegation
```

## 3.2 Domain Events — Decoupling Features

### The Problem Direct Calls Create

```python
# ❌ BAD: Tight coupling between features
class SyncSymbolHandler:
    async def handle(self, request):
        await self._save_to_database(data)
        # Now we need to notify strategy engine...
        await self._strategy_engine.on_data_synced(...)  # Direct coupling!
        # And update dashboard...
        await self._dashboard_service.refresh(...)  # More coupling!
        # And send notification...
        await self._notification_service.send(...)  # Even more!
```

### Event-Driven Solution

**From `src/common/messaging/event_bus.py:13-50`:**
```python
class EventBus:
    """In-memory async event bus with FIFO delivery and bounded history."""

    def __init__(self, max_history: int = 50) -> None:
        self._handlers: dict[type, list[Callable[[Any], Any]]] = {}
        self._history: deque[DomainEvent] = deque(maxlen=max_history)

    def subscribe(
        self, event_type: type[TEvent], handler: Callable[[TEvent], Any]
    ) -> None:
        """Register handler for event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all subscribers (FIFO order)."""
        handlers = self._handlers.get(type(event), [])
        for handler in handlers:
            result = handler(event)
            if inspect.iscoroutine(result):
                await result
        self._history.append(event)
```

### Usage Pattern (From `src/features/market_data/sync/handler.py:91-97`)
```python
# In SyncSymbolHandler.handle():

# Create domain aggregate
aggregate = OHLCVAggregate(symbol=symbol, exchange=exchange)

# Record business action (creates event internally)
aggregate.record_sync(
    interval=DomainInterval(interval.value),
    bars_count=upserted_count,
    last_bar_at=latest_bar.datetime if latest_bar else datetime.now(UTC),
)

# Publish all uncommitted events
await self.event_bus.publish_all(aggregate.get_uncommitted_events())

# Handler doesn't know WHO receives the event - decoupled!
```

### Aggregate Event Collection Pattern

**From `src/domain/ohlcv/aggregate.py:34-50`:**
```python
def record_sync(
    self,
    interval: Interval,
    bars_count: int,
    first_bar_at: datetime | None = None,
    last_bar_at: datetime | None = None,
) -> None:
    """Record that historical data was synced."""
    event = HistoricalDataSyncedEvent(
        symbol=self.symbol,
        exchange=self.exchange,
        interval=interval.value,
        bars_count=bars_count,
        first_bar_at=first_bar_at,
        last_bar_at=last_bar_at,
    )
    self._events.append(event)  # Collect, don't publish yet
```

### C# Equivalent
```csharp
// Using MediatR INotification
public class HistoricalDataSyncedEvent : INotification {
    public string Symbol { get; init; }
    public int BarsCount { get; init; }
}

// Handler publishes
await _mediator.Publish(new HistoricalDataSyncedEvent { ... });

// Subscribers
public class StrategyEventHandler : INotificationHandler<HistoricalDataSyncedEvent> {
    public Task Handle(HistoricalDataSyncedEvent notification, CancellationToken ct) { ... }
}
```

### ❌ BAD: Direct Feature-to-Feature Calls
```python
class SyncHandler:
    def __init__(self, strategy_engine, dashboard, notifications):
        self._strategy = strategy_engine  # Knows about strategy
        self._dashboard = dashboard       # Knows about dashboard
        self._notifications = notifications  # Knows about notifications
```

### ❌ WORST: Callback Hell
```python
class SyncHandler:
    def __init__(self):
        self._on_sync_callbacks = []  # Manual callback list

    def register_callback(self, cb):
        self._on_sync_callbacks.append(cb)

    async def handle(self, request):
        # ...
        for cb in self._on_sync_callbacks:
            await cb(data)  # No type safety, no discoverability
```

### ✅ GOOD: Event Bus with Domain Events
```python
# Decoupled - handler just publishes
await self.event_bus.publish_all(aggregate.get_uncommitted_events())

# Subscribers register at startup
event_bus.subscribe(HistoricalDataSyncedEvent, strategy_engine.on_data_synced)
event_bus.subscribe(HistoricalDataSyncedEvent, dashboard.refresh)
```

## 3.3 Singleton Pattern — Managing Expensive Resources

### The Problem with Per-Request Resources

```python
# ❌ BAD: New connection per request
class SyncHandler:
    async def handle(self, request):
        client = AsyncMongoClient(url)  # New connection!
        await client.server_info()      # Slow handshake!
        result = await client["db"]["coll"].find_one(...)
        await client.close()            # Waste!
```

### Singleton Solution

**From `src/infrastructure/persistence/mongodb.py:13-54`:**
```python
class Database:
    _client: AsyncMongoClient | None = None  # Class-level = shared
    _database: AsyncDatabase | None = None

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        logger.info("mongodb.connecting", database=settings.mongodb_database)

        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )

        try:
            await client.server_info()
            cls._client = client
            cls._database = client[settings.mongodb_database]
            logger.info("mongodb.connected", database=settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb.connection_failed", error=str(e))
            await client.close()
            raise

    @classmethod
    def get_collection(cls, name: str):
        return cls.get_database()[name]
```

### Usage Throughout Codebase
```python
# No instantiation, no injection needed
collection = Database.get_collection("ohlcv")
await collection.find_one({...})
```

### Why Not Dependency Injection?

| Approach | Pros | Cons |
|----------|------|------|
| **DI Container** | Testable, flexible | Complex setup, learning curve, DI framework needed |
| **Singleton Class** | Simple, no framework | Harder to mock in tests |

**This project's choice:** Singleton with explicit `connect()`/`disconnect()` lifecycle.

### Testing Singletons (The Monkeypatch Pattern)

```python
@pytest.fixture
async def mock_database(monkeypatch):
    mock_db = AsyncMock()
    monkeypatch.setattr(Database, "_database", mock_db)
    return mock_db

@pytest.mark.asyncio
async def test_sync_handler(mock_database):
    mock_database.get_collection.return_value.find_one.return_value = None
    # Test with mocked database...
```

### ❌ BAD: Global Variable Without Lifecycle
```python
# Connects at import time - no control!
db = AsyncMongoClient(os.getenv("MONGO_URL"))

# Can't disconnect, can't test, can't configure
```

### ❌ WORST: Connection Per Request
```python
async def get_data():
    client = AsyncMongoClient(url)
    try:
        return await client["db"]["coll"].find_one({})
    finally:
        await client.close()
# Slow, wasteful, can exhaust server connections
```

### ✅ GOOD: Singleton with Explicit Lifecycle
```python
class Database:
    _client: AsyncMongoClient | None = None

    @classmethod
    async def connect(cls, settings): ...  # Call once at startup

    @classmethod
    async def disconnect(cls): ...  # Call once at shutdown

    @classmethod
    def get_collection(cls, name): ...  # Use anywhere
```

---

# Part 4: Application Lifecycle — FastAPI Lifespan

## 4.1 The Lifespan Context Manager

**From `src/main.py:88-233`:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    logger.info("application_starting", environment=settings.environment)

    # === STARTUP ===
    mediator = Mediator()
    event_bus = EventBus(max_history=100)
    app.state.mediator = mediator
    app.state.event_bus = event_bus

    try:
        # Connect infrastructure
        await Database.connect(settings)
        await Cache.connect(settings)

        # Initialize components
        tv_provider = TradingViewProvider(settings)
        sync_handler = SyncSymbolHandler(tv_provider, event_bus)

        # Register handlers with mediator
        mediator.register(SyncSymbolCommand, sync_handler)
        # ... more registrations ...

        logger.info("application_started")
        yield  # ← Server runs here, handling requests

    # === SHUTDOWN ===
    finally:
        await strategy_engine.stop()
        if settings.enable_jobs:
            JobScheduler.shutdown(wait=True)
        await Cache.disconnect()
        await Database.disconnect()
        logger.info("application_stopped")
```

### The `yield` Statement Explained

```python
@asynccontextmanager
async def lifespan(app):
    # Everything BEFORE yield = startup
    await Database.connect()

    yield  # Application runs here, serving requests

    # Everything AFTER yield = shutdown
    await Database.disconnect()
```

### C# Equivalent
```csharp
public class Program {
    public static async Task Main(string[] args) {
        var builder = WebApplication.CreateBuilder(args);

        // Startup
        builder.Services.AddSingleton<Database>();
        var app = builder.Build();
        await app.Services.GetRequiredService<Database>().ConnectAsync();

        // Run
        await app.RunAsync();

        // Shutdown (via IHostedService or ApplicationStopping)
        await app.Services.GetRequiredService<Database>().DisconnectAsync();
    }
}
```

### ❌ BAD: No Explicit Lifecycle
```python
# Connect at import
Database.connect()  # Blocks! No async!

app = FastAPI()

# Never disconnects - connection leaks
```

### ❌ WORST: Connect in Every Request
```python
@app.get("/data")
async def get_data():
    await Database.connect()  # Reconnects every request!
    data = await Database.get_collection("x").find_one({})
    await Database.disconnect()  # Disconnects every request!
    return data
```

### ✅ GOOD: Lifespan Context Manager
```python
@asynccontextmanager
async def lifespan(app):
    await Database.connect()     # Once at startup
    yield                        # Serve all requests
    await Database.disconnect()  # Once at shutdown
```

---

# Part 5: Practical Exercises

## Exercise 1: Trace a Request Flow (30 min)

**Goal:** Understand how a request flows through CQRS architecture

**Steps:**
1. Open `src/features/market_data/api/routes.py`
2. Find the POST `/sync` endpoint
3. Trace: Route → Command → Mediator → Handler → Database → EventBus
4. Draw a sequence diagram

**Questions to Answer:**
- Where is the `SyncSymbolCommand` created?
- How does `mediator.send()` find the right handler?
- What events are published after sync completes?
- Who receives those events?

## Exercise 2: Create a Query Handler (1 hour)

**Goal:** Implement CQRS query following project patterns

**Task:** Create `GetSymbolStatsQuery` returning total bars, date range, avg volume

**Files to Create:**
```
src/features/market_data/stats/
├── __init__.py
├── query.py          # GetSymbolStatsQuery dataclass
├── dto.py            # SymbolStats response dataclass
└── handler.py        # GetSymbolStatsHandler
```

**Pattern to Follow:**
```python
# query.py
@dataclass
class GetSymbolStatsQuery:
    symbol: str
    exchange: str

# handler.py
class GetSymbolStatsHandler(Handler[GetSymbolStatsQuery, SymbolStats]):
    async def handle(self, request: GetSymbolStatsQuery) -> SymbolStats:
        collection = Database.get_collection("ohlcv")
        # Aggregate query for stats...
```

## Exercise 3: Add Event Subscriber (45 min)

**Goal:** Understand event-driven decoupling

**Task:** Log when any symbol sync completes

**Steps:**
1. Create handler function in `src/features/market_data/subscribers.py`
2. Subscribe to `HistoricalDataSyncedEvent` in `src/main.py`
3. Log symbol, bars_count, timestamp

**Pattern:**
```python
# subscribers.py
async def on_data_synced(event: HistoricalDataSyncedEvent) -> None:
    logger.info(
        "data_synced_notification",
        symbol=event.symbol,
        bars_count=event.bars_count,
    )

# main.py (in lifespan)
event_bus.subscribe(HistoricalDataSyncedEvent, on_data_synced)
```

## Exercise 4: Write Tests with Mocked Singleton (1 hour)

**Goal:** Learn pytest-asyncio and singleton mocking

**Test GetSymbolStatsHandler:**
```python
import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_database(monkeypatch):
    mock_coll = AsyncMock()
    mock_db = AsyncMock()
    mock_db.__getitem__ = lambda self, name: mock_coll
    monkeypatch.setattr("src.common.database.Database._database", mock_db)
    return mock_coll

@pytest.mark.asyncio
async def test_get_stats_returns_correct_count(mock_database):
    mock_database.count_documents.return_value = 500

    handler = GetSymbolStatsHandler()
    result = await handler.handle(GetSymbolStatsQuery("AAPL", "NASDAQ"))

    assert result.total_bars == 500
```

---

# Part 6: Quick Reference

## Python vs C# Cheat Sheet

| Concept | C# | Python |
|---------|-----|--------|
| Entry point | `static void Main()` | `if __name__ == "__main__":` |
| Async method | `async Task<T> Method()` | `async def method() -> T:` |
| Constructor | `public ClassName()` | `def __init__(self):` |
| Properties | `get; set;` | `@property` |
| Abstract class | `abstract class X` | `class X(ABC):` |
| Interface | `interface IX` | `class IX(ABC):` + abstractmethod |
| Null | `null` | `None` |
| String interp | `$"Hello {name}"` | `f"Hello {name}"` |
| Type check | `obj is Type` | `isinstance(obj, Type)` |
| Cast | `(Type)obj` | No cast needed (duck typing) |
| Generics | `List<T>` | `list[T]` |
| Dictionary | `Dictionary<K,V>` | `dict[K, V]` |
| Tuple | `(int, string)` | `tuple[int, str]` |
| Lambda | `x => x * 2` | `lambda x: x * 2` |
| LINQ Select | `.Select(x => x.Y)` | `[x.y for x in items]` |
| LINQ Where | `.Where(x => x > 0)` | `[x for x in items if x > 0]` |

## Common Commands

```bash
# Virtual environment
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # Linux/Mac

# Run application
uvicorn src.main:app --reload

# Type checking
pyright src/

# Linting
ruff check .
ruff check . --fix              # Auto-fix

# Formatting
ruff format .

# Testing
pytest
pytest -v --tb=short           # Verbose
pytest --cov=src              # Coverage
pytest -x                     # Stop on first failure
pytest --pdb                  # Debug on failure
```

## VS Code Shortcuts

| Action | Shortcut |
|--------|----------|
| Go to definition | F12 |
| Find references | Shift+F12 |
| Rename symbol | F2 |
| Quick fix | Ctrl+. |
| Format document | Shift+Alt+F |
| Open terminal | Ctrl+` |
| Go to file | Ctrl+P |
| Command palette | Ctrl+Shift+P |

---

# Summary: The Python Way vs C# Way

| Aspect | C# Approach | Python Approach (This Project) |
|--------|-------------|-------------------------------|
| **Type Safety** | Compiler enforced | Type hints + Pyright + runtime validation |
| **DI** | Container (Autofac, etc.) | Singleton classes + explicit wiring |
| **Async** | ThreadPool-based, automatic | Single-threaded, explicit `await` |
| **Domain Objects** | Records, classes | Frozen dataclasses |
| **Events** | C# events, MediatR | Custom EventBus |
| **Testing** | xUnit + Moq | pytest + monkeypatch |
| **Linting** | StyleCop, analyzers | Ruff |
| **Package Mgmt** | NuGet | pip + pyproject.toml |

**Key Mental Shifts:**
1. **Trust tooling, not runtime** — Type hints need Pyright, not Python
2. **Explicit is better than implicit** — `self`, `await`, type hints
3. **Protect shared state** — `asyncio.Lock` even in single-threaded
4. **Blocking kills everything** — Use async libraries or thread pool
5. **Convention over enforcement** — `_private` is suggestion, not rule
