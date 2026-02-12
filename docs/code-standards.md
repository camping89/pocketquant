# Code Standards & Patterns

**Last Updated:** 2026-02-12 | **Coverage:** 213 files, 14,393 LOC (182 Python files in src/)

## Architecture Patterns

### 1. Vertical Slice Architecture

Each feature (market_data, backtesting, strategy, trading, risk) is self-contained with all layers in one directory. No shared services between slices except via infrastructure singletons.

```
features/
├── market_data/         (2,116 LOC, 31 files)
├── backtesting/         (2,259 LOC, 27 files)
├── strategy/            (1,236 LOC, 18 files)
├── trading/             (782 LOC, 12 files)
└── risk/                (163 LOC, 5 files)

Each slice contains:
├── api/                 # FastAPI routes
├── handlers/            # CQRS handlers
├── models/              # Pydantic DTOs
├── services/            # Business logic (optional)
├── repositories/        # Data access (optional)
└── jobs/                # Background tasks (optional)
```

**Rationale:** Tight cohesion within feature, loose coupling between features. Easy to add/remove features without cascading changes. Each slice owns API contracts and data models.

### 2. Singleton Infrastructure (Class-Method Pattern)

Expensive connections (DB, Cache, JobScheduler) are singletons with class methods as API:

```python
# Database
from src.common.database import Database

collection = Database.get_collection("ohlcv")
await Database.connect(settings)
await Database.disconnect()

# Cache
from src.common.cache import Cache

value = await Cache.get("key")
await Cache.set("key", value, ttl=3600)

# Jobs
from src.common.jobs import JobScheduler

JobScheduler.initialize(settings)
JobScheduler.add_interval_job(func, interval_seconds)
```

**Rationale:** Avoids DI complexity for expensive resources, single shared connection per resource type, initialized once at startup, clean API.

### 3. Repository Pattern (Stateless Data Access)

All data access through class methods. No instance state.

```python
# OHLCVRepository
class OHLCVRepository:
    @classmethod
    async def upsert_many(cls, records: List[OHLCVCreate]) -> int:
        # Bulk insert/update with unique key
        pass

    @classmethod
    async def get_bars(cls, symbol: str, exchange: str, interval: str, limit: int = 100):
        # Query with filtering and sorting
        pass
```

**Rationale:** Stateless design, easy to test, no complex lifecycle management, class methods used directly without instantiation.

### 4. Service Pattern (Business Logic)

Two patterns depending on state requirements:

#### Per-Request Instantiation (Stateless)

```python
# DataSyncService - injected with Settings
class DataSyncService:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def sync_symbol(self, symbol: str, exchange: str, interval: str, n_bars: int):
        # Fetch, upsert, invalidate cache
        pass
```

Used for: Data sync, calculations, stateless transformations.

#### Singleton (Stateful)

```python
# QuoteService - maintains WebSocket state
class QuoteService:
    _instance: Optional["QuoteService"] = None
    _running: bool = False

    @classmethod
    def get_instance(cls) -> "QuoteService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self):
        self._running = True
        # Initialize WebSocket
```

Used for: WebSocket connections, persistent state, event distribution.

**Rationale:** Per-request services are simple and testable. Singleton services for state that must persist across requests.

### 5. Provider Pattern (External Integrations)

Encapsulate external API calls with clean interface:

```python
# TradingViewProvider
class TradingViewProvider:
    def __init__(self, username: Optional[str], password: Optional[str]):
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def get_bars(self, symbol: str, exchange: str, interval: str, n_bars: int):
        # Run blocking tvdatafeed in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self._fetch_bars, ...)
```

**Rationale:** Isolates blocking I/O from async event loop, clean error handling, easy to mock for testing.

### 6. Event Handler Auto-Discovery Pattern

Register event subscribers automatically using the `@event_handler` decorator:

```python
from src.common.messaging.event_registry import event_handler

class PositionTracker:
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
from src.common.messaging.event_registry import get_event_registry

registry = get_event_registry()
count = registry.register_instance(position_tracker, event_bus)
# All @event_handler methods now subscribed to EventBus
```

**Benefits:**
- Decorative, self-documenting: Clear which methods handle which events
- Auto-discovery: No manual subscribe() calls
- Scalable: Add new handlers without modifying mediator
- Type-safe: Event types checked at decorator definition

### 7. CQRS Handler Pattern

Separate request handlers for commands (mutate state) and queries (read-only). All handlers extend `Handler[TRequest, TResponse]` base class.

