# Phase 1: Read & Understand Patterns (Week 1)

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Reference:** [Brainstorm Guide](../reports/brainstorm-260201-1223-python-learning-guide.md)
- **Duration:** ~4 hours total

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Foundation |
| Status | pending |
| Goal | Understand Python patterns through code reading |

**Philosophy:** No code changes this week. Learn by tracing, not typing.

---

## Exercise 1.1: Trace CQRS Request Flow

**Objective:** Understand how requests flow through the CQRS mediator pattern

**Files to Read:**
```
src/main.py                                    # Lines 119-123: Handler registration
src/common/mediator/mediator.py                # Full file (37 lines)
src/common/mediator/handler.py                 # Full file (16 lines)
src/features/market_data/sync/handler.py       # SyncSymbolHandler implementation
src/features/market_data/sync/command.py       # Command dataclass
```

**Task:**
1. Open `src/main.py`, find where `SyncSymbolHandler` is registered
2. Trace: How does `mediator.send(command)` find the right handler?
3. Read `SyncSymbolHandler.handle()` - identify the 5-step pattern:
   - Fetch from provider
   - Execute domain logic
   - Persist to database
   - Publish events
   - Return DTO

**Pattern Explanation (WHY):**
CQRS separates read (Query) from write (Command) operations. Benefits:
- Single Responsibility: Each handler does ONE thing
- Testability: Test handlers in isolation
- Scalability: Scale reads/writes independently

**C# Comparison:**
```csharp
// MediatR equivalent
public class SyncSymbolHandler : IRequestHandler<SyncSymbolCommand, SyncResult> {
    public async Task<SyncResult> Handle(SyncSymbolCommand request, CancellationToken ct) { ... }
}
services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(...));
var result = await _mediator.Send(new SyncSymbolCommand { Symbol = "AAPL" });
```

**❌ BAD Alternative:**
```python
# Direct service call - tight coupling
@router.post("/sync")
async def sync(request):
    service = MarketDataService()  # New instance each time
    return await service.sync(request.symbol)
```

**❌ WORST Alternative:**
```python
# Logic in route - unmaintainable
@router.post("/sync")
async def sync(request):
    records = await provider.fetch(...)
    await database.insert_many(...)
    await cache.delete(...)
    # 200 lines of business logic in route
```

**Success Criteria:**
- [ ] Can explain how `mediator.send()` routes to correct handler
- [ ] Can identify the 5-step handler pattern
- [ ] Drew sequence diagram of request flow

---

## Exercise 1.2: Understand Singleton Lifecycle

**Objective:** Learn how expensive resources (DB, Cache) are managed

**Files to Read:**
```
src/infrastructure/persistence/mongodb.py      # Database singleton
src/common/cache/__init__.py                   # Cache re-export
src/main.py                                    # Lines 88-233: lifespan context manager
```

**Task:**
1. Read `Database` class - note class-level variables `_client`, `_database`
2. Understand `@classmethod` - why not instance methods?
3. Trace lifecycle in `lifespan()`:
   - Startup: `await Database.connect(settings)`
   - Shutdown: `await Database.disconnect()`
4. How is `yield` used in async context manager?

**Pattern Explanation (WHY):**
Database connections are expensive. Creating per-request wastes resources and can exhaust connection pools. Singleton ensures:
- One connection pool shared across all requests
- Explicit lifecycle (connect at startup, disconnect at shutdown)
- Simple usage: `Database.get_collection("ohlcv")` anywhere

**C# Comparison:**
```csharp
// C# uses DI container with singleton lifetime
services.AddSingleton<IMongoClient>(sp => new MongoClient(connectionString));
services.AddSingleton<IDatabase>(sp => sp.GetRequiredService<IMongoClient>().GetDatabase("mydb"));
```

**❌ BAD Alternative:**
```python
# Global without lifecycle - connects at import!
db = AsyncMongoClient(os.getenv("MONGO_URL"))  # No async! Blocks!
```

**❌ WORST Alternative:**
```python
# Connection per request - exhausts resources
async def get_data():
    client = AsyncMongoClient(url)  # New connection!
    try:
        return await client["db"]["coll"].find_one({})
    finally:
        await client.close()  # Wasted setup/teardown
```

