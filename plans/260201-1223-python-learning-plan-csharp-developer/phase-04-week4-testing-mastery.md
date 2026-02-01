# Phase 4: Testing Mastery (Week 4)

## Context
- **Parent Plan:** [plan.md](./plan.md)
- **Depends On:** [Phase 3](./phase-03-week3-create-new-features.md)
- **Duration:** ~5 hours total

## Overview

| Field | Value |
|-------|-------|
| Priority | P1 - Quality |
| Status | pending |
| Goal | Master pytest, async testing, and singleton mocking |

**Philosophy:** Tests prove understanding. If you can test it, you understand it.

---

## Exercise 4.1: Unit Test Handler with Mocked Database

**Objective:** Learn monkeypatch for singleton mocking

**Files to Create:**
```
tests/unit/features/market_data/test_stats_handler.py
```

**Reference Files:**
```
tests/unit/common/test_mediator.py             # Existing test patterns
tests/conftest.py                              # Shared fixtures
```

**Task:**

```python
import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

from src.common.messaging import EventBus
from src.features.market_data.stats.query import GetSymbolStatsQuery
from src.features.market_data.stats.handler import GetSymbolStatsHandler
from src.features.market_data.stats.cache import StatsCache


@pytest.fixture
def mock_collection():
    """Create mock MongoDB collection."""
    collection = AsyncMock()
    return collection


@pytest.fixture
def mock_database(monkeypatch, mock_collection):
    """Patch Database singleton to return mock collection."""
    mock_db = MagicMock()
    mock_db.get_collection.return_value = mock_collection
    monkeypatch.setattr(
        "src.features.market_data.stats.handler.Database",
        mock_db
    )
    return mock_db


@pytest.fixture
def event_bus():
    """Create real EventBus for testing."""
    return EventBus()


@pytest.fixture
def stats_cache():
    """Create real StatsCache for testing."""
    return StatsCache(ttl_seconds=60)


class TestGetSymbolStatsHandler:
    """Tests for GetSymbolStatsHandler."""

    @pytest.mark.asyncio
    async def test_returns_stats_when_data_exists(
        self,
        mock_database,
        mock_collection,
        event_bus,
        stats_cache,
    ):
        # Arrange
        mock_aggregate = AsyncMock()
        mock_aggregate.to_list.return_value = [
            {
                "total_bars": 500,
                "first_bar_at": datetime(2024, 1, 1, tzinfo=UTC),
                "last_bar_at": datetime(2024, 12, 31, tzinfo=UTC),
                "avg_volume": 1000000.0,
                "intervals": ["1d", "1h"],
            }
        ]
        mock_collection.aggregate.return_value = mock_aggregate

        handler = GetSymbolStatsHandler(event_bus, stats_cache)
        query = GetSymbolStatsQuery(symbol="AAPL", exchange="NASDAQ")

        # Act
        result = await handler.handle(query)

        # Assert
        assert result.symbol == "AAPL"
        assert result.exchange == "NASDAQ"
        assert result.total_bars == 500
        assert result.avg_volume == 1000000.0
        assert "1d" in result.intervals_available

    @pytest.mark.asyncio
    async def test_returns_empty_stats_when_no_data(
        self,
        mock_database,
        mock_collection,
        event_bus,
        stats_cache,
    ):
        # Arrange
        mock_aggregate = AsyncMock()
        mock_aggregate.to_list.return_value = []  # No data
        mock_collection.aggregate.return_value = mock_aggregate

        handler = GetSymbolStatsHandler(event_bus, stats_cache)
        query = GetSymbolStatsQuery(symbol="UNKNOWN", exchange="NYSE")

        # Act
        result = await handler.handle(query)

        # Assert
        assert result.total_bars == 0
        assert result.first_bar_at is None
        assert result.intervals_available == []

    @pytest.mark.asyncio
    async def test_publishes_event_on_query(
        self,
        mock_database,
        mock_collection,
        event_bus,
        stats_cache,
    ):
        # Arrange
        mock_aggregate = AsyncMock()
        mock_aggregate.to_list.return_value = [{"total_bars": 100, "first_bar_at": None, "last_bar_at": None, "avg_volume": None, "intervals": []}]
        mock_collection.aggregate.return_value = mock_aggregate

        events_received = []
        event_bus.subscribe(
            type(None),  # Will be replaced with actual event type
            lambda e: events_received.append(e)
        )

        handler = GetSymbolStatsHandler(event_bus, stats_cache)
        query = GetSymbolStatsQuery(symbol="AAPL", exchange="NASDAQ")

        # Act
        await handler.handle(query)

        # Assert
        assert len(event_bus.get_history()) == 1
        event = event_bus.get_history()[0]
        assert event.symbol == "AAPL"
        assert event.total_bars == 100
```

