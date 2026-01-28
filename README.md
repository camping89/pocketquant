# PocketQuant

Algorithmic trading platform with real-time market data, WebSocket quotes, and automated bar aggregation.

## Prerequisites

Install these tools first:

| Tool | Install (macOS) | Install (Linux) |
|------|-----------------|-----------------|
| Python 3.14+ | `brew install python@3.14` | `sudo apt install python3.14` |
| Docker | [Docker Desktop](https://docker.com/products/docker-desktop) | `sudo apt install docker.io` |
| just | `brew install just` | `sudo apt install just` |
| uv | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env

# 2. Install dependencies (creates .venv)
just install

# 3. Start everything
just start

# Access API at http://localhost:8765/api/v1/docs
```

**Commands:**
| Command | Purpose |
|---------|---------|
| `just install` | Create .venv + install deps |
| `just start` | Start services + app |
| `just stop` | Stop containers |
| `just logs` | View logs |

## Features

- **Historical Data**: Pull OHLCV data from TradingView (up to 5000 bars)
- **Real-time Quotes**: WebSocket connection for live price updates
- **Auto-Aggregation**: Real-time ticks aggregated into OHLCV bars (1m to 1M)
- **MongoDB Storage**: Efficient time-series data persistence
- **Redis Cache**: High-performance caching
- **Background Jobs**: Scheduled data sync (6-hourly + market hours)
- **Structured Logging**: JSON logs for Datadog, Splunk, ELK, etc.

## Architecture

Vertical Slice Architecture with shared infrastructure:

```
src/
├── common/              # Shared infrastructure (singletons)
│   ├── database/        # MongoDB (Motor async)
│   ├── cache/           # Redis caching
│   ├── logging/         # Structured JSON logging
│   └── jobs/            # APScheduler wrapper
│
├── features/            # Feature slices
│   └── market_data/     # Market data feature
│       ├── api/         # FastAPI routes
│       ├── services/    # Business logic
│       ├── repositories/ # Data access
│       ├── models/      # Pydantic models
│       ├── providers/   # TradingView integrations
│       └── jobs/        # Background sync
│
├── main.py              # FastAPI + lifespan
└── config.py            # Settings
```

## API Examples

> Adjust port per your `.env` config (default: 8765)

```bash
# Sync historical data
curl -X POST http://localhost:8765/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1d", "n_bars": 5000}'

# Start real-time quotes
curl -X POST http://localhost:8765/api/v1/quotes/start

# Subscribe to symbol
curl -X POST http://localhost:8765/api/v1/quotes/subscribe \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ"}'

# Get latest quote
curl http://localhost:8765/api/v1/quotes/latest/NASDAQ/AAPL

# Query historical data
curl "http://localhost:8765/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=100"
```

**Full API Docs:** `http://localhost:8765/api/v1/docs`

## Configuration

All settings via `.env`:

```env
MONGODB_URL=mongodb://localhost:27018
REDIS_URL=redis://localhost:6379
LOG_FORMAT=console          # or "json" for production
LOG_LEVEL=info
ENVIRONMENT=development     # or "production"
TRADINGVIEW_USERNAME=optional
TRADINGVIEW_PASSWORD=optional
```

## Development

```bash
# Setup
just install
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Run with hot reload
uvicorn src.main:app --reload

# Testing
pytest                      # All tests
pytest -v --tb=short        # Verbose

# Code quality
ruff check .                # Lint
ruff format .               # Format
mypy src/                   # Type check
```

## Documentation

- **[Deployment Guide](./docs/deployment-guide.md)** - Production setup, systemd, health checks
- **[Architecture Guide](./docs/system-architecture.md)** - Infrastructure, data pipelines
- **[Code Standards](./docs/code-standards.md)** - Patterns, testing, code quality
- **[Codebase Summary](./docs/codebase-summary.md)** - Module breakdown, key decisions
- **[Project Overview](./docs/project-overview-pdr.md)** - Vision, requirements, status

## License

MIT
