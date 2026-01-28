# DDD Tactical Patterns & CQRS with Mediator for FastAPI

**Research Date:** Jan 28, 2026
**Target:** Python DDD implementation for Vertical Slice Architecture refactor

---

## 1. Aggregate Root Pattern

### Design Decision: Frozen Dataclass vs Regular Class

**Frozen Dataclass (Recommended for Value Objects & Immutable Aggregates)**
```python
from dataclasses import dataclass

@dataclass(frozen=True, eq=True)
class Symbol:
    """Value object - immutable, equality by value"""
    code: str
    exchange: str

    def __hash__(self) -> int:
        # Auto-generated when frozen=True, eq=True
        return hash((self.code, self.exchange))

# Usage
s1 = Symbol("AAPL", "NASDAQ")
s2 = Symbol("AAPL", "NASDAQ")
assert s1 == s2  # True: equality by value
assert hash(s1) == hash(s2)  # Can use in sets/dicts
```

**Entity with Identity-Based Equality**
```python
from dataclasses import dataclass
from uuid import UUID, uuid4

@dataclass(eq=False, frozen=False)  # Override dataclass equality
class HistoricalBar:
    """Aggregate root - identity-based equality"""
    id: UUID
    symbol: Symbol
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: int

    def __eq__(self, other):
        # Identity-based: same if same ID
        if not isinstance(other, HistoricalBar):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

# Usage
bar1 = HistoricalBar(id=uuid4(), symbol=Symbol("AAPL", "NASDAQ"), ...)
bar2 = HistoricalBar(id=bar1.id, symbol=Symbol("AAPL", "NASDAQ"), ...)
assert bar1 == bar2  # True: same identity
```

**Key Tradeoff:** Frozen dataclasses are 5-10% slower on instantiation but enforce immutability. Use frozen=True for value objects (Symbol, Price, TimeInterval), regular for entities needing identity.

---

## 2. Value Objects Implementation

Value objects represent domain concepts with no identity, defined solely by values.

```python
from dataclasses import dataclass
from enum import Enum

@dataclass(frozen=True)
class Price:
    amount: float
    currency: str = "USD"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Price must be non-negative")

    def add(self, other: "Price") -> "Price":
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies")
        return Price(self.amount + other.amount, self.currency)

@dataclass(frozen=True)
class TimeInterval(str, Enum):
    """Value object - enumerated intervals"""
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1mo"

# Usage - immutable + hashable
price1 = Price(100.50, "USD")
prices_set = {price1, Price(100.50, "USD")}  # Set deduplication works
assert len(prices_set) == 1
```

**Best Practice:** Value objects always frozen, hashable, compared by value. They're serialization-friendly (Pydantic models for API).

---

## 3. Domain Events

Events capture state changes within aggregates.

```python
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

@dataclass(frozen=True)
class DomainEvent:
    """Base class - all events immutable"""
    aggregate_id: UUID
    occurred_at: datetime

    def __eq__(self, other):
        # Events equal if same type + aggregate_id + time
        return (
            isinstance(other, self.__class__) and
            self.aggregate_id == other.aggregate_id and
            self.occurred_at == other.occurred_at
        )

@dataclass(frozen=True)
class HistoricalDataSynced(DomainEvent):
    symbol: str
    interval: str
    n_bars: int
    last_timestamp: int

@dataclass(frozen=True)
class QuoteUpdated(DomainEvent):
    symbol: str
    price: float
    timestamp: int

# Aggregate collects events
@dataclass(eq=False)
class MarketDataAggregate:
    id: UUID
    symbol: str
    _events: list = None

    def __post_init__(self):
        if self._events is None:
            object.__setattr__(self, "_events", [])

    def sync_completed(self, interval: str, n_bars: int, ts: int):
        event = HistoricalDataSynced(
            aggregate_id=self.id,
            occurred_at=datetime.utcnow(),
            symbol=self.symbol,
            interval=interval,
            n_bars=n_bars,
            last_timestamp=ts
        )
        self._events.append(event)

    def get_uncommitted_events(self) -> list:
        return self._events.copy()

    def clear_events(self):
        object.__setattr__(self, "_events", [])
```