**Pattern Explanation (WHY):**
- `monkeypatch.setattr()` replaces module-level references
- Mock the import path where it's USED, not where it's DEFINED
- `AsyncMock` for async methods, `MagicMock` for sync
- Real EventBus to verify event publishing

**C# Comparison:**
```csharp
// xUnit + Moq
public class GetSymbolStatsHandlerTests {
    private readonly Mock<IMongoCollection<BsonDocument>> _mockCollection;
    private readonly Mock<IEventBus> _mockEventBus;

    [Fact]
    public async Task Handle_ReturnsStats_WhenDataExists() {
        _mockCollection
            .Setup(c => c.AggregateAsync(It.IsAny<PipelineDefinition>(), ...))
            .ReturnsAsync(new List<BsonDocument> { ... });

        var handler = new GetSymbolStatsHandler(_mockCollection.Object, _mockEventBus.Object);
        var result = await handler.Handle(new GetSymbolStatsQuery("AAPL", "NASDAQ"), CancellationToken.None);

        Assert.Equal(500, result.TotalBars);
    }
}
```

**❌ BAD Alternative:**
```python
# Testing with real database - slow, flaky
@pytest.mark.asyncio
async def test_handler():
    await Database.connect(settings)  # Real connection!
    handler = GetSymbolStatsHandler(...)
    result = await handler.handle(query)  # Hits real DB!
```

**❌ WORST Alternative:**
```python
# No tests at all
# "It works on my machine" - famous last words
```

**Success Criteria:**
- [ ] Test file created with proper structure
- [ ] Database singleton properly mocked
- [ ] Tests pass: `pytest tests/unit/features/market_data/test_stats_handler.py -v`
- [ ] Coverage for happy path and empty data case

---

## Exercise 4.2: Test Async Code with pytest-asyncio

**Objective:** Master async test patterns

**Files to Create:**
```
tests/unit/features/market_data/test_stats_cache.py
```

**Task:**

```python
import pytest
import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.features.market_data.stats.cache import StatsCache


class TestStatsCache:
    """Tests for StatsCache async operations."""

    @pytest.mark.asyncio
    async def test_get_returns_none_when_empty(self):
        cache = StatsCache()

        result = await cache.get("AAPL", "NASDAQ")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_returns_value(self):
        cache = StatsCache()
        data = {"total_bars": 100}

        await cache.set("AAPL", "NASDAQ", data)
        result = await cache.get("AAPL", "NASDAQ")

        assert result == data

    @pytest.mark.asyncio
    async def test_get_returns_none_after_ttl_expires(self):
        cache = StatsCache(ttl_seconds=1)  # 1 second TTL
        data = {"total_bars": 100}

        await cache.set("AAPL", "NASDAQ", data)

        # Fast-forward time
        await asyncio.sleep(1.1)

        result = await cache.get("AAPL", "NASDAQ")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_removes_cached_value(self):
        cache = StatsCache()
        data = {"total_bars": 100}

        await cache.set("AAPL", "NASDAQ", data)
        await cache.invalidate("AAPL", "NASDAQ")
        result = await cache.get("AAPL", "NASDAQ")

        assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_access_is_thread_safe(self):
        """Verify lock prevents race conditions."""
        cache = StatsCache()
        results = []

        async def writer(i: int):
            await cache.set("AAPL", "NASDAQ", {"value": i})
            await asyncio.sleep(0.01)  # Yield to other coroutines

        async def reader():
            for _ in range(10):
                result = await cache.get("AAPL", "NASDAQ")
                if result:
                    results.append(result)
                await asyncio.sleep(0.005)

        # Run concurrent writers and readers
        await asyncio.gather(
            writer(1),
            writer(2),
            writer(3),
            reader(),
            reader(),
        )

        # All results should be valid (no KeyError, no corruption)
        assert all(isinstance(r, dict) for r in results)

    @pytest.mark.asyncio
    async def test_keys_are_case_insensitive(self):
        cache = StatsCache()
        data = {"total_bars": 100}

        await cache.set("aapl", "nasdaq", data)
        result = await cache.get("AAPL", "NASDAQ")

        assert result == data
```