```python
from src.common.mediator import Handler

# Command Handler (mutates state)
class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResultDTO]):
    def __init__(self, provider: IDataProvider):
        self.provider = provider

    async def handle(self, cmd: SyncSymbolCommand) -> SyncResultDTO:
        # 1. Fetch from infrastructure
        bars = await self.provider.fetch_ohlcv(
            cmd.symbol, cmd.exchange, cmd.interval, cmd.n_bars
        )

        # 2. Validate via domain
        aggregate = OHLCVAggregate(bars)

        # 3. Persist via infrastructure
        collection = Database.get_collection("ohlcv")
        await collection.bulk_write([...])

        # 4. Publish domain events
        await EventBus.publish(HistoricalDataSyncedEvent(...))

        # 5. Return DTO (never return entities)
        return SyncResultDTO(bars_synced=len(bars), status="completed")

# Query Handler (read-only)
class GetBarsHandler(Handler[GetBarsQuery, BarsDTO]):
    async def handle(self, query: GetBarsQuery) -> BarsDTO:
        cache_key = f"ohlcv:{query.symbol}:{query.interval}"

        # 1. Check cache first
        cached = await Cache.get(cache_key)
        if cached:
            return cached

        # 2. Query database
        collection = Database.get_collection("ohlcv")
        bars = await collection.find({
            "symbol": query.symbol,
            "interval": query.interval
        }).to_list(query.limit)

        # 3. Cache result (300s TTL)
        result = BarsDTO(bars=bars, count=len(bars))
        await Cache.set(cache_key, result, ttl=300)

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
- Handlers are stateless, instantiated per-request
- Constructor receives dependencies (injected by route or factory)
- `handle()` must be idempotent if possible (for retries)
- Return DTOs, not domain entities
- Publish domain events for all state changes

### 8. Strategy Implementation Pattern

Implement IStrategy interface for custom trading strategies:

```python
from src.domain.strategy.base import IStrategy

class MACrossoverStrategy(IStrategy):
    def __init__(self, fast_period: int = 10, slow_period: int = 20):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.fast_ma = None
        self.slow_ma = None

    async def on_bar(self, bar: OHLCVBar) -> Optional[StrategySignal]:
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
- No direct broker/database access (StrategyEngine manages execution)

## Code Organization Guidelines

### File Naming

Use kebab-case with descriptive names that indicate purpose:

```
quote_routes.py           # FastAPI routes for quotes
quote_service.py          # QuoteService business logic
quote_aggregator.py       # QuoteAggregator bar building
ohlcv_repository.py       # OHLCVRepository data access
tradingview.py            # TradingViewProvider for REST API
tradingview_ws.py         # TradingViewWebSocketProvider for WebSocket
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

```python
# 1. Standard library
import asyncio
from datetime import datetime
from typing import Optional, List

# 2. Third-party
from pydantic import BaseModel
import structlog

# 3. Local
from src.common.database import Database
from src.common.logging import get_logger
from src.features.market_data.models import OHLCV
```

## Commenting & Documentation

### Comments (Minimal)

**DO write comments for:**

- Non-obvious logic or complex algorithms
- WHY something is done a certain way (not WHAT)
- Non-obvious constraints or limitations
- Gotchas or warnings about subtle behavior
- External API quirks or workarounds

```python
# Example: WHY comments
# Run in thread pool to avoid blocking event loop
bars = await loop.run_in_executor(self.executor, self._fetch_bars)

# tvdatafeed max is 5000 bars per request
if n_bars > 5000:
    n_bars = 5000
```

**DO NOT write comments for:**

- Obvious code operations (e.g., `# Create list`, `# Return result`)
- Code that restates variable/function names
- Trivial sections or obvious operations
- Code that is self-documenting via type hints and naming

```python
# BAD: This comment adds no value
# Get the collection
collection = Database.get_collection("ohlcv")

# GOOD: Self-documenting code
collection = Database.get_collection("ohlcv")
```

### Docstrings (Brief)

Keep docstrings minimal. Heavy lifting done by type hints:

```python
# Good: Type hints + brief description
async def get_bars(
    cls,
    symbol: str,
    exchange: str,
    interval: str,
    limit: int = 100
) -> List[OHLCV]:
    """Retrieve OHLCV bars for a symbol."""

# Skip Args/Returns/Raises if types are clear from signature
```

### Module Docstrings

Brief purpose statement:

```python
"""
Quote service for managing TradingView WebSocket subscriptions.
Handles connection lifecycle, quote caching, and tick distribution.
"""
```

## Type Hints

Use full type hints everywhere:

```python
# Function signatures
async def sync_symbol(
    self,
    symbol: str,
    exchange: str,
    interval: str,
    n_bars: int
) -> Dict[str, Any]:
    pass

# Class attributes
_client: pymongo.asynchronous.AsyncMongoClient
_database: pymongo.asynchronous.AsyncDatabase
_lock: asyncio.Lock = asyncio.Lock()

# Complex types
from typing import Optional, List, Dict, Tuple, Union, Callable, Any
bars: List[OHLCV]
status: Optional[SyncStatus]
result: Dict[str, Union[int, str]]
```

**Tools:**
- `pyright src/` - Type checking (catches type errors at development time)
- `ruff check .` - Linting (includes type annotation checks)

## Error Handling

### Try-Except Strategy

Catch specific exceptions, never bare `except`:

```python
# Good: Catch specific exception
try:
    bars = await provider.get_bars(symbol)
except ValueError as e:
    logger.error("invalid_symbol", symbol=symbol, error=str(e))
    return {"status": "error", "message": str(e)}

# Bad: Generic exception catching
try:
    bars = await provider.get_bars(symbol)
except Exception:
    pass
```

### Error Propagation

- Routes: Catch exceptions, return error responses
- Services: Catch and log, update status, return error dict
- Repositories: Let exceptions propagate (caller handles)
- Providers: Catch specific errors, re-raise as custom exceptions

```python
# Service (catches and returns error)
try:
    bars = await self.provider.get_bars(symbol, exchange, interval, n_bars)
except Exception as e:
    status = await OHLCVRepository.update_sync_status(status_id, "error", str(e))
    return {"status": "error", "error_message": str(e)}

# Route (returns HTTP response)
result = await service.sync_symbol(...)
if result["status"] == "error":
    return JSONResponse(status_code=400, content=result)
```

### Logging

Use structured logging with context variables:

```python
from src.common.logging import get_logger

logger = get_logger(__name__)

# Log events with context
logger.info("sync_started", symbol="AAPL", exchange="NASDAQ", n_bars=500)
logger.error("sync_failed", symbol="AAPL", error=str(e), traceback=traceback.format_exc())
logger.warning("slow_query", query_time_ms=1500, threshold_ms=1000)
```

**Avoid:**
- String formatting in log calls (`f"User {user_id} created"` → log with context)
- Generic log messages without context
- DEBUG level logging for every operation

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

We use **Pyright** (via Pylance in VSCode) instead of mypy:
- **3-5x faster** than mypy for large codebases
- **Native VSCode integration** via Pylance extension
- **Better type inference** for complex patterns
- **Pydantic v2 native support** (no plugin needed)

```bash
pyright src/                 # Type check entire source
pyright src/features/market_data/services/  # Check specific module
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
await OHLCVRepository.upsert_many(records)  # One round trip to DB

# Bad: Loop of individual inserts
for record in records:
    await OHLCVRepository.insert_one(record)  # N round trips!
```

### Cache Invalidation

Use pattern-based deletion for correctness (vs selective):

```python
# Good: Pattern-based deletion (simple, correct)
await Cache.delete_pattern("ohlcv:AAPL:*")

# Bad: Selective deletion (easy to miss keys)
await Cache.delete(f"ohlcv:AAPL:NYSE:1d:100")
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
# In src/config.py
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
| quote_service.py | 236 LOC | <200 (consider split if modified) |
| data_sync_service.py | 244 LOC | <200 |
| routes.py | 472 LOC | Split into smaller route modules |

**Current largest files (acceptable but monitor):**
- `quote_aggregator.py` - 368 LOC (core algorithm, complexity justified)
- `routes.py` - 472 LOC (may benefit from split)

## UUID Generation (Time-Ordered IDs)

All aggregates use UUID7 (time-ordered) for better database indexing:

```python
from src.common.uuid import generate_id, generate_id_str

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

## Deprecated Patterns (Do Not Use)

❌ Synchronous blocking I/O in async context
❌ Global mutable state outside singletons
❌ Bare except clauses
❌ String formatting in log calls
❌ Service instantiation as global variables
❌ Database connection per-request (use singleton)
❌ No type hints on public APIs
❌ Comments explaining obvious code
❌ Circular imports between features
❌ Feature-specific configuration in main module
❌ Manual event subscription instead of @event_handler decorator
❌ UUID4 for aggregates (use UUID7)

## Quality Checklist

Before committing:

- [ ] All type hints present on public APIs
- [ ] No syntax errors (ruff check passes)
- [ ] Code formatted (ruff format run)
- [ ] Type checking passes (pyright)
- [ ] Tests pass (pytest)
- [ ] Test coverage ≥80%
- [ ] Comments only for non-obvious logic
- [ ] No blocking I/O in async functions
- [ ] Error paths tested
- [ ] Environment variables used (not hardcoded)
- [ ] Log statements have context
- [ ] No secrets in code or config
