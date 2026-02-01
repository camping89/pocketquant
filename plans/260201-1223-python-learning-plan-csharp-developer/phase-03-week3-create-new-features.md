# Phase 3: Create New Features (Week 3)

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** [Phase 2](./phase-02-week2-small-modifications.md)
- **Duration:** ~6 hours total

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Application |
| Status | pending |
| Goal | Create new code following project patterns |

**Philosophy:** Build complete features from scratch using learned patterns.

---

## Exercise 3.1: Create GetSymbolStatsQuery + Handler

**Objective:** Implement complete CQRS query following project patterns

**Files to Create:**
```
src/features/market_data/stats/__init__.py
src/features/market_data/stats/query.py
src/features/market_data/stats/dto.py
src/features/market_data/stats/handler.py
```

**Files to Modify:**
```
src/main.py                                    # Register handler
src/features/market_data/api/routes.py         # Add endpoint
```

**Task:**

1. Create `query.py`:
   ```python
   from dataclasses import dataclass


   @dataclass
   class GetSymbolStatsQuery:
       """Query to get statistics for a symbol."""

       symbol: str
       exchange: str

       def __post_init__(self) -> None:
           if not self.symbol:
               raise ValueError("Symbol is required")
           if not self.exchange:
               raise ValueError("Exchange is required")
           object.__setattr__(self, "symbol", self.symbol.upper())
           object.__setattr__(self, "exchange", self.exchange.upper())
   ```

2. Create `dto.py`:
   ```python
   from dataclasses import dataclass
   from datetime import datetime


   @dataclass
   class SymbolStats:
       """Statistics for a symbol."""

       symbol: str
       exchange: str
       total_bars: int
       first_bar_at: datetime | None
       last_bar_at: datetime | None
       avg_volume: float | None
       intervals_available: list[str]
   ```

3. Create `handler.py`:
   ```python
   from src.common.database import Database
   from src.common.constants import COLLECTION_OHLCV
   from src.common.logging import get_logger
   from src.common.mediator import Handler
   from src.features.market_data.stats.dto import SymbolStats
   from src.features.market_data.stats.query import GetSymbolStatsQuery

   logger = get_logger(__name__)


   class GetSymbolStatsHandler(Handler[GetSymbolStatsQuery, SymbolStats]):
       """Handle GetSymbolStatsQuery."""

       async def handle(self, request: GetSymbolStatsQuery) -> SymbolStats:
           logger.info(
               "stats.query.started",
               symbol=request.symbol,
               exchange=request.exchange,
           )

           collection = Database.get_collection(COLLECTION_OHLCV)

           # Aggregation pipeline for stats
           pipeline = [
               {
                   "$match": {
                       "symbol": request.symbol,
                       "exchange": request.exchange,
                   }
               },
               {
                   "$group": {
                       "_id": None,
                       "total_bars": {"$sum": 1},
                       "first_bar_at": {"$min": "$datetime"},
                       "last_bar_at": {"$max": "$datetime"},
                       "avg_volume": {"$avg": "$volume"},
                       "intervals": {"$addToSet": "$interval"},
                   }
               },
           ]

           result = await collection.aggregate(pipeline).to_list(1)

           if not result:
               return SymbolStats(
                   symbol=request.symbol,
                   exchange=request.exchange,
                   total_bars=0,
                   first_bar_at=None,
                   last_bar_at=None,
                   avg_volume=None,
                   intervals_available=[],
               )

           stats = result[0]
           return SymbolStats(
               symbol=request.symbol,
               exchange=request.exchange,
               total_bars=stats["total_bars"],
               first_bar_at=stats["first_bar_at"],
               last_bar_at=stats["last_bar_at"],
               avg_volume=stats["avg_volume"],
               intervals_available=sorted(stats["intervals"]),
           )
   ```

4. Create `__init__.py`:
   ```python
   from src.features.market_data.stats.dto import SymbolStats
   from src.features.market_data.stats.handler import GetSymbolStatsHandler
   from src.features.market_data.stats.query import GetSymbolStatsQuery

   __all__ = ["GetSymbolStatsQuery", "GetSymbolStatsHandler", "SymbolStats"]
   ```

5. Register in `main.py` (after other market_data handlers):
   ```python
   from src.features.market_data.stats import GetSymbolStatsQuery, GetSymbolStatsHandler

   mediator.register(GetSymbolStatsQuery, GetSymbolStatsHandler())
   ```

