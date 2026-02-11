# UUID Versions Guide

Comprehensive guide to UUID versions for Python developers working with trading systems.

## UUID Versions Comparison Table

| Version | Generation Method | Sortability | Use Case | Performance |
|---------|------------------|-------------|----------|-------------|
| UUID v1 | Timestamp + MAC | Time-sorted | Legacy systems | Medium |
| UUID v4 | Random | No order | General purpose | Fast |
| UUID v6 | Reordered v1 | Time-sorted | Modern replacement for v1 | Medium |
| UUID v7 | Unix timestamp + random | Time-sorted | **Recommended for DBs** | Best |
| UUID v8 | Custom | Depends | Specialized needs | Varies |

## When to Use Each Version

### UUID v7 (Recommended for Most Cases)
- **Primary keys** in PostgreSQL/MySQL
- **Order IDs** in trading systems
- **Transaction logs** requiring chronological sorting
- **Event sourcing** with time-based ordering

### UUID v4 (Good for Non-Sequential Data)
- **API keys** and tokens
- **Session identifiers**
- **Cache keys** where ordering doesn't matter
- **Public-facing IDs** (prevents enumeration attacks)

### UUID v1/v6 (Legacy/Specialized)
- **Legacy system compatibility**
- When MAC address tracking is acceptable
- v6 is better than v1 for database performance

### UUID v8 (Custom Requirements)
- **Domain-specific** encoding needs
- **Custom timestamp** formats
- **Embedded metadata** in UUIDs

## Python 3.14 UUID Module

Python 3.14 adds native `uuid7()` support:

```python
import uuid
from datetime import datetime

# Generate UUID v7 (time-ordered)
order_id = uuid.uuid7()
print(f"Order ID: {order_id}")
# Output: Order ID: 018e5e5e-8b5a-7000-8000-0123456789ab

# Generate multiple UUIDs - notice they're sequential
trade_ids = [uuid.uuid7() for _ in range(3)]
for tid in trade_ids:
    print(tid)
# 018e5e5e-8b5a-7001-8000-abcdef123456
# 018e5e5e-8b5a-7002-8000-fedcba987654
# 018e5e5e-8b5a-7003-8000-112233445566

# UUID v4 for comparison (random)
session_id = uuid.uuid4()
print(f"Session: {session_id}")
```

## Trading System Examples

### Order Management System

```python
from uuid import uuid7, uuid4
from datetime import datetime
from pydantic import BaseModel, Field

class Order(BaseModel):
    """Trading order with UUID v7 for time-based sorting."""
    order_id: uuid.UUID = Field(default_factory=uuid7)  # Time-ordered
    session_id: uuid.UUID = Field(default_factory=uuid4)  # Random
    symbol: str
    quantity: int
    price: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Create orders
orders = [
    Order(symbol="AAPL", quantity=100, price=150.25),
    Order(symbol="MSFT", quantity=50, price=380.50),
    Order(symbol="GOOGL", quantity=25, price=2800.75),
]

# Orders are naturally sorted by order_id (UUID v7)
for order in orders:
    print(f"{order.order_id} | {order.symbol} | {order.timestamp}")
```

### Event Store Implementation

```python
import uuid
from typing import Any
from datetime import datetime

class TradingEvent:
    """Event with UUID v7 for chronological ordering."""

    def __init__(self, event_type: str, data: dict[str, Any]):
        self.event_id = uuid.uuid7()  # Time-ordered
        self.event_type = event_type
        self.data = data
        self.timestamp = datetime.utcnow()

    def __lt__(self, other):
        """Enable sorting by event_id (naturally time-ordered)."""
        return self.event_id < other.event_id

# Create events
events = [
    TradingEvent("OrderPlaced", {"symbol": "AAPL", "qty": 100}),
    TradingEvent("OrderFilled", {"symbol": "AAPL", "qty": 50}),
    TradingEvent("OrderCancelled", {"symbol": "AAPL", "qty": 50}),
]

# Events are naturally sorted
sorted_events = sorted(events)
for event in sorted_events:
    print(f"{event.event_id} | {event.event_type}")
```

