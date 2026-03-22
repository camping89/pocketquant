# Explore: pocketquant-core Package

**Date:** 2026-03-22 | **Package:** pocketquant-core | **Status:** Complete

## Summary

Comprehensive DDD monorepo core package: **4,763 LOC (src) + 846 LOC (tests)** across 90 files. Zero external package dependencies. Three-tier architecture: domain aggregates → concepts (non-persisted logic) → infrastructure ports/adapters → persistence layer.

---

## 1. Directory Structure & File Counts

```
pocketquant-core/
├── src/pocketquant/core/
│   ├── common/              31 files (~978 LOC)    [shared utilities]
│   ├── domain/              23 files (~1249 LOC)   [aggregates + events]
│   ├── concepts/            15 files (~714 LOC)    [non-persisted logic]
│   ├── infrastructure/      13 files (~1211 LOC)   [ports + adapters]
│   ├── persistence/         8 files (~532 LOC)     [repositories]
│   └── config.py            (~80 LOC)              [Settings via pydantic]
│
└── tests/                   7 files (~846 LOC)
    ├── unit/common/         test_mediator, test_event_bus
    ├── unit/domain/         test_domain_purity, test_value_objects
    ├── integration/         test_websocket_integration
    └── conftest.py          [pytest fixtures]
```

**Total:** 90 source files + 7 test files = 97 files | **5,609 LOC total**

---

## 2. Domain Entities & Aggregates

### Top-Level Aggregates (Collection-Backed)

**Bar** (`domain/bar/entities.py` – 104 LOC)
- UUID identity + MongoDB persistence
- OHLCV fields: open, high, low, close, volume
- Metadata: symbol, exchange, interval (Interval enum), datetime
- Methods: `to_mongo()`, `from_mongo()`, `to_dict()`, properties `is_complete`
- Used by: BarRepository, backtest engine, strategy signals

**OrderAggregate** (`domain/order/entities.py` – 266 LOC)
- UUID identity + state machine (PENDING → SUBMITTED → PARTIALLY_FILLED → FILLED | CANCELLED | REJECTED)
- Order types: MARKET, LIMIT, STOP_LIMIT, STOP_MARKET
- Fields: strategy_id, symbol, exchange, side (BUY/SELL), quantity, price, stop_price
- Status transitions validated via `_VALID_TRANSITIONS` class dict
- Methods: `create()`, `submit()`, `fill()`, `partial_fill()`, `cancel()`, `reject()`
- Domain events: OrderSubmittedEvent, OrderFilledEvent, OrderPartiallyFilledEvent, OrderCancelledEvent, OrderRejectedEvent
- Event collection via `collect_events()`

**PositionAggregate** (`domain/position/entities.py` – 238 LOC)
- UUID identity + lifecycle management (open → add/reduce → close)
- Fields: strategy_id, symbol, exchange, side (LONG/SHORT), entry_price, quantity, current_price, realized_pnl
- Weighted average price on scale-in, realized P&L on reduce
- Methods: `open()`, `update_price()`, `add_quantity()`, `reduce_quantity()`, `close()`
- Properties: `unrealized_pnl`, `pnl` (PnL value object), `market_value`, `cost_basis`
- Domain events: PositionOpenedEvent, PositionUpdatedEvent, PositionClosedEvent

**Symbol** (`domain/symbol/entities.py` – 81 LOC)
- UUID identity for tradeable instruments
- Fields: code (uppercase), exchange, name, asset_type, is_active
- Methods: `create()`, `activate()`, `deactivate()`, `symbol_key` property (returns "EXCHANGE:CODE")
- MongoDB persistence with backward-compat mapping: entity field `code` ↔ MongoDB field `symbol`

**SyncStatus** (`domain/sync_status/entities.py` – 51 LOC)
- Tracks data sync progress per symbol/exchange/interval
- Fields: symbol, exchange, interval, last_synced_at, status
- Used for resuming partial syncs

### Value Objects

**Shared** (`domain/shared/value_objects.py`)
- `INTERVAL_SECONDS`: mapping from Interval enum to seconds (1m=60s → 1M=2592000s)
- Re-exports Interval enum for backward compat