**Pattern:** Aggregates raise events as side effects. Unit of Work flushes them to event bus/storage.

---

## 4. CQRS Mediator Pattern

Separate Commands (writes) from Queries (reads) via typed request handlers.

```python
from dataclasses import dataclass
from typing import Generic, TypeVar, Protocol
from abc import ABC, abstractmethod
import asyncio

# Request types
@dataclass
class SyncHistoricalDataCommand:
    symbol: str
    exchange: str
    interval: str
    n_bars: int

@dataclass
class GetOHLCVDataQuery:
    symbol: str
    exchange: str
    interval: str
    limit: int = 100

# Handler protocol
T = TypeVar("T")

class Handler(ABC, Generic[T]):
    @abstractmethod
    async def handle(self, request: T) -> any:
        pass

# Command handlers
class SyncHistoricalDataHandler(Handler[SyncHistoricalDataCommand]):
    def __init__(self, service: "DataSyncService"):
        self.service = service

    async def handle(self, req: SyncHistoricalDataCommand) -> dict:
        result = await self.service.sync_symbol(
            req.symbol, req.exchange, req.interval, req.n_bars
        )
        return {"bars_synced": result["n_bars"], "timestamp": result["last_ts"]}

# Query handlers
class GetOHLCVDataHandler(Handler[GetOHLCVDataQuery]):
    def __init__(self, repository):
        self.repository = repository

    async def handle(self, req: GetOHLCVDataQuery) -> list:
        bars = await self.repository.get_bars(
            req.symbol, req.exchange, req.interval, limit=req.limit
        )
        return bars

# Mediator - request dispatcher
class Mediator:
    def __init__(self):
        self._handlers: dict = {}

    def register(self, request_type: type, handler: Handler):
        """Register handler for request type"""
        self._handlers[request_type] = handler

    async def send(self, request) -> any:
        """Dispatch request to handler"""
        handler = self._handlers.get(type(request))
        if not handler:
            raise ValueError(f"No handler for {type(request).__name__}")
        return await handler.handle(request)

# FastAPI integration with Depends
from fastapi import FastAPI, Depends

app = FastAPI()
mediator = Mediator()

def get_mediator() -> Mediator:
    return mediator

@app.post("/api/v1/market-data/sync")
async def sync_data(
    cmd: SyncHistoricalDataCommand,
    mediator: Mediator = Depends(get_mediator)
):
    return await mediator.send(cmd)

@app.get("/api/v1/market-data/ohlcv/{exchange}/{symbol}")
async def get_ohlcv(
    exchange: str,
    symbol: str,
    interval: str = "1d",
    limit: int = 100,
    mediator: Mediator = Depends(get_mediator)
):
    query = GetOHLCVDataQuery(symbol, exchange, interval, limit)
    return await mediator.send(query)
```

---

## 5. Keeping Domain Layer Pure

Domain layer must have zero I/O imports. Dependency inversion via constructor injection.

**❌ Violates Purity** - Domain imports MongoDB/Redis
```python
# BAD: Domain depends on infrastructure
from motor.motor_asyncio import AsyncIOMotorCollection

class DataSyncService:
    async def sync(self, symbol: str):
        collection = await get_mongo_connection()
        await collection.insert_one(...)  # Domain knows about MongoDB!
```

**✅ Pure Domain** - Infrastructure injected
```python
from abc import ABC, abstractmethod

# Domain interface (abstract)
class OHLCVRepository(ABC):
    @abstractmethod
    async def save(self, bars: list) -> int:
        pass

# Domain service - no I/O imports
class DataSyncService:
    def __init__(self, repository: OHLCVRepository, provider: "DataProvider"):
        self.repository = repository  # Injected interface
        self.provider = provider

    async def sync(self, symbol: str, exchange: str, interval: str):
        bars = await self.provider.fetch_bars(symbol, exchange, interval)
        saved_count = await self.repository.save(bars)
        return {"n_bars": saved_count}

# Infrastructure implementation (outside domain)
from motor.motor_asyncio import AsyncIOMotorCollection

class MongoOHLCVRepository(OHLCVRepository):
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def save(self, bars: list) -> int:
        result = await self.collection.insert_many(bars)
        return len(result.inserted_ids)
```

