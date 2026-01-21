# Phase 2: Migrate Database Connection Layer

## Context Links
- [Plan Overview](plan.md)
- [Phase 1: Dependencies](phase-01-update-dependencies.md)
- [connection.py](../../src/common/database/connection.py)
- [PyMongo Async API Docs](https://pymongo.readthedocs.io/en/stable/api/pymongo/asynchronous/)

## Overview
- **Priority:** P1 (blocking)
- **Status:** pending
- **Effort:** 30m
- **Description:** Replace Motor imports with PyMongo Async API in Database singleton

## Key Insights
- `AsyncIOMotorClient` → `AsyncMongoClient`
- `AsyncIOMotorDatabase` → `AsyncDatabase`
- No `io_loop` parameter needed (auto-detects event loop)
- Connection pool settings remain the same (`minPoolSize`, `maxPoolSize`)
- `server_info()` still available for connection verification

## Requirements

### Functional
- Database.connect() establishes MongoDB connection
- Database.get_collection() returns async collection
- Singleton pattern preserved
- Connection pooling maintained (5-50)

### Non-Functional
- Type hints accurate for IDE/mypy
- No behavioral changes to consumers

## Architecture

### Current (Motor)
```python
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

class Database:
    _client: AsyncIOMotorClient | None = None
    _database: AsyncIOMotorDatabase | None = None
```

### Target (PyMongo Async)
```python
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

class Database:
    _client: AsyncMongoClient | None = None
    _database: AsyncDatabase | None = None
```

## Related Code Files

### Files to Modify
| File | Lines | Change Description |
|------|-------|-------------------|
| `src/common/database/connection.py` | 6 | Update import statement |
| `src/common/database/connection.py` | 17-18 | Update type hints |
| `src/common/database/connection.py` | 32-37 | Update client instantiation |
| `src/common/database/connection.py` | 60 | Update return type hint |
| `src/common/database/connection.py` | 87 | Update context manager type |

## Implementation Steps

### Step 1: Update Imports (Line 6)

```python
# BEFORE
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# AFTER
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
```

### Step 2: Update Class Type Hints (Lines 17-18)

```python
# BEFORE
class Database:
    _client: AsyncIOMotorClient | None = None
    _database: AsyncIOMotorDatabase | None = None

# AFTER
class Database:
    _client: AsyncMongoClient | None = None
    _database: AsyncDatabase | None = None
```

### Step 3: Update Client Instantiation (Lines 32-37)

```python
# BEFORE
client = AsyncIOMotorClient(
    str(settings.mongodb_url),
    minPoolSize=settings.mongodb_min_pool_size,
    maxPoolSize=settings.mongodb_max_pool_size,
    serverSelectionTimeoutMS=5000,
)

# AFTER
client = AsyncMongoClient(
    str(settings.mongodb_url),
    minPoolSize=settings.mongodb_min_pool_size,
    maxPoolSize=settings.mongodb_max_pool_size,
    serverSelectionTimeoutMS=5000,
)
```

### Step 4: Update get_database Return Type (Line 60)

```python
# BEFORE
def get_database(cls) -> AsyncIOMotorDatabase:

# AFTER
def get_database(cls) -> AsyncDatabase:
```

### Step 5: Update Context Manager (Line 87)

```python
# BEFORE
async def get_database(settings: Settings) -> AsyncGenerator[AsyncIOMotorDatabase, None]:

# AFTER
async def get_database(settings: Settings) -> AsyncGenerator[AsyncDatabase, None]:
```

### Step 6: Update Module Docstring (Line 1)

```python
# BEFORE
"""MongoDB async connection management using Motor."""

# AFTER
"""MongoDB async connection management using PyMongo Async API."""
```

## Complete Modified File

```python
"""MongoDB async connection management using PyMongo Async API."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from src.common.logging import get_logger
from src.config import Settings

logger = get_logger(__name__)


class Database:
    """MongoDB database connection manager."""

    _client: AsyncMongoClient | None = None
    _database: AsyncDatabase | None = None

    @classmethod
    async def connect(cls, settings: Settings) -> None:
        """Establish MongoDB connection."""
        logger.info(
            "connecting_to_mongodb",
            database=settings.mongodb_database,
        )

        client = AsyncMongoClient(
            str(settings.mongodb_url),
            minPoolSize=settings.mongodb_min_pool_size,
            maxPoolSize=settings.mongodb_max_pool_size,
            serverSelectionTimeoutMS=5000,
        )

        # Verify connection
        try:
            await client.server_info()
            cls._client = client
            cls._database = client[settings.mongodb_database]
            logger.info("mongodb_connected", database=settings.mongodb_database)
        except Exception as e:
            logger.error("mongodb_connection_failed", error=str(e))
            client.close()
            raise

    @classmethod
    async def disconnect(cls) -> None:
        """Close MongoDB connection."""
        if cls._client is not None:
            cls._client.close()
            cls._client = None
            cls._database = None
            logger.info("mongodb_disconnected")

    @classmethod
    def get_database(cls) -> AsyncDatabase:
        """Get the database instance."""
        if cls._database is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls._database

    @classmethod
    def get_collection(cls, name: str):
        """Get a collection from the database."""
        return cls.get_database()[name]


@asynccontextmanager
async def get_database(settings: Settings) -> AsyncGenerator[AsyncDatabase, None]:
    """Context manager for database connection."""
    try:
        await Database.connect(settings)
        yield Database.get_database()
    finally:
        await Database.disconnect()
```

## Todo List
- [ ] Update import statement (Motor → PyMongo Async)
- [ ] Update _client type hint to AsyncMongoClient
- [ ] Update _database type hint to AsyncDatabase
- [ ] Update client instantiation to AsyncMongoClient
- [ ] Update get_database() return type
- [ ] Update context manager return type
- [ ] Update module docstring
- [ ] Run basic import test: `python -c "from src.common.database import Database"`

## Success Criteria
- `from src.common.database import Database` succeeds
- `Database.connect()` establishes connection
- `Database.get_collection()` returns collection
- No Motor imports remain in file
- Type hints accurate for mypy

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Import path wrong | Medium | High | Verify exact path from PyMongo docs |
| server_info() behavior change | Low | Medium | Test connection verification explicitly |
| close() becomes async | Low | Medium | Check PyMongo docs; may need await |

**Note:** In PyMongo 4.16, `close()` is synchronous. No change needed.

## Security Considerations
- Connection string handling unchanged
- Credentials flow through same Settings path
- No new attack surface

## Next Steps
After completion, proceed to [Phase 3: Update Repository Types](phase-03-update-repository-types.md)