**Pattern Explanation (WHY):**
- `@pytest.mark.asyncio` enables async test functions
- Test concurrent access to verify lock correctness
- Test edge cases (TTL expiry, case sensitivity)
- Use `asyncio.gather()` to simulate concurrent access

**Success Criteria:**
- [ ] All cache tests pass
- [ ] Concurrent access test verifies thread safety
- [ ] TTL expiration tested
- [ ] `pytest tests/unit/features/market_data/test_stats_cache.py -v`

---

## Exercise 4.3: Test Event Publishing and Subscription

**Objective:** Verify event-driven behavior

**Files to Create:**
```
tests/unit/features/market_data/test_stats_events.py
```

**Task:**

```python
import pytest
from datetime import UTC, datetime

from src.common.messaging import EventBus
from src.domain.market_data.stats_event import SymbolStatsQueriedEvent


class TestSymbolStatsQueriedEvent:
    """Tests for SymbolStatsQueriedEvent."""

    def test_event_is_immutable(self):
        event = SymbolStatsQueriedEvent(
            symbol="AAPL",
            exchange="NASDAQ",
            total_bars=100,
            queried_at=datetime.now(UTC),
        )

        with pytest.raises(AttributeError):
            event.symbol = "GOOGL"  # Should fail - frozen

    def test_event_has_unique_id(self):
        event1 = SymbolStatsQueriedEvent(
            symbol="AAPL",
            exchange="NASDAQ",
            total_bars=100,
            queried_at=datetime.now(UTC),
        )
        event2 = SymbolStatsQueriedEvent(
            symbol="AAPL",
            exchange="NASDAQ",
            total_bars=100,
            queried_at=datetime.now(UTC),
        )

        assert event1.event_id != event2.event_id


class TestEventBusWithStatsEvent:
    """Tests for EventBus with SymbolStatsQueriedEvent."""

    @pytest.mark.asyncio
    async def test_subscriber_receives_event(self):
        event_bus = EventBus()
        received_events = []

        async def handler(event: SymbolStatsQueriedEvent):
            received_events.append(event)

        event_bus.subscribe(SymbolStatsQueriedEvent, handler)

        event = SymbolStatsQueriedEvent(
            symbol="AAPL",
            exchange="NASDAQ",
            total_bars=100,
            queried_at=datetime.now(UTC),
        )
        await event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive_event(self):
        event_bus = EventBus()
        subscriber1_events = []
        subscriber2_events = []

        event_bus.subscribe(
            SymbolStatsQueriedEvent,
            lambda e: subscriber1_events.append(e)
        )
        event_bus.subscribe(
            SymbolStatsQueriedEvent,
            lambda e: subscriber2_events.append(e)
        )

        event = SymbolStatsQueriedEvent(
            symbol="AAPL",
            exchange="NASDAQ",
            total_bars=100,
            queried_at=datetime.now(UTC),
        )
        await event_bus.publish(event)

        assert len(subscriber1_events) == 1
        assert len(subscriber2_events) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving_events(self):
        event_bus = EventBus()
        received_events = []

        def handler(event):
            received_events.append(event)

        event_bus.subscribe(SymbolStatsQueriedEvent, handler)

        # Publish first event
        event1 = SymbolStatsQueriedEvent(
            symbol="AAPL", exchange="NASDAQ", total_bars=100,
            queried_at=datetime.now(UTC),
        )
        await event_bus.publish(event1)

        # Unsubscribe
        event_bus.unsubscribe(SymbolStatsQueriedEvent, handler)

        # Publish second event
        event2 = SymbolStatsQueriedEvent(
            symbol="GOOGL", exchange="NASDAQ", total_bars=200,
            queried_at=datetime.now(UTC),
        )
        await event_bus.publish(event2)

        # Should only have first event
        assert len(received_events) == 1
        assert received_events[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_event_history_is_bounded(self):
        event_bus = EventBus(max_history=3)

        for i in range(5):
            event = SymbolStatsQueriedEvent(
                symbol=f"SYM{i}",
                exchange="NYSE",
                total_bars=i * 100,
                queried_at=datetime.now(UTC),
            )
            await event_bus.publish(event)

        history = event_bus.get_history()
        assert len(history) == 3
        # Should have last 3 events
        assert history[0].symbol == "SYM2"
        assert history[2].symbol == "SYM4"
```