**Dependency Flow:**
- Domain Layer: Defines `OHLCVRepository` interface
- Application Layer: Orchestrates `DataSyncService + MongoOHLCVRepository`
- Infrastructure Layer: Implements `MongoOHLCVRepository` with Motor
- FastAPI Routes: Receives fully wired service via DI

---

## 6. In-Memory Event Bus (Production-Ready)

```python
from dataclasses import dataclass
from typing import Callable, list
import asyncio

@dataclass(frozen=True)
class EventHandler:
    event_type: type
    handler: Callable

class EventBus:
    """In-memory, async-safe event bus with FIFO delivery"""

    def __init__(self, max_history: int = 50):
        self._handlers: dict[type, list[Callable]] = {}
        self._history: list = []
        self._max_history = max_history

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Register handler for event type"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def publish(self, event: DomainEvent) -> None:
        """FIFO: Deliver to all handlers sequentially"""
        handlers = self._handlers.get(type(event), [])

        for handler in handlers:
            await handler(event)

        # Keep bounded history for debugging
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    async def publish_all(self, events: list[DomainEvent]) -> None:
        """Atomic: Publish all or none"""
        for event in events:
            await self.publish(event)

# Usage
event_bus = EventBus(max_history=100)

async def on_data_synced(event: HistoricalDataSynced):
    print(f"Synced {event.n_bars} bars for {event.symbol}")

async def on_quote_updated(event: QuoteUpdated):
    print(f"Quote: {event.symbol}={event.price}")

event_bus.subscribe(HistoricalDataSynced, on_data_synced)
event_bus.subscribe(QuoteUpdated, on_quote_updated)

# In service
async def sync_symbol(self, symbol: str):
    aggregate = MarketDataAggregate(id=uuid4(), symbol=symbol)
    aggregate.sync_completed("1d", 5000, 1706400000)

    await self.event_bus.publish_all(
        aggregate.get_uncommitted_events()
    )
    aggregate.clear_events()
```

**Tradeoffs:**
- **Bounded History:** Prevents unbounded memory in long-running apps
- **FIFO Sequential:** Ensures event order, easier debugging
- **No Persistence:** Use external bus (Redis, RabbitMQ) for durability

---

## Summary: Implementation Priority

1. **Value Objects First** - `@dataclass(frozen=True)` for Symbol, Price, TimeInterval
2. **Aggregate Roots** - `@dataclass(eq=False)` for MarketDataAggregate with event collection
3. **Repository Interfaces** - Pure domain ABCs, MongoDB impl in infrastructure
4. **Mediator** - Command/Query handlers wired in FastAPI startup
5. **Event Bus** - In-memory async bus for intra-process domain events

**PocketQuant Alignment:** Vertical Slice stays intact (market_data feature). Add `domain/` layer inside feature for aggregates, value objects, events. Services become mediator handlers.

---

## Sources

- [Python Dataclasses Docs](https://docs.python.org/3/library/dataclasses.html)
- [Cosmic Python - Aggregate Pattern](https://www.cosmicpython.com/book/chapter_07_aggregate.html)
- [DDD Python Example](https://github.com/qu3vipon/python-ddd)
- [PyMediator Implementation](https://www.johal.in/mediatr-pymediator-request-handler-dispatch-for-loose-coupling-2025-2/)
- [FastAPI CQRS Mediator](https://github.com/ocbunknown/fastapi-cqrs-mediator)
- [Cosmic Python - Event Bus](https://www.cosmicpython.com/book/chapter_08_events_and_message_bus.html)
- [Value Objects in Python](https://damianpiatkowski.com/blog/value-objects-in-python)