## Database B-tree Performance

### Why UUID v7 Outperforms v4

**UUID v4 (Random):**
- Inserts cause random B-tree splits
- Poor cache locality
- Index fragmentation over time
- Slower INSERT performance

**UUID v7 (Time-ordered):**
- Inserts append to B-tree (mostly)
- Better cache locality
- Minimal fragmentation
- Faster INSERT performance (~30-50% improvement)

### PostgreSQL Example

```sql
-- Bad: UUID v4 causes random inserts
CREATE TABLE orders_v4 (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- Random
    symbol VARCHAR(10),
    quantity INTEGER
);

-- Good: UUID v7 maintains insertion order
CREATE TABLE orders_v7 (
    order_id UUID PRIMARY KEY,  -- Use uuid7() from Python
    symbol VARCHAR(10),
    quantity INTEGER
);

-- Index efficiency comparison
EXPLAIN ANALYZE SELECT * FROM orders_v7
WHERE order_id > '018e5e5e-8b5a-7000-8000-000000000000';
-- Sequential scan benefits from clustering
```

## ULID Comparison

**ULID (Universally Unique Lexicographically Sortable Identifier):**

```python
# ULID example (requires: pip install python-ulid)
from ulid import ULID

# Similar to UUID v7 but with different encoding
trade_id = ULID()
print(trade_id)  # 01ARZ3NDEKTSV4RRFFQ69G5FAV

# UUID v7 equivalent
import uuid
order_id = uuid.uuid7()
print(order_id)  # 018e5e5e-8b5a-7000-8000-0123456789ab
```

**Comparison:**

| Feature | UUID v7 | ULID |
|---------|---------|------|
| Standard | RFC 9562 | Informal spec |
| Length | 36 chars (with hyphens) | 26 chars |
| Sortable | Yes | Yes |
| Python stdlib | 3.14+ | Requires library |
| Database support | Native | Convert to UUID |

**Recommendation:** Use UUID v7 for native PostgreSQL/Python compatibility.

## Best Practices for Trading Systems

1. **Use UUID v7 for:**
   - Order IDs
   - Trade IDs
   - Transaction logs
   - Audit trails
   - Any time-series data

2. **Use UUID v4 for:**
   - API keys
   - Session tokens
   - Cache keys
   - User-facing reference numbers

3. **Database indexing:**
   ```python
   # Always index UUID v7 primary keys
   # PostgreSQL automatically creates B-tree index on PRIMARY KEY
   # Additional indexes for foreign keys
   ```

4. **Avoid mixing UUID versions** in the same table/column for consistency.

5. **Consider timestamp extraction** from UUID v7 for analytics:
   ```python
   import uuid

   order_id = uuid.uuid7()
   # Extract timestamp (first 48 bits)
   timestamp_ms = (order_id.int >> 80) & ((1 << 48) - 1)
   print(f"Timestamp (ms): {timestamp_ms}")
   ```

## Migration Strategy

```python
# Migrating from UUID v4 to UUID v7
from uuid import uuid4, uuid7

# Old code
old_order_id = uuid4()

# New code
new_order_id = uuid7()

# Database migration script
"""
-- Add new column
ALTER TABLE orders ADD COLUMN order_id_v7 UUID;

-- Populate with new UUIDs
UPDATE orders SET order_id_v7 = generate_uuid_v7();  -- Custom function

-- Swap columns (in transaction)
BEGIN;
ALTER TABLE orders DROP CONSTRAINT orders_pkey;
ALTER TABLE orders DROP COLUMN order_id;
ALTER TABLE orders RENAME COLUMN order_id_v7 TO order_id;
ALTER TABLE orders ADD PRIMARY KEY (order_id);
COMMIT;
"""
```

## References

- [RFC 9562: UUID Version 7](https://www.rfc-editor.org/rfc/rfc9562.html)
- [Python 3.14 UUID Documentation](https://docs.python.org/3.14/library/uuid.html)
- [PostgreSQL UUID Performance](https://www.postgresql.org/docs/current/datatype-uuid.html)