**Position** (`domain/position/value_objects.py` – 21 LOC)
- `PnL`: frozen dataclass with unrealized/realized fields
- Properties: `total` (sum), `is_profitable`

**Bar** (`domain/bar/value_objects.py` – 47 LOC)
- OHLC range validation
- Bar builder helpers

**Quote** (`concepts/quote/value_objects.py` – 42 LOC)
- `QuoteData`: bid/ask prices, timestamp, liquidity metrics

**Risk** (`concepts/risk/value_objects.py` – 28 LOC)
- `RiskConfig`: frozen dataclass with model (enum), risk_per_trade%, max_positions, max_exposure_percent
- Validation: `__post_init__` checks ranges (0-10% risk, ≥1 position, 0-100% exposure)

**Strategy** (`concepts/strategy/value_objects.py` – 160 LOC)
- `StrategyConfig`: base config loader from YAML
- `MASettings`: moving average strategy parameters (fast_period, slow_period)
- `StrategyMetrics`: performance aggregates (trades, win_rate, sharpe, max_drawdown)

---

## 3. Shared Enums

| Module | File | Enums |
|--------|------|-------|
| **domain/shared** | `enums.py` | `Interval` (22 values: 1m–1M), |
| **domain/order** | `enums.py` | `OrderType` (4: MARKET, LIMIT, STOP_LIMIT, STOP_MARKET), `OrderSide` (2: BUY, SELL), `OrderStatus` (6: PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED) |
| **domain/position** | `enums.py` | `PositionSide` (2: LONG, SHORT) |
| **concepts/strategy** | `enums.py` | `Direction` (4: LONG, SHORT, EXIT, FLAT) |
| **concepts/risk** | `enums.py` | `RiskModel` (3: PERCENT_RISK, KELLY, FIXED) |

---

## 4. Domain Events

**Base:** `DomainEvent` (frozen dataclass)
- `event_id` (UUID), `occurred_at` (datetime UTC)
- Equality/hash based on event_id only

**Order Events** (`domain/order/events.py` – 61 LOC)
- `OrderSubmittedEvent`, `OrderFilledEvent`, `OrderPartiallyFilledEvent`, `OrderCancelledEvent`, `OrderRejectedEvent`
- Each tracks order_id, strategy_id, order metadata, timestamps

**Position Events** (`domain/position/events.py` – 45 LOC)
- `PositionOpenedEvent`, `PositionUpdatedEvent`, `PositionClosedEvent`
- Track side, entry/exit prices, quantity, P&L

**Bar Events** (`domain/bar/events.py` – 33 LOC)
- `BarCreatedEvent`, `BarUpdatedEvent`
- Track bar data + interval

**Strategy Events** (`concepts/strategy/events.py` – 20 LOC)
- `StrategySignalEvent` (direction, rationale, timestamp)

---

## 5. Infrastructure Ports & Interfaces

### Brokers (`infrastructure/brokers/`)

**IBroker** (`interface.py` – 105 LOC)
- Abstract base class (ABC) for all broker implementations
- Methods (all async):
  - `connect()`, `disconnect()`, `is_connected` property
  - `submit_order(order: OrderAggregate) → OrderResult`
  - `cancel_order(broker_order_id: str) → bool`
  - `get_positions() → list[PositionAggregate]`
  - `get_balance() → AccountBalance`
  - `subscribe_order_updates(callback) → None` (callback can be sync or async)
  - `unsubscribe_order_updates() → None`

**IBrokerFactory** (Protocol, not ABC)
- Factory pattern: `create(broker_type: str, config: dict) → IBroker`
- Separates type-name registration from instance creation

**OrderResult** (`models.py` – 45 LOC)
- Response from `submit_order()`
- Fields: order_id, broker_order_id, status, filled_quantity, filled_price, submitted_at, error_message
- Used by order handlers to update OrderAggregate state

**AccountBalance** (`models.py`)
- Cash, equity, used_margin, available_margin, currency

### PaperBroker (`infrastructure/brokers/paper/paper_broker.py` – 262 LOC)

