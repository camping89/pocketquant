# Core Infrastructure Analysis Report
**Date:** 2026-01-21 | **Analyzed:** PocketQuant core infrastructure

## Executive Summary
PocketQuant uses singleton-based infrastructure with class methods as API. Database, Cache, JobScheduler initialized once during startup, then accessed directly throughout codebase.

## Key Architecture Patterns
### 1. Singleton Pattern (Class-Method Based)
All three core services (Database, Cache, JobScheduler) use class methods exclusively. State in class variables.

### 2. Configuration Management
Pydantic Settings with LRU-cached factory. Loads from .env. Type validation for MongoDsn, RedisDsn.

## Infrastructure Modules

### Database (src/common/database/)
- Driver: Motor (async MongoDB)
- State: _client, _database
- Pool: 5-50 (configurable)
- Methods: connect, disconnect, get_database, get_collection
- Validation: ping() on connect

### Cache (src/common/cache/)
- Driver: redis-py async
- JSON: Auto-serialize/deserialize
- TTL: 3600s default
- Methods: connect, disconnect, get, set, delete, delete_pattern, exists, get_or_set
- Advanced: SCAN for patterns, default=str for dates

### Logging (src/common/logging/)
- Library: structlog
- Formats: JSON (prod), Console (dev)
- Pipeline: context vars, log level, logger name, timestamp, exceptions, app context
- Compatible: Datadog, Splunk, ELK, CloudWatch, Google Cloud, Loki

### Jobs (src/common/jobs/)
- Library: APScheduler (AsyncIOScheduler)
- Storage: In-memory (MemoryJobStore)
- Executor: AsyncIOExecutor
- Defaults: coalesce=True, max_instances=3, grace_time=60s
- Methods: initialize, start, shutdown, add_interval_job, add_cron_job, remove_job, get_jobs, run_job_now

## Startup Sequence (lifespan in main.py)
1. get_settings() - cached
2. setup_logging(settings)
3. await Database.connect(settings)
4. await Cache.connect(settings)
5. JobScheduler.initialize(settings)
6. JobScheduler.start()
7. register_sync_jobs()
8. yield - serve requests
9. JobScheduler.shutdown(wait=True)
10. await Cache.disconnect()
11. await Database.disconnect()

## Usage Patterns
Routes: Database.get_collection, await Cache.get/set
Services: access singletons directly when needed
Repositories: static/class methods only, no instances

## Dependency Structure
config → logging + database + cache + jobs → main → features
No circular dependencies. Clean layering.

## Critical Design Decisions

### Why Singletons?
Expensive connections (DB, Cache) should exist once per app. Class methods avoid DI complexity.

### Why In-Memory Jobs?
Sync jobs non-critical. Acceptable to lose on restart. Reduces dependencies (no Celery/RabbitMQ needed).

### Why No DI?
FastAPI Depends() for routes. Services injected with Settings. Infrastructure accessed as singletons.

### Why JSON Logging?
Required for production log aggregation. Single format everywhere.

## Production Notes
- MongoDB pool: adjust min/max via settings
- Redis: single connection (pooling internal)
- Graceful shutdown waits for jobs
- AsyncIOExecutor on event loop: don't block with heavy work
- Health endpoint: could check DB/Cache connectivity

## Summary Table
Module | Pattern | Deps | Responsibility
Database | Singleton | Motor | Connection lifecycle
Cache | Singleton | redis-py | Caching, TTL
JobScheduler | Singleton | APScheduler | Job scheduling
Config | Singleton | Pydantic | Settings
Logging | Module | structlog | Setup, factory

## Files Analyzed (844 LOC core)
- src/main.py (99)
- src/config.py (59)
- src/common/database/connection.py (92)
- src/common/cache/redis_cache.py (206)
- src/common/logging/setup.py (99)
- src/common/jobs/scheduler.py (265)

## Unresolved Questions
1. Automatic retry if MongoDB/Redis disconnects?
2. Should critical jobs persist across restarts?
3. Infrastructure observability available?
4. How are singletons mocked in tests?
5. Should /health check DB/Cache connectivity?
