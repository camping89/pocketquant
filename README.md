# PocketQuant

Algorithmic trading platform with backtesting and forward testing capabilities.

## Features

- **Market Data Provider**: Pull OHLCV data from TradingView
- **FastAPI Backend**: Async REST API with OpenAPI documentation
- **MongoDB Storage**: Efficient storage for time-series market data
- **Redis Cache**: Global caching layer for frequently accessed data
- **Background Jobs**: Scheduled data synchronization
- **Structured Logging**: JSON logs compatible with log aggregation services

## Architecture

The project uses **Vertical Slice Architecture** where each feature is self-contained:

```
src/
├── common/                 # Shared infrastructure
│   ├── database/           # MongoDB connection (Motor async driver)
│   ├── cache/              # Redis cache abstraction
│   ├── logging/            # Structured JSON logging
│   └── jobs/               # Background job scheduler (APScheduler)
│
├── features/               # Vertical slices
│   └── market_data/        # Market data feature
│       ├── api/            # FastAPI routes
│       ├── services/       # Business logic
│       ├── repositories/   # Data access layer
│       ├── models/         # Domain models & DTOs
│       ├── jobs/           # Background sync jobs
│       └── providers/      # External data providers (TradingView)
│
├── main.py                 # FastAPI app entry point
└── config.py               # Pydantic settings
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for MongoDB and Redis)

### Setup

1. **Clone and navigate to the project:**
   ```bash
   cd pocketquant
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Start infrastructure:**
   ```bash
   docker-compose up -d
   ```

5. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env as needed
   ```

6. **Run the application:**
   ```bash
   python -m src.main
   # Or with uvicorn directly:
   uvicorn src.main:app --reload
   ```

7. **Access the API:**
   - API Docs: http://localhost:8000/api/v1/docs
   - Health Check: http://localhost:8000/health

## API Endpoints

### Market Data

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/market-data/sync` | POST | Sync data for a symbol |
| `/api/v1/market-data/sync/background` | POST | Trigger background sync |
| `/api/v1/market-data/sync/bulk` | POST | Sync multiple symbols |
| `/api/v1/market-data/ohlcv/{exchange}/{symbol}` | GET | Get OHLCV data |
| `/api/v1/market-data/symbols` | GET | List tracked symbols |
| `/api/v1/market-data/sync-status` | GET | Get all sync statuses |

### Example: Sync Apple Stock Data

```bash
curl -X POST http://localhost:8000/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "AAPL",
    "exchange": "NASDAQ",
    "interval": "1d",
    "n_bars": 5000
  }'
```

### Example: Get OHLCV Data

```bash
curl "http://localhost:8000/api/v1/market-data/ohlcv/NASDAQ/AAPL?interval=1d&limit=100"
```

## TradingView Data

This project uses [tvdatafeed](https://github.com/rongardF/tvdatafeed) for pulling data from TradingView.

### Supported Intervals

| Interval | Code |
|----------|------|
| 1 Minute | `1m` |
| 5 Minutes | `5m` |
| 15 Minutes | `15m` |
| 1 Hour | `1h` |
| 4 Hours | `4h` |
| 1 Day | `1d` |
| 1 Week | `1w` |
| 1 Month | `1M` |

### Authentication (Optional)

For extended access to symbols, add TradingView credentials to `.env`:

```env
TRADINGVIEW_USERNAME=your_username
TRADINGVIEW_PASSWORD=your_password
```

## Logging

Logs are output in JSON format for compatibility with:
- Datadog
- Splunk
- ELK Stack
- AWS CloudWatch
- Google Cloud Logging
- Grafana Loki

For development, set `LOG_FORMAT=console` for human-readable output.

## Development

### Running Tests

```bash
pytest
```

### Linting

```bash
ruff check .
ruff format .
```

### Type Checking

```bash
mypy src/
```

## License

MIT