**Pattern Explanation (WHY):**
- Test event immutability (frozen dataclass)
- Test pub/sub contract
- Test unsubscribe to prevent memory leaks
- Test bounded history to verify memory safety

**Success Criteria:**
- [ ] Event immutability verified
- [ ] Subscribe/publish/unsubscribe flow tested
- [ ] History bounds tested
- [ ] All tests pass

---

## Exercise 4.4: Integration Test (Optional Advanced)

**Objective:** Test full feature with real components

**Files to Create:**
```
tests/integration/market_data/test_stats_integration.py
```

**Task:**

```python
import pytest
from datetime import UTC, datetime

from src.common.messaging import EventBus
from src.features.market_data.stats.query import GetSymbolStatsQuery
from src.features.market_data.stats.handler import GetSymbolStatsHandler
from src.features.market_data.stats.cache import StatsCache
from src.domain.market_data.stats_event import SymbolStatsQueriedEvent


class TestStatsFeatureIntegration:
    """Integration tests for stats feature (without real DB)."""

    @pytest.fixture
    def event_bus(self):
        return EventBus()

    @pytest.fixture
    def cache(self):
        return StatsCache(ttl_seconds=60)

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_publish_event(
        self,
        event_bus,
        cache,
        monkeypatch,
    ):
        """Verify cached responses don't trigger events."""
        # Setup mock database
        from unittest.mock import AsyncMock, MagicMock

        mock_collection = AsyncMock()
        mock_aggregate = AsyncMock()
        mock_aggregate.to_list.return_value = [
            {"total_bars": 100, "first_bar_at": None, "last_bar_at": None,
             "avg_volume": None, "intervals": ["1d"]}
        ]
        mock_collection.aggregate.return_value = mock_aggregate

        mock_db = MagicMock()
        mock_db.get_collection.return_value = mock_collection
        monkeypatch.setattr(
            "src.features.market_data.stats.handler.Database",
            mock_db
        )

        # Track events
        events_received = []
        event_bus.subscribe(
            SymbolStatsQueriedEvent,
            lambda e: events_received.append(e)
        )

        handler = GetSymbolStatsHandler(event_bus, cache)
        query = GetSymbolStatsQuery(symbol="AAPL", exchange="NASDAQ")

        # First call - cache miss, should publish event
        await handler.handle(query)
        assert len(events_received) == 1

        # Second call - cache hit, should NOT publish event
        await handler.handle(query)
        assert len(events_received) == 1  # Still 1, not 2

        # Database should only be called once
        assert mock_collection.aggregate.call_count == 1
```

**Success Criteria:**
- [ ] Integration test verifies cache prevents duplicate events
- [ ] Database called only once for cached queries
- [ ] Test demonstrates component interaction

---

## Week 4 Checklist

- [ ] Exercise 4.1: Handler tests with mocked singleton
- [ ] Exercise 4.2: Async cache tests
- [ ] Exercise 4.3: Event publishing tests
- [ ] Exercise 4.4: Integration test (optional)
- [ ] All tests pass with `pytest tests/ -v`
- [ ] Coverage report generated

## Verification Commands

```bash
# Run all new tests
pytest tests/unit/features/market_data/ -v

# Run with coverage
pytest tests/unit/features/market_data/ --cov=src/features/market_data/stats --cov-report=term-missing

# Run integration tests
pytest tests/integration/market_data/ -v

# Full test suite
pytest tests/ -v --tb=short
```

## Final Project Checklist

After completing all 4 weeks:

- [ ] Can read Python code fluently
- [ ] Understands asyncio event loop vs C# ThreadPool
- [ ] Can implement CQRS handlers following project patterns
- [ ] Can write tests with mocked singletons
- [ ] All new code passes `pyright` and `ruff check`
- [ ] Comfortable debugging with structured logs

## Congratulations!

You've completed the Python mastery program. Key skills gained:
1. **Syntax fluency** - Type hints, dataclasses, decorators
2. **Async mastery** - asyncio.Lock, coroutines, event loop
3. **Pattern application** - CQRS, events, singletons
4. **Testing confidence** - pytest, monkeypatch, async tests

**Next steps:**
- Contribute to a real feature
- Review PRs with newfound knowledge
- Explore advanced topics (multiprocessing, metaclasses)