In-memory simulated broker. Features:
- Configurable initial balance (default 100K USDT), slippage%, fill delay
- Async order submission with simulated fills
- Slippage applied bid/ask (buy price up, sell price down)
- In-memory position tracking with scale-in/scale-out support
- Order callback notifications (sync or async handlers)
- No persistence (state lost on disconnect)
- Used by backtest engine and paper trading mode

### Other Infrastructure

**TradingView WebSocket** (`infrastructure/tradingview/`)
- `TradingViewClient`: REST client for chart data fetch
- `TradingViewWebSocketClient`: WebSocket connection for real-time bars
- Handles subscriptions, unsubscriptions, reconnection

**HTTP Client** (`infrastructure/http_client/client.py` – 93 LOC)
- Wraps httpx AsyncClient for retry + timeout

**Scheduler** (`infrastructure/scheduling/scheduler.py` – 182 LOC)
- APScheduler wrapper for job scheduling
- Methods: `add_job()`, `remove_job()`, `start()`, `shutdown()`
- Used for sync jobs, periodic tasks

---

## 6. Common Utilities

### CQRS Mediator (`common/mediator/` – 157 LOC)

**Mediator** (`mediator.py` – 43 LOC)
- In-process CQRS dispatcher
- `register(request_type, handler)`: 1 handler per request type (throws on duplicate)
- `send(request)`: dispatches to handler, returns response
- `get_registered_types()`, `has_handler()`: introspection

**Handler** (`handler.py` – 17 LOC)
- Generic ABC: `async def handle(request: TRequest) → TResponse`

**HandlerRegistry** (`handler_registry.py`)
- Auto-registers handlers decorated with `@handles(RequestType)`
- Reads `_handles_request_type` metadata

**Exceptions** (`exceptions.py`)
- `DuplicateHandlerError`, `HandlerNotFoundError`

### Event Bus (`common/messaging/` – 176 LOC)

**EventBus** (`event_bus.py` – 63 LOC)
- In-memory async pub/sub for domain events
- FIFO delivery per event type
- Bounded history (default 50 events)
- Methods: `subscribe()`, `unsubscribe()`, `publish()`, `publish_all()`
- Introspection: `get_subscriber_count()`, `get_all_event_types()`, `get_history()`

**EventHandler** base class
- Generic handler for event types

**EventRegistry**
- Auto-discovery and registration of event handlers

### Configuration (`config.py` – 80 LOC)

**Settings** (Pydantic BaseSettings)
- App metadata: name, version, environment (dev/staging/prod)
- MongoDB: url, database name, pool sizes
- Redis: url, cache TTL
- TradingView: optional username/password
- Logging: level, format (json/console)
- Jobs: worker count, enable flag
- OKX: optional API keys, demo mode flag
- Strategy defaults: broker type (paper/okx), initial balance, slippage
- Resolution: reads .env file (lazy lookup via `_find_project_root()` + `[tool.uv.workspace]`)
- Singleton: `@lru_cache def get_settings() → Settings`

### Other Common

**UUID** (`common/uuid.py`)
- `UUID` type alias + `generate_id()`, `generate_id_str()`

**Tracing** (`common/tracing/`)
- Context, correlation IDs, request logging

**Health Checks** (`common/health/`)
- Coordinator + checks interfaces

**Rate Limiting** (`common/rate_limit/middleware.py`)
- Middleware stub

**Time Simulation** (`common/time/simulation.py`)
- Mocked time for backtest (freezes clock)

**Logging** (`common/logging/setup.py`)
- Structlog setup with JSON or console formatters

**Idempotency** (`common/idempotency/middleware.py`)
- Idempotent request deduplication

**Job Runner** (`common/jobs/`)
- Job orchestration stubs

**Constants** (`common/constants.py`)
- Collection names: `COLLECTION_BARS`, etc.

---

## 7. Persistence Layer

### Base Repository (`persistence/base_repository.py` – 21 LOC)

**BaseRepository** mixin
- DI-injected `Database` instance
- Subclasses set `_collection_name` class var
- Protected `_collection()` returns MongoDB collection handle

### MongoDB Connection (`persistence/mongodb.py` – 71 LOC)

