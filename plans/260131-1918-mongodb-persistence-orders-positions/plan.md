---
title: "MongoDB Persistence for Orders and Positions"
description: "Add MongoDB repositories for OrderAggregate and PositionAggregate with async operations"
status: complete
priority: P1
effort: 3h
branch: feat/strategy-init
tags: [mongodb, persistence, trading, orders, positions]
created: 2026-01-31
---

# MongoDB Persistence for Orders and Positions

## Overview

Add MongoDB persistence layer for `OrderAggregate` and `PositionAggregate` following existing codebase patterns. Update `OrderManager` and `PositionTracker` to use repositories for persistence.

## Current State

- **In-memory only**: `OrderManager._orders`, `PositionTracker._positions` dicts
- **Domain models exist**: `src/domain/order/aggregate.py`, `src/domain/position/aggregate.py`
- **MongoDB infrastructure ready**: `src/infrastructure/persistence/mongodb.py` with async Motor client
- **Pattern reference**: `src/features/market_data/sync/handler.py` shows direct collection access via `Database.get_collection()`

## Architecture Decision

**Repository Pattern** - Create dedicated repository classes (not inline in handlers) for:
- Reusability across handlers
- Testability (mock repositories)
- Separation of concerns

## Phases

| Phase | Description | Status | Est |
|-------|-------------|--------|-----|
| 1 | Add collection constants | pending | 10m |
| 2 | Create Pydantic models for MongoDB serialization | pending | 30m |
| 3 | Create OrderRepository | pending | 45m |
| 4 | Create PositionRepository | pending | 45m |
| 5 | Update OrderManager | pending | 30m |
| 6 | Update PositionTracker | pending | 30m |

---

## Phase 1: Collection Constants

**File**: `src/common/constants.py`

Add:
```python
COLLECTION_ORDERS = "orders"
COLLECTION_POSITIONS = "positions"
```

---

## Phase 2: MongoDB Models

**Location**: `src/features/trading/models/`

### `src/features/trading/models/__init__.py`
```python
from src.features.trading.models.order import OrderDocument
from src.features.trading.models.position import PositionDocument

__all__ = ["OrderDocument", "PositionDocument"]
```

### `src/features/trading/models/order.py`
Pydantic model for MongoDB serialization:

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from src.domain.order import OrderAggregate, OrderSide, OrderStatus, OrderType


