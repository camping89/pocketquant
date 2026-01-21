# PocketQuant

Algorithmic trading platform with real-time market data, WebSocket quotes, and automated bar aggregation.

## Features

- **Historical Data**: Pull OHLCV data from TradingView (up to 5000 bars)
- **Real-time Quotes**: WebSocket connection for live price updates
- **Auto-Aggregation**: Real-time ticks automatically aggregated into OHLCV bars at 13 intervals
- **MongoDB Storage**: Efficient time-series data persistence
- **Redis Cache**: High-performance caching (quotes, bars, queries)
- **Background Jobs**: Scheduled data synchronization (6-hourly + market hours)
- **Structured Logging**: JSON logs compatible with Datadog, Splunk, ELK, CloudWatch, Loki

## Quick Start

**Prerequisites:** Python 3.14+ | Docker & Docker Compose

```bash
# 1. Configure environment (see .env.example for all options)
cp .env.example .env

# 2. Start everything
just start

# Access API at configured API_PORT (default 8765): /api/v1/docs
```

**Daily Commands:**
| Command | Purpose |
|---------|---------|
| `just start` | Start services + app |
| `just stop` | Stop containers |
| `just logs` | View logs |

## Architecture

Vertical Slice Architecture with shared infrastructure (Database, Cache, Logging, Jobs):

```
src/
├── common/              # Shared infrastructure (singletons)
│   ├── database/        # MongoDB (Motor async)
│   ├── cache/           # Redis caching
│   ├── logging/         # Structured JSON logging
│   └── jobs/            # APScheduler wrapper
│
├── features/            # Feature slices
│   └── market_data/     # Market data (2,714 LOC)
│       ├── api/         # FastAPI routes (472 LOC)
│       ├── services/    # Business logic (848 LOC)
│       ├── repositories/ # Data access (428 LOC)
│       ├── models/      # Pydantic models (289 LOC)
│       ├── providers/   # TradingView integrations (572 LOC)
│       └── jobs/        # Background sync (118 LOC)
│
├── main.py              # FastAPI + lifespan
└── config.py            # Settings
```

Total: ~3,600 LOC across 33 Python files.

## API Examples

> **Note:** Examples use default port. Adjust `$API_PORT` per your `.env` config.

### Sync Historical Data

```bash
curl -X POST http://localhost:$API_PORT/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1d", "n_bars": 5000}'
```

### Real-time Quotes

```bash
# Start service
curl -X POST http://localhost:$API_PORT/api/v1/quotes/start

# Subscribe
curl -X POST http://localhost:$API_PORT/api/v1/quotes/subscribe \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ"}'

# Get latest
curl http://localhost:$API_PORT/api/v1/quotes/latest/NASDAQ/AAPL
```

### Query Historical Data

```bash
curl "http://localhost:$API_PORT/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=100"
```

**Full API Docs:** `http://localhost:$API_PORT/api/v1/docs`

## Key Concepts

### Data Pipelines

1. **Historical Sync**: TradingView REST → DataSyncService → MongoDB
   - Single/bulk/background sync
   - 5000 bar limit enforced
   - Status tracking (pending → syncing → completed/error)

2. **Real-time Quotes**: TradingView WebSocket → QuoteService → QuoteAggregator → MongoDB + Redis
   - Binary protocol (custom frame format)
   - Auto-reconnect with exponential backoff
   - Multi-interval aggregation (1m to 1M)

### Infrastructure Patterns

- **Singleton:** Database, Cache, JobScheduler via class methods
- **Repository:** Stateless data access (class methods only)
- **Service:** Per-request (DataSyncService) or singleton (QuoteService)
- **Thread Pool:** TradingView blocking I/O isolation (4 workers)
- **Concurrency:** asyncio.Lock for atomic bar building

### Supported Intervals

1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M

### Background Jobs

- `sync_all_symbols` - Every 6 hours (500 bars)
- `sync_daily_data` - Hourly Mon-Fri 9-17 UTC (10 bars)

## Configuration

All settings via `.env`:

```env
MONGODB_URL=mongodb://localhost:27018
REDIS_URL=redis://localhost:6379
LOG_FORMAT=console          # or "json" for production
LOG_LEVEL=info
ENVIRONMENT=development     # or "production"
TRADINGVIEW_USERNAME=optional_username
TRADINGVIEW_PASSWORD=optional_password
```

## Production Deployment

```bash
# Install
sudo apt install python3.14 docker.io
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup
git clone <repo> && cd pocketquant
cp .env.example .env  # Configure API_PORT, MONGODB_URL, etc.
uv venv && uv pip install -e .
docker compose -f docker/compose.yml up -d

# Run (reads config from .env)
.venv/bin/python -m src.main
```

## Documentation

- **[Architecture Guide](./docs/system-architecture.md)** - Infrastructure, data pipelines, concurrency
- **[Code Standards](./docs/code-standards.md)** - Patterns, testing, code quality
- **[Codebase Summary](./docs/codebase-summary.md)** - Module breakdown, LOC, key decisions
- **[Project Overview](./docs/project-overview-pdr.md)** - Vision, requirements, status
- **[Roadmap](./docs/project-roadmap.md)** - Phases, TODOs, release schedule

## Development

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Commands

```bash
# Run app (config from .env)
python -m src.main

# Infrastructure
docker compose -f docker/compose.yml up -d          # Services
docker compose -f docker/compose.yml --profile admin up -d  # + Mongo UI

# Testing
pytest                                              # All tests
pytest -v --tb=short                               # Verbose
pytest --cov=src --cov-report=term-missing         # Coverage

# Code quality
ruff check .                                        # Lint
ruff format .                                       # Format
mypy src/                                           # Type check
```

## License

MIT
