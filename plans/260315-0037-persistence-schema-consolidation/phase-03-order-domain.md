# Phase 3: Order Domain + Repo

## Overview
- **Priority**: MEDIUM
- **Status**: completed

## Context
- Current schema: `src/persistence/schemas/order_schema.py` — `OrderDocument` (Pydantic)
- Current aggregate: `src/domain/order/aggregate.py` — `OrderAggregate` (dataclass)
- Current repo: `src/persistence/repositories/order_repository.py`
- `OrderDocument` has `from_aggregate()` / `to_aggregate()` — clean bidirectional mapping

## Key Insight

`OrderAggregate` already has `created_at` and `updated_at` as business fields (set in `submit()`, `fill()`, `cancel()`, etc.). These are **business timestamps** — keep them on the entity. Repo also `$set`s infrastructure `updated_at` on every write.

`id` is already `str` (UUID7 string via `generate_id_str()`). No type change needed.

## Files to Modify

| File | Action |
|------|--------|
| `src/domain/order/aggregate.py` | Migrate dataclass → Pydantic, add `to_mongo()`/`from_mongo()` |
| `src/persistence/repositories/order_repository.py` | Use `order.to_mongo()` / `OrderAggregate.from_mongo()`, remove `OrderDocument` import |
| `src/domain/order/__init__.py` | Update exports |

## Files to Delete
| File | Reason |
|------|--------|
| `src/persistence/schemas/order_schema.py` | Replaced by aggregate methods |

## Implementation Steps

### 1. Migrate `OrderAggregate` (dataclass → Pydantic)

Key changes:
- `@dataclass` → `class OrderAggregate(BaseModel):`
- `field(default_factory=...)` → `Field(default_factory=...)`
- `_events: list[DomainEvent] = field(...)` → `_events: list[DomainEvent] = PrivateAttr(default_factory=list)`
- `_VALID_TRANSITIONS: ClassVar[...]` stays as-is (ClassVar works in Pydantic)
- `_events.append(...)` in methods — works with PrivateAttr, accessed via `self._events`

```python
def to_mongo(self) -> dict[str, Any]:
    return {
        "_id": self.id,
        "strategy_id": self.strategy_id,
        "symbol": self.symbol,
        "exchange": self.exchange,
        "side": self.side.value,
        "order_type": self.order_type.value,
        "quantity": self.quantity,
        "price": self.price,
        "stop_price": self.stop_price,
        "status": self.status.value,
        "filled_quantity": self.filled_quantity,
        "filled_price": self.filled_price,
        "broker_order_id": self.broker_order_id,
        "created_at": self.created_at,
        "updated_at": self.updated_at,
    }

@classmethod
def from_mongo(cls, doc: dict[str, Any]) -> "OrderAggregate":
    return cls(
        id=doc["_id"],
        strategy_id=doc["strategy_id"],
        symbol=doc["symbol"],
        exchange=doc["exchange"],
        side=OrderSide(doc["side"]),
        order_type=OrderType(doc["order_type"]),
        quantity=doc["quantity"],
        price=doc.get("price"),
        stop_price=doc.get("stop_price"),
        status=OrderStatus(doc["status"]),
        filled_quantity=doc.get("filled_quantity", 0.0),
        filled_price=doc.get("filled_price"),
        broker_order_id=doc.get("broker_order_id"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )
```

### 2. PrivateAttr init pattern

Pydantic `PrivateAttr` fields are NOT set via constructor. Current code in `_events.append()` inside methods works fine — `self._events` is initialized by `PrivateAttr(default_factory=list)` at model creation.

But: `PositionAggregate.open()` does `position._events.append(...)` — this works because PrivateAttr is accessible after construction.

### 3. Update `OrderRepository`

```python
# Before
doc = OrderDocument.from_aggregate(order)
await collection.replace_one({"_id": order.id}, doc.model_dump(by_alias=True), upsert=True)

# After
doc = order.to_mongo()
await collection.replace_one({"_id": order.id}, doc, upsert=True)
```

Read path:
```python
# Before
return OrderDocument(**doc).to_aggregate()

# After
return OrderAggregate.from_mongo(doc)
```

### 4. Delete `src/persistence/schemas/order_schema.py`

### 5. Compile check + test

## Success Criteria

- [x] `OrderAggregate` is Pydantic with `to_mongo()`/`from_mongo()`
- [x] No imports from `src.persistence.schemas.order_schema`
- [x] `order_schema.py` deleted
- [x] Business `updated_at` preserved on aggregate (set in domain methods)
- [x] All tests pass
