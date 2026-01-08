# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Infrastructure (MongoDB + Redis)
docker-compose up -d                              # Core services
docker-compose --profile admin up -d              # With Mongo Express UI

# Run application
python -m src.main                                # Direct
uvicorn src.main:app --reload                     # With hot reload

# Testing
pytest                                            # All tests
pytest tests/path/to/test.py::test_name           # Single test
pytest -v --tb=short                              # Verbose, short traceback

# Code quality
ruff check .                                      # Lint
ruff format .                                     # Format
mypy src/                                         # Type check
```

## Architecture

**Vertical Slice Architecture** - Each feature is self-contained with its own API/services/repositories/models.

```
src/
├── common/           # Shared infrastructure (singleton patterns)
│   ├── database/     # Database.get_collection("name") - class-based singleton
│   ├── cache/        # Cache.get/set/delete - class-based singleton
│   ├── logging/      # get_logger(__name__) - structlog JSON logging
│   └── jobs/         # JobScheduler.add_job() - APScheduler wrapper
│
├── features/         # Feature slices
│   └── market_data/
│       ├── api/      # FastAPI routers (routes.py, quote_routes.py)
│       ├── services/ # Business logic (injected with Settings)
│       ├── repositories/ # MongoDB data access (class methods, static)
│       ├── models/   # Pydantic models & DTOs
│       ├── providers/# External integrations (TradingView)
│       └── jobs/     # Background job definitions
│
├── main.py           # FastAPI app with lifespan manager
└── config.py         # Pydantic Settings (env vars from .env)
```

## Key Patterns

**Singleton Infrastructure** - `Database`, `Cache`, `JobScheduler` use class methods, initialized once in app lifespan:
```python
# In routes/services - just call class methods directly
from src.common.database import Database
collection = Database.get_collection("ohlcv")
```

**Repository Pattern** - Static/class methods for data access:
```python
bars = await OHLCVRepository.get_bars(symbol, exchange, interval)
await OHLCVRepository.upsert_many(records)
```

**Service Pattern** - Instantiated with Settings, contains business logic:
```python
service = DataSyncService(get_settings())
result = await service.sync_symbol(symbol, exchange, interval)
```

**Structured Logging** - JSON format for production, console for dev:
```python
from src.common.logging import get_logger
logger = get_logger(__name__)
logger.info("event_name", key=value, another=data)
```

## Data Flow

1. **Historical**: TradingView (tvdatafeed) → DataSyncService → OHLCVRepository → MongoDB
2. **Real-time**: TradingView WebSocket → QuoteService → QuoteAggregator → Redis cache + MongoDB

## Configuration

All settings via environment variables (`.env` file supported):
- `MONGODB_URL` - MongoDB connection string
- `REDIS_URL` - Redis connection string
- `LOG_FORMAT` - `json` (production) or `console` (development)
- `TRADINGVIEW_USERNAME/PASSWORD` - Optional TradingView auth

## Code Style

**Comments** - Only write comments for non-obvious logic. Never write:
- Comments describing what code does (e.g., `# Create user`, `# Return result`, `# Get data`)
- Comments restating method names (e.g., `# Initialize` before `__init__`)
- Comments labeling obvious sections (e.g., `# Startup`, `# Shutdown`, `# Build cache key`)

**DO write comments for:**
- WHY something is done a certain way (e.g., `# Run in thread pool to avoid blocking event loop`)
- Non-obvious constraints (e.g., `# tvdatafeed max is 5000 bars`)
- Warnings about gotchas (e.g., `# Redis SCAN can be slow with many keys`)
- Complex algorithms or business logic that isn't self-evident

**Docstrings** - Keep them minimal:
- Module/class docstrings: Brief description of purpose
- Method docstrings: Only for public APIs with non-obvious behavior
- Skip Args/Returns if types are annotated and names are descriptive

## API Structure

Base URL: `/api/v1`
- `/market-data/*` - Historical OHLCV sync and retrieval
- `/quotes/*` - Real-time quote WebSocket management
- `/system/jobs` - Background job listing
- `/health` - Health check (root level)
- `/api/v1/docs` - OpenAPI documentation
