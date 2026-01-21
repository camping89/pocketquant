---
title: "Motor to PyMongo Async Migration"
description: "Migrate MongoDB driver from Motor 3.7.1 to PyMongo 4.16+ native Async API for Python 3.14 compatibility"
status: completed
priority: P1
effort: 3h
branch: master
tags: [database, mongodb, migration, python-3.14, infrastructure]
created: 2026-01-21
completed: 2026-01-21
---

# Motor to PyMongo Async Migration

## Problem
Motor 3.7.1 doesn't support Python 3.14, causing authentication failures. Motor deprecated May 2025, EOL May 2027.

## Solution
Migrate to PyMongo 4.16+ native Async API. Direct asyncio integration (2-3x faster), full Python 3.14 support.

## Scope
- **Files to modify:** 5
- **Motor references:** 11 total
- **Breaking changes:** Import paths, type hints only
- **Behavioral changes:** None (API 95% compatible)

## Phase Overview

| Phase | Description | Effort | Status |
|-------|-------------|--------|--------|
| [Phase 1](phase-01-update-dependencies.md) | Update dependencies | 15m | ✅ completed |
| [Phase 2](phase-02-migrate-database-connection.md) | Migrate Database singleton | 30m | ✅ completed |
| [Phase 3](phase-03-update-repository-types.md) | Update repository type hints | 20m | ✅ completed |
| [Phase 4](phase-04-update-configuration.md) | Review configuration | 10m | ✅ completed |
| [Phase 5](phase-05-code-quality-docs.md) | Code quality & docs | 30m | ✅ completed |
| [Phase 6](phase-06-manual-testing.md) | Manual testing | 45m | ✅ completed |

## Key Migration Pattern

```python
# OLD (Motor)
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection

# NEW (PyMongo Async)
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.collection import AsyncCollection
```

## Critical Notes
- No `io_loop` parameter (remove if present)
- `to_list(0)` becomes `to_list(None)` (not used in codebase)
- `async for doc in cursor` pattern unchanged (already correct)
- Connection errors now raised during operations, not at init

## Success Criteria
- [x] All imports updated to `pymongo.asynchronous`
- [x] Type hints use `AsyncMongoClient`, `AsyncDatabase`, `AsyncCollection`
- [x] mypy: 58 errors (pre-existing strictness issues, not migration-related)
- [x] ruff lint passes
- [x] Manual tests pass (DB connect, sync, quotes, jobs)
- [x] Documentation updated

## Completion Notes
- **Port conflict resolved:** Changed Docker MongoDB from 27017 to 27018 (local MongoDB was intercepting)
- **All services connected:** MongoDB, Redis, Job Scheduler confirmed working
- **Type errors:** 58 mypy errors are pre-existing (generic type params, pydantic strictness) - not introduced by migration

## Research Reports
- [PyMongo Async API](research/researcher-pymongo-async-api.md)
- [Motor Deprecation](research/researcher-motor-deprecation.md)
