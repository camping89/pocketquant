# CQRS Patterns for Python/FastAPI: Research Report

## Executive Summary

CQRS separates read (queries) and write (commands) responsibilities for independent scaling and clearer code architecture. Direct DB access in services (eliminating repositories) is viable but trades abstraction for simplicity—appropriate for teams prioritizing pragmatism over complex domain models.

---

## 1. CQRS Without Repository Layer

### Direct Service-to-DB Pattern

**Command Services** → MongoDB collection operations directly
**Query Services** → Direct reads from projections or event stores

```python
class CreateOrderCommand:
    async def execute(self, order_data):
        db = Database.get_collection("orders")
        result = await db.insert_one(order_data)
        return result.inserted_id

class GetOrderQuery:
    async def execute(self, order_id):
        db = Database.get_collection("orders")
        return await db.find_one({"_id": order_id})
```

**Mechanism**: Services instantiate database connections via class methods (singletons), eliminating repository abstraction layer.

---

## 2. MongoDB Bulk Operations Best Practices

### Batch Size Strategy
- **Optimal range**: 1,000-5,000 operations per batch (performance plateaus above 5k)
- **Below 1,000**: Degraded performance vs. single ops
- **Memory**: Batch cursors minimize memory footprint for large datasets

### Ordered vs. Unordered
- **Ordered**: Sequential execution, stops on error (slower on sharded clusters)
- **Unordered** (recommended): Parallel execution, continues on errors (50%+ faster on shards)

### Inlined Bulk Pattern
```python
requests = [
    InsertOne({'symbol': s, 'data': d})
    for s, d in data_batch
]
result = collection.bulk_write(requests, ordered=False)
```

**Key insight**: Batch operations reduce network round-trips by 60-80% vs. individual inserts.

---

## 3. Service Layer Without Repository Abstraction

### Structure Evolution

**Traditional**: Route → Service → Repository → DB
**Direct**: Route → Service → DB (class methods)

**Advantages**:
- One less indirection layer
- Simpler for CRUD-heavy operations
- Easier to inline bulk operations

**Disadvantages**:
- No data access abstraction (harder to test with mocks)
- DB logic scattered across services
- Difficult to swap databases later

### Recommended Approach
Keep **command/query service separation** but collapse repository into methods:

```python
class DataSyncService:
    @staticmethod
    async def upsert_many(records):
        db = Database.get_collection("ohlcv")
        ops = [UpdateOne({'_id': r['_id']}, {'$set': r}, upsert=True)
               for r in records]
        return await db.bulk_write(ops, ordered=False)
```

---

## 4. Pros/Cons: Direct DB vs. Repository Pattern

### Direct DB Access (No Repository)

**Pros:**
- Fewer abstractions = less boilerplate
- Faster development for CRUD operations
- Bulk operations inline naturally
- Clearer data flow

**Cons:**
- Testing requires DB or async mocks
- Coupling to MongoDB specifics
- Migration difficult (changing DB vendor)
- Query logic duplicated across services
- No reusable data access patterns

### Repository Pattern

**Pros:**
- Testable (mock repositories easily)
- Database-agnostic abstractions
- Reusable query logic
- Dependency injection friendly

**Cons:**
- Additional layer complexity
- Performance overhead (extra method calls)
- Bulk operations less natural to express
- Over-engineering for simple CRUD

---

## 5. Recommended Hybrid Approach

**For PocketQuant's market data use case:**

1. **Keep direct MongoDB** in services (minimal abstraction)
2. **Separate command/query services** (CQRS principle)
3. **Bulk operations inline** in services (no repository layer needed)
4. **Integration tests** validate actual DB behavior
5. **Keep singleton pattern** for Database, Cache, JobScheduler

```
Commands: CreateBar, UpsertBars (write)
Queries: GetBars, GetSymbols (read)
Direct: Services call Database.get_collection() → bulk_write()
```

---

## Unresolved Questions

- How to handle transaction rollback with bulk operations on upsert failure?
- Should query projections be separate collections or views?
- How deep does CQRS separation go—separate DB connections for read replicas?

---

## Sources

- [GitHub: CQRS Architecture with Python](https://github.com/marcosvs98/cqrs-architecture-with-python)
- [PyMongo Bulk Write Operations](https://pymongo.readthedocs.io/en/4.11/examples/bulk.html)
- [MongoDB Bulk Operations Guide](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [Building Python API with CQRS](https://wawaziphil.medium.com/building-a-python-api-using-cqrs-a-simple-guide-3d584b6ead34)
- [GeeksforGeeks: Python MongoDB bulk_write()](https://www.geeksforgeeks.org/python/python-mongodb-bulk_write/)