6. Add endpoint in `routes.py`:
   ```python
   @router.get("/stats/{exchange}/{symbol}")
   async def get_symbol_stats(
       exchange: str,
       symbol: str,
       mediator: Mediator = Depends(get_mediator),
   ):
       query = GetSymbolStatsQuery(symbol=symbol, exchange=exchange)
       return await mediator.send(query)
   ```

**Pattern Explanation (WHY):**
Complete CQRS query implementation:
- Query: Immutable request with validation
- DTO: Response contract with clear types
- Handler: Single responsibility, uses Database singleton
- Registration: Wired through Mediator

**C# Comparison:**
```csharp
public record GetSymbolStatsQuery(string Symbol, string Exchange) : IRequest<SymbolStats>;

public class GetSymbolStatsHandler : IRequestHandler<GetSymbolStatsQuery, SymbolStats> {
    public async Task<SymbolStats> Handle(GetSymbolStatsQuery request, CancellationToken ct) {
        var pipeline = new BsonDocument[] { /* aggregation */ };
        var result = await _collection.Aggregate<BsonDocument>(pipeline).FirstOrDefaultAsync(ct);
        return new SymbolStats { ... };
    }
}
```

**Success Criteria:**
- [ ] All 4 files created with proper types
- [ ] Handler registered in main.py
- [ ] Endpoint added to routes.py
- [ ] `GET /api/v1/market-data/stats/NASDAQ/AAPL` returns stats
- [ ] `pyright src/features/market_data/stats/` passes

---

## Exercise 3.2: Create New Domain Event + Subscriber

**Objective:** Implement complete event-driven feature

**Files to Create:**
```
src/domain/market_data/stats_event.py
```

**Files to Modify:**
```
src/features/market_data/stats/handler.py      # Publish event
src/features/market_data/subscribers.py        # Subscribe to event
src/main.py                                    # Register subscription
```

**Task:**

1. Create `stats_event.py`:
   ```python
   from dataclasses import dataclass
   from datetime import datetime

   from src.domain.shared.domain_event import DomainEvent


   @dataclass(frozen=True)
   class SymbolStatsQueriedEvent(DomainEvent):
       """Event raised when symbol stats are queried."""

       symbol: str
       exchange: str
       total_bars: int
       queried_at: datetime
   ```

2. Modify handler to publish event:
   ```python
   from datetime import UTC, datetime
   from src.common.messaging import EventBus
   from src.domain.market_data.stats_event import SymbolStatsQueriedEvent


   class GetSymbolStatsHandler(Handler[GetSymbolStatsQuery, SymbolStats]):
       def __init__(self, event_bus: EventBus) -> None:
           self._event_bus = event_bus

       async def handle(self, request: GetSymbolStatsQuery) -> SymbolStats:
           # ... existing code ...

           # Publish event
           event = SymbolStatsQueriedEvent(
               symbol=request.symbol,
               exchange=request.exchange,
               total_bars=stats.total_bars,
               queried_at=datetime.now(UTC),
           )
           await self._event_bus.publish(event)

           return stats
   ```

3. Add subscriber in `subscribers.py`:
   ```python
   from src.domain.market_data.stats_event import SymbolStatsQueriedEvent


   async def on_symbol_stats_queried(event: SymbolStatsQueriedEvent) -> None:
       """Log when symbol stats are queried (for analytics)."""
       logger.info(
           "subscriber.stats_queried",
           symbol=event.symbol,
           exchange=event.exchange,
           total_bars=event.total_bars,
       )
   ```

4. Update registration in `main.py`:
   ```python
   from src.domain.market_data.stats_event import SymbolStatsQueriedEvent
   from src.features.market_data.subscribers import on_symbol_stats_queried

   # Update handler registration to pass event_bus
   mediator.register(GetSymbolStatsQuery, GetSymbolStatsHandler(event_bus))

   # Subscribe
   event_bus.subscribe(SymbolStatsQueriedEvent, on_symbol_stats_queried)
   ```

**Pattern Explanation (WHY):**
Events enable analytics without polluting business logic:
- Handler focuses on query execution
- Analytics subscriber tracks usage patterns
- Easy to add more subscribers (alerts, dashboards)

**Success Criteria:**
- [ ] Event class created with proper inheritance
- [ ] Handler publishes event after query
- [ ] Subscriber logs query analytics
- [ ] Query endpoint triggers subscriber log

---

## Exercise 3.3: Implement asyncio.Lock for Shared State

**Objective:** Learn thread-safe async state management