**Database** class (instance-based for DI)
- Private `__client` (AsyncMongoClient), `__database` (AsyncDatabase)
- `async connect(settings)`: establishes connection, runs server_info() healthcheck
- `async disconnect()`: closes client, clears refs
- `get_database()`, `get_collection(name)`: public accessors (raises if not connected)
- Name mangling (__) prevents external access to internals

### Redis Cache (`persistence/redis.py`)
- Redis connection manager (similar to Database)

### Repositories (`persistence/repositories/`)

**BarRepository** (`bar_repository.py` – 174 LOC)
- Methods:
  - `insert_many(bars) → int`: bulk insert, skips duplicates via BulkWriteError handling
  - `upsert_bar(bar)`: upsert single bar (updates or inserts)
  - `find(symbol, exchange, interval, start_date?, end_date?, limit?) → list[Bar]`: queries with date range
  - `stream(symbol, exchange, interval, start, end) → AsyncIterator[Bar]`: async generator for backtest
  - `count()`, `get_latest()`: metadata queries
  - `ensure_indexes()`: compound index on (symbol, exchange, interval, datetime)

**SymbolRepository** (`symbol_repository.py`)
- CRUD for Symbol entities

**SyncStatusRepository** (`sync_status_repository.py`)
- Tracks sync progress per symbol/interval

---

## 8. Concepts (Non-Persisted Logic)

### Strategy (`concepts/strategy/` – 454 LOC)

**StrategyInterface** (`interfaces.py` – 80 LOC)
- Abstract protocol for strategy implementations
- Methods: `generate_signal(bars: list[Bar]) → StrategySignal`

**MASettings** & **StrategyMetrics** value objects
- MA configuration + performance tracking

**MACrossover** service (`services/ma_crossover.py` – 156 LOC)
- Pure domain service for MA-crossover strategy
- No I/O, no external deps
- Calculates SMA, generates LONG/SHORT/EXIT signals based on crossover

### Risk (`concepts/risk/` – 179 LOC)

**RiskConfig** value object
- `model`: PERCENT_RISK | KELLY | FIXED
- `risk_per_trade`, `max_positions`, `max_exposure_percent`
- Validation in `__post_init__()`

**PositionSizer** service (`services/position_sizer.py` – 128 LOC)
- Pure domain: `calculate_size(balance, entry_price, stop_loss, risk_config) → float`
- Implements 3 models:
  - **Percent Risk**: size = (balance × risk%) / |entry - stop|
  - **Kelly**: size = (balance × kelly_fraction) / entry_price
  - **Fixed**: size = (balance × max_exposure) / entry_price
- `validate_size()`: checks exposure limits

### Quote (`concepts/quote/` – 67 LOC)

**QuoteData** value object
- Bid/ask prices, timestamp, spread, liquidity

---

## 9. Key Patterns & Architectural Decisions

### DDD (Domain-Driven Design)

1. **Layering**: Domain → Concepts → Infrastructure → Persistence
2. **Aggregates**: Bar, OrderAggregate, PositionAggregate, Symbol (collection roots with identity)
3. **Value Objects**: PnL, RiskConfig, QuoteData, Interval (immutable, no identity)
4. **Domain Events**: Published by aggregates, consumed by event bus subscribers
5. **Event Sourcing**: Aggregates collect events via `collect_events()`, cleared after publish

### CQRS (Command Query Responsibility Segregation)

- **Mediator**: Single dispatcher for all commands/queries
- **Handlers**: One handler per request type (registered via `@handles` decorator)
- **No Query-side projections yet**: In-process only (ready for event store + read models)

### Ports & Adapters

- **IBroker** protocol: Abstraction for paper & OKX implementations
- **IBrokerFactory** protocol: Decouples strategy from broker creation
- **PaperBroker**: In-memory adapter (no external deps)
- **TradingView adapter**: REST + WebSocket clients

### Persistence

- **Pydantic serialization**: Aggregates define `to_mongo()`, `from_mongo()` (not ORM)
- **No O/R mapping**: Raw MongoDB documents ↔ Pydantic models
- **MongoDB _id**: Maps to aggregate UUID (backward compat for symbol: code ↔ symbol field)
- **DI injection**: Database instance injected into repositories