**Success Criteria:**
- [ ] Can explain why `@classmethod` instead of instance methods
- [ ] Can trace startup/shutdown lifecycle in `lifespan()`
- [ ] Understands `yield` in async context manager

---

## Exercise 1.3: Map Domain Events to C# INotification

**Objective:** Understand event-driven decoupling pattern

**Files to Read:**
```
src/domain/shared/domain_event.py              # Base event class
src/domain/order/order_event.py                # Concrete events
src/common/messaging/event_bus.py              # EventBus implementation
src/main.py                                    # Event subscriptions
```

**Task:**
1. Read `DomainEvent` base class - note `frozen=True` (immutable)
2. Read `OrderFilledEvent` - what fields does it carry?
3. Read `EventBus.publish()` - how does it find subscribers?
4. In `main.py`, find where events are subscribed

**Pattern Explanation (WHY):**
Events decouple features. When order fills:
- OrderManager doesn't know about PositionTracker
- OrderManager publishes `OrderFilledEvent`
- PositionTracker subscribes and updates positions
- Adding new subscriber doesn't change OrderManager

**C# Comparison:**
```csharp
// MediatR INotification
public class OrderFilledEvent : INotification {
    public string OrderId { get; init; }
    public decimal FillPrice { get; init; }
}

// Handler
public class PositionHandler : INotificationHandler<OrderFilledEvent> {
    public Task Handle(OrderFilledEvent notification, CancellationToken ct) { ... }
}

// Publisher
await _mediator.Publish(new OrderFilledEvent { ... });
```

**❌ BAD Alternative:**
```python
# Direct coupling
class OrderManager:
    def __init__(self, position_tracker, dashboard, notifications):
        self._position = position_tracker  # Knows everyone
        self._dashboard = dashboard
        self._notifications = notifications

    async def on_fill(self, order):
        await self._position.update(...)  # Direct call
        await self._dashboard.refresh(...) # Direct call
```

**Success Criteria:**
- [ ] Can explain why events are `frozen=True`
- [ ] Can trace event from publish to subscriber
- [ ] Understands decoupling benefit

---

## Exercise 1.4: Compare Async Models

**Objective:** Internalize Python asyncio vs C# ThreadPool difference

**Files to Read:**
```
src/features/market_data/managers/bar_manager.py   # Lines 154, 159-161: asyncio.Lock
src/common/messaging/event_bus.py                  # Lines 41-44: coroutine detection
```

**Task:**
1. Find `asyncio.Lock()` in BarManager - why needed in single-threaded code?
2. In EventBus.publish(), find `inspect.iscoroutine()` - why check this?
3. Mental exercise: What happens if you use `threading.Lock` instead?

**Pattern Explanation (WHY):**

**Python asyncio (Single-Threaded Cooperative):**
```
Event Loop (1 thread)
├── Coroutine A: await db.find() → suspends
├── Coroutine B: runs while A waits
├── Coroutine A: resumes when I/O completes
└── No parallelism, only concurrency
```

**C# async (ThreadPool Multi-Threaded):**
```
ThreadPool (N threads)
├── Thread 1: Task A runs
├── Thread 2: Task B runs in parallel
└── True parallelism on multi-core
```

**Why Lock in Single-Threaded?**
Even single-threaded, race conditions occur at `await` points:
```
Tick1 → reads bar → [await] → Tick2 reads same bar → Tick2 writes → Tick1 writes (overwrites!)
```
Lock ensures atomic read-modify-write.

**❌ WORST Alternative:**
```python
import threading
self._lock = threading.Lock()  # WRONG - blocks event loop!

async def add_tick(self):
    with self._lock:  # Entire event loop frozen!
        await self._process()  # Can't even await inside!
```

**Success Criteria:**
- [ ] Can explain why asyncio.Lock needed even in single thread
- [ ] Understands suspension points create race conditions
- [ ] Knows threading.Lock blocks event loop

---

## Week 1 Checklist

- [ ] Exercise 1.1: CQRS request flow traced
- [ ] Exercise 1.2: Singleton lifecycle understood
- [ ] Exercise 1.3: Domain events mapped to C#
- [ ] Exercise 1.4: Asyncio model internalized

## Next Phase

→ [Phase 2: Small Modifications](./phase-02-week2-small-modifications.md)