**Files to Create:**
```
src/features/market_data/stats/cache.py
```

**Task:**

Create an in-memory cache for stats with proper locking:

```python
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from src.common.logging import get_logger

logger = get_logger(__name__)


class StatsCache:
    """In-memory cache for symbol stats with TTL."""

    def __init__(self, ttl_seconds: int = 60) -> None:
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _make_key(self, symbol: str, exchange: str) -> str:
        return f"{exchange}:{symbol}".upper()

    async def get(self, symbol: str, exchange: str) -> Any | None:
        """Get cached stats if not expired."""
        key = self._make_key(symbol, exchange)

        async with self._lock:
            if key not in self._cache:
                return None

            value, cached_at = self._cache[key]
            if datetime.now(UTC) - cached_at > self._ttl:
                del self._cache[key]
                logger.debug("stats_cache.expired", key=key)
                return None

            logger.debug("stats_cache.hit", key=key)
            return value

    async def set(self, symbol: str, exchange: str, value: Any) -> None:
        """Cache stats with current timestamp."""
        key = self._make_key(symbol, exchange)

        async with self._lock:
            self._cache[key] = (value, datetime.now(UTC))
            logger.debug("stats_cache.set", key=key)

    async def invalidate(self, symbol: str, exchange: str) -> None:
        """Remove cached stats for symbol."""
        key = self._make_key(symbol, exchange)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug("stats_cache.invalidated", key=key)
```

**Pattern Explanation (WHY):**
Lock protects dict operations across await points:
```
Without lock:
  get() reads _cache → await → set() modifies _cache → get() reads stale

With lock:
  get() acquires → reads → releases → set() acquires → modifies → releases
```

**❌ BAD Alternative:**
```python
# No lock - race condition
async def get(self, key):
    if key in self._cache:  # Check
        # Another coroutine could delete here!
        return self._cache[key]  # Use - might KeyError!
```

**❌ WORST Alternative:**
```python
import threading
self._lock = threading.Lock()  # Blocks event loop!

def get(self, key):  # Not async - can't await inside
    with self._lock:
        return self._cache.get(key)
```

**Success Criteria:**
- [ ] StatsCache created with asyncio.Lock
- [ ] TTL expiration works correctly
- [ ] Can integrate with handler (optional)
- [ ] `pyright src/features/market_data/stats/cache.py` passes

---

## Exercise 3.4: Wire Complete Feature End-to-End

**Objective:** Integration of all components

**Task:**

Update handler to use cache:

```python
class GetSymbolStatsHandler(Handler[GetSymbolStatsQuery, SymbolStats]):
    def __init__(self, event_bus: EventBus, cache: StatsCache) -> None:
        self._event_bus = event_bus
        self._cache = cache

    async def handle(self, request: GetSymbolStatsQuery) -> SymbolStats:
        # Check cache first
        cached = await self._cache.get(request.symbol, request.exchange)
        if cached:
            logger.info("stats.cache_hit", symbol=request.symbol)
            return cached

        # ... existing query logic ...

        # Cache result
        await self._cache.set(request.symbol, request.exchange, stats)

        # Publish event
        await self._event_bus.publish(event)

        return stats
```

Update main.py:
```python
from src.features.market_data.stats.cache import StatsCache

# Create shared cache instance
stats_cache = StatsCache(ttl_seconds=60)

# Pass to handler
mediator.register(
    GetSymbolStatsQuery,
    GetSymbolStatsHandler(event_bus, stats_cache)
)
```

**Success Criteria:**
- [ ] First query hits database, subsequent queries hit cache
- [ ] Cache expires after TTL
- [ ] Events still published on cache miss
- [ ] Full integration test passes

---

## Week 3 Checklist

- [ ] Exercise 3.1: Query + Handler created
- [ ] Exercise 3.2: Domain event + subscriber
- [ ] Exercise 3.3: Async cache with lock
- [ ] Exercise 3.4: End-to-end integration
- [ ] All files pass `pyright` and `ruff check`
- [ ] Manual testing via API endpoints

## Verification Commands

```bash
# Type check new feature
pyright src/features/market_data/stats/

# Lint check
ruff check src/features/market_data/stats/

# Run app
uvicorn src.main:app --reload

# Test endpoint
curl http://localhost:8000/api/v1/market-data/stats/NASDAQ/AAPL

# Check logs for cache hits and events
```

## Next Phase

→ [Phase 4: Testing Mastery](./phase-04-week4-testing-mastery.md)