### Pure Domain Services

- **PositionSizer**: No I/O, pure calculation
- **MACrossover**: No persistence, pure signal logic

---

## 10. Test Structure (846 LOC, 7 files)

| Test File | Purpose | Tests |
|-----------|---------|-------|
| `tests/conftest.py` | Pytest fixtures | Settings, Mediator, EventBus |
| `tests/unit/common/test_mediator.py` | CQRS dispatcher | Register, dispatch, duplicate handlers, decorator |
| `tests/unit/common/test_event_bus.py` | Pub/sub | Subscribe, publish, history, unsubscribe |
| `tests/unit/domain/test_domain_purity.py` | Domain logic | Aggregate invariants, state machines |
| `tests/unit/domain/test_value_objects.py` | Value objects | PnL, RiskConfig, Interval conversions |
| `tests/unit/infrastructure/tradingview/test_websocket.py` | WebSocket adapter | Connection, subscription, parsing |
| `tests/integration/tradingview/test_websocket_integration.py` | Live WebSocket | E2E with TradingView server |

---

## 11. Public API Surface

### Imports (from CLAUDE.md)

```python
# Core domain
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.persistence.repositories import BarRepository
from pocketquant.core.infrastructure.brokers import IBroker, PaperBroker, IBrokerFactory
from pocketquant.core.config import Settings
```

### Key Classes & Protocols

- **Aggregates**: Bar, OrderAggregate, PositionAggregate, Symbol, SyncStatus
- **Value Objects**: PnL, RiskConfig, QuoteData, StrategyMetrics, Interval (enum)
- **Infrastructure Ports**: IBroker, IBrokerFactory
- **Implementations**: PaperBroker, TradingViewClient, TradingViewWebSocketClient
- **CQRS**: Mediator, Handler, EventBus
- **Persistence**: Database, BaseRepository, BarRepository, SymbolRepository, SyncStatusRepository
- **Services**: PositionSizer, MACrossover
- **Config**: Settings, RiskConfig

---

## 12. Dependencies & Constraints

### Package Dependencies (pyproject.toml)

Zero custom package dependencies. External only:
- **pydantic** 2.5+ (models, validation, settings)
- **pymongo** 4.16+ (MongoDB async driver)
- **redis** 5.0+ (caching)
- **apscheduler** 3.10+ (job scheduling)
- **tvdatafeed** (TradingView scraper, git+https)
- **websockets** 12.0+ (WebSocket protocol)
- **pandas, numpy** (data processing)
- **pyyaml** (config parsing)
- **structlog** 24.1+ (JSON/console logging)
- **httpx** 0.26+ (async HTTP)
- **rich** 13+ (terminal formatting)

### Architecture Constraints

- **No O/R mapping**: Raw Pydantic ↔ MongoDB
- **Namespace packages**: No `__init__.py` at `pocketquant/` level (PEP 420)
- **DI container**: Managed by pocketquant-api package (not core)
- **Async-first**: All I/O operations are async (Mediator, EventBus, repositories, brokers)
- **No circular deps**: core ← {backtest, trading} ← api

---

## Summary: What This Package Provides

| Layer | Purpose | Key Classes |
|-------|---------|-------------|
| **Domain** | Business logic, aggregates, events | OrderAggregate, PositionAggregate, Bar, Symbol, domain events |
| **Concepts** | Non-persisted domain logic | PositionSizer, MACrossover, RiskConfig, StrategyMetrics |
| **Infrastructure** | External adapters, protocols | IBroker, PaperBroker, TradingViewClient, Database |
| **Persistence** | MongoDB + Redis access | BarRepository, SymbolRepository, Database |
| **Common** | Shared utilities | Mediator, EventBus, Settings, UUID, logging, tracing |

**Summary:** Core is self-contained, zero custom dependencies, ready for composition by api package via DI. Aggregates use Pydantic for serialization. Pure domain services (PositionSizer, MACrossover) facilitate testing. CQRS + EventBus patterns enable loose coupling.