class OrderDocument(BaseModel):
    """MongoDB document for orders."""
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    strategy_id: str
    symbol: str
    exchange: str
    side: str  # Store as string, convert to enum
    order_type: str
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    status: str
    filled_quantity: float = 0.0
    filled_price: float | None = None
    broker_order_id: str | None = None
    created_at: datetime
    updated_at: datetime

    def to_mongo(self) -> dict[str, Any]:
        """Convert to MongoDB document."""
        data = self.model_dump(by_alias=True)
        return data

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> "OrderDocument":
        """Create from MongoDB document."""
        return cls(**doc)

    @classmethod
    def from_aggregate(cls, agg: OrderAggregate) -> "OrderDocument":
        """Create from domain aggregate."""
        return cls(
            _id=agg.id,
            strategy_id=agg.strategy_id,
            symbol=agg.symbol,
            exchange=agg.exchange,
            side=agg.side.value,
            order_type=agg.order_type.value,
            quantity=agg.quantity,
            price=agg.price,
            stop_price=agg.stop_price,
            status=agg.status.value,
            filled_quantity=agg.filled_quantity,
            filled_price=agg.filled_price,
            broker_order_id=agg.broker_order_id,
            created_at=agg.created_at,
            updated_at=agg.updated_at,
        )

    def to_aggregate(self) -> OrderAggregate:
        """Convert back to domain aggregate."""
        return OrderAggregate(
            id=self.id,
            strategy_id=self.strategy_id,
            symbol=self.symbol,
            exchange=self.exchange,
            side=OrderSide(self.side),
            order_type=OrderType(self.order_type),
            quantity=self.quantity,
            price=self.price,
            stop_price=self.stop_price,
            status=OrderStatus(self.status),
            filled_quantity=self.filled_quantity,
            filled_price=self.filled_price,
            broker_order_id=self.broker_order_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
```

### `src/features/trading/models/position.py`
Similar pattern for PositionAggregate.

---

## Phase 3: OrderRepository

**File**: `src/features/trading/repositories/order_repository.py`

```python
from src.common.constants import COLLECTION_ORDERS
from src.common.database import Database
from src.domain.order import OrderAggregate, OrderStatus
from src.features.trading.models import OrderDocument

class OrderRepository:
    """MongoDB repository for orders."""

    @staticmethod
    def _collection():
        return Database.get_collection(COLLECTION_ORDERS)

    async def save(self, order: OrderAggregate) -> None:
        """Upsert order to MongoDB."""
        doc = OrderDocument.from_aggregate(order).to_mongo()
        await self._collection().replace_one(
            {"_id": order.id},
            doc,
            upsert=True,
        )

    async def get(self, order_id: str) -> OrderAggregate | None:
        """Get order by ID."""
        doc = await self._collection().find_one({"_id": order_id})
        if not doc:
            return None
        return OrderDocument.from_mongo(doc).to_aggregate()

    async def find_by_strategy(self, strategy_id: str) -> list[OrderAggregate]:
        """Get all orders for a strategy."""
        cursor = self._collection().find({"strategy_id": strategy_id})
        return [
            OrderDocument.from_mongo(doc).to_aggregate()
            async for doc in cursor
        ]

    async def find_active_by_strategy(self, strategy_id: str) -> list[OrderAggregate]:
        """Get active (non-terminal) orders for strategy."""
        active_statuses = [
            OrderStatus.PENDING.value,
            OrderStatus.SUBMITTED.value,
            OrderStatus.PARTIALLY_FILLED.value,
        ]
        cursor = self._collection().find({
            "strategy_id": strategy_id,
            "status": {"$in": active_statuses},
        })
        return [
            OrderDocument.from_mongo(doc).to_aggregate()
            async for doc in cursor
        ]

    async def find_by_status(self, status: OrderStatus) -> list[OrderAggregate]:
        """Get orders by status."""
        cursor = self._collection().find({"status": status.value})
        return [
            OrderDocument.from_mongo(doc).to_aggregate()
            async for doc in cursor
        ]

    async def ensure_indexes(self) -> None:
        """Create indexes for efficient queries."""
        coll = self._collection()
        await coll.create_index("strategy_id")
        await coll.create_index("symbol")
        await coll.create_index("status")
        await coll.create_index([("strategy_id", 1), ("status", 1)])
```

---

## Phase 4: PositionRepository

**File**: `src/features/trading/repositories/position_repository.py`

Same pattern as OrderRepository with position-specific queries:
- `save(position)` - upsert
- `get(position_id)` - by ID
- `get_by_strategy(strategy_id)` - single open position per strategy
- `find_open()` - all open positions
- `find_closed_by_strategy(strategy_id)` - historical closed positions

---

## Phase 5: Update OrderManager

**File**: `src/features/trading/managers/order_manager.py`

Changes:
1. Inject `OrderRepository` in constructor
2. After state changes, call `await self._repo.save(order)`
3. Load orders from DB on startup (optional, for recovery)

```python
class OrderManager:
    def __init__(self, event_bus: EventBus, repo: OrderRepository) -> None:
        self._event_bus = event_bus
        self._repo = repo
        # Keep in-memory cache for performance
        self._orders: dict[str, OrderAggregate] = {}
        ...

    async def submit(self, order: OrderAggregate, broker: IBroker) -> OrderResult:
        # ... existing logic ...
        # After status update:
        await self._repo.save(order)
        return result
```

---

## Phase 6: Update PositionTracker

**File**: `src/features/trading/managers/position_tracker.py`

Changes:
1. Inject `PositionRepository` in constructor
2. Save position after updates
3. Load open positions on `start()` for recovery

```python
class PositionTracker:
    def __init__(self, event_bus: EventBus, repo: PositionRepository) -> None:
        self._event_bus = event_bus
        self._repo = repo
        self._positions: dict[str, PositionAggregate] = {}
        ...

    async def start(self) -> None:
        # Load open positions from DB
        open_positions = await self._repo.find_open()
        for pos in open_positions:
            self._positions[pos.strategy_id] = pos
        ...
```

---

## Files to Create

```
src/features/trading/
├── models/
│   ├── __init__.py
│   ├── order.py
│   └── position.py
└── repositories/
    ├── __init__.py
    ├── order_repository.py
    └── position_repository.py
```

## Files to Modify

- `src/common/constants.py` - Add collection names
- `src/features/trading/managers/order_manager.py` - Inject and use repo
- `src/features/trading/managers/position_tracker.py` - Inject and use repo

---

## Index Strategy

| Collection | Indexes |
|------------|---------|
| orders | `strategy_id`, `symbol`, `status`, `(strategy_id, status)` |
| positions | `strategy_id`, `symbol`, `is_closed`, `(strategy_id, is_closed)` |

---

## Success Criteria

- [x] OrderRepository saves/loads orders correctly
- [x] PositionRepository saves/loads positions correctly
- [x] OrderManager persists state changes
- [x] PositionTracker persists state changes
- [x] Indexes created for query performance
- [x] Existing tests pass (56/56 passed)
- [x] Recovery on restart loads open positions/pending orders

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Performance overhead | Keep in-memory cache, async writes |
| Stale cache | Write-through: update cache after DB write |
| Startup delay | Lazy load or background load |

---

## Dependencies

- MongoDB connection already established
- Domain aggregates complete with all fields

---

## Next Steps

After persistence:
1. Add historical trade queries for analytics
2. Add position reconciliation job
3. Consider Redis cache for hot data
