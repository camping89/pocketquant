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
- **Strategy Engine**: Load and run trading strategies with broker abstraction
- **Backtesting**: Full backtest engine with historical replay and parameter optimization
- **Paper Trading**: Simulate trades with PaperBroker (slippage, fill delays)
- **Live Trading**: OKX WebSocket integration with order/position management
- **MongoDB Storage**: Efficient time-series data persistence
- **Redis Cache**: High-performance caching
- **Background Jobs**: Scheduled data sync (6-hourly + market hours)
- **Structured Logging**: JSON logs for Datadog, Splunk, ELK, etc.

## Architecture (DDD + CQRS + Vertical Slice)

**12,420 LOC across 180 Python files:**

```
src/
├── common/              (700 LOC)   - Mediator, EventBus, middleware, singletons
├── domain/              (1,674 LOC) - Pure business logic (zero I/O)
├── infrastructure/      (3,127 LOC) - Brokers, persistence, providers, scheduling
└── features/            (6,561 LOC) - Vertical slices: market_data, backtesting,
    │                                  strategy, trading, risk
    ├── backtesting/     (2,259 LOC) - BacktestRunner, GridOptimizer
    ├── market_data/     (2,116 LOC) - BarManager, sync, quotes
    ├── strategy/        (1,236 LOC) - StrategyEngine, IStrategy interface
    ├── trading/         (782 LOC)   - OrderManager, PositionTracker
    └── risk/            (163 LOC)   - RiskCheckHandler
```

## API Examples

> Adjust port per your `.env` config (default: 8765)

```bash
# Market Data - Sync historical data
curl -X POST http://localhost:8765/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL", "exchange": "NASDAQ", "interval": "1d", "n_bars": 500}'

# Real-time Quotes - Start WebSocket stream
curl -X POST http://localhost:8765/api/v1/quotes/start

# Backtesting - Run backtest
curl -X POST http://localhost:8765/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"strategy_name": "ma_crossover", "symbol": "AAPL", "start_date": "2024-01-01", "end_date": "2025-01-01"}'

# Strategy - Load and start strategy
curl -X POST http://localhost:8765/api/v1/strategies/load \
  -H "Content-Type: application/json" \
  -d '{"name": "ma_crossover", "config_path": "strategies/ma_crossover.yaml"}'

# Trading - Get open orders
curl http://localhost:8765/api/v1/orders

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
