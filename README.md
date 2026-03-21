# PocketQuant

Algorithmic trading platform with real-time market data, backtesting, and live trading via OKX.

## Monorepo Structure

4-package [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) — dependency graph: `core ← {backtest, trading} ← api`

```
packages/
├── pocketquant-core/       # Domain, persistence, infra ports (0 sibling deps)
├── pocketquant-backtest/   # Backtest engine, optimization, PaperBroker (→ core)
├── pocketquant-trading/    # Live trading, OKX broker, strategy orchestration (→ core)
└── pocketquant-api/        # FastAPI server, DI container, composition root (→ all)
```

Each package has its own `pyproject.toml`, `src/pocketquant/<name>/`, and `tests/`.

## Prerequisites

| Tool         | Install                                                       |
|--------------|---------------------------------------------------------------|
| Python 3.14+ | [python.org](https://www.python.org/downloads/)              |
| Docker       | [docker.com](https://docker.com/products/docker-desktop)     |
| just         | `cargo install just` or [docs](https://just.systems/man/en/) |
| uv           | `curl -LsSf https://astral.sh/uv/install.sh \| sh`           |

## Quick Start

```bash
cp .env.example .env          # 1. Configure environment
just install                   # 2. Install all packages (uv sync)
just up                        # 3. Start MongoDB + Redis
just dev                       # 4. Run dev server with hot reload
# API docs → http://localhost:41920/api/v1/docs
```

## Commands

```
just install       Create .venv + install all workspace packages
just up            Start Docker (MongoDB 27018 + Redis 6379)
just down          Stop containers
just reset         Stop + delete volumes
just check         Verify environment (Docker, MongoDB, Redis)
just dev           Start dev server (port 41920, hot reload)
just test          Run all tests
just test-pkg core Run tests for a single package
just lint          Ruff lint check
just fmt           Ruff format
just types         Pyright type check
just qa            lint + format + types
```

## Features

- **Historical Data** — Pull bars from TradingView (up to 5000 bars)
- **Real-time Quotes** — WebSocket live price updates + auto bar aggregation
- **Strategy Engine** — Load/run strategies with broker abstraction (YAML config)
- **Backtesting** — Historical replay with parameter grid optimization
- **Paper Trading** — PaperBroker with simulated fills, slippage
- **Live Trading** — OKX WebSocket with order/position management
- **Persistence** — MongoDB time-series (bars, orders, positions) + Redis cache
- **Background Jobs** — Scheduled data sync (6-hourly + market hours)
- **DI Container** — Dishka with 6 providers, CQRS via Mediator

## API Examples

```bash
# Sync historical data
curl -X POST http://localhost:41920/api/v1/market-data/sync \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSD","exchange":"BINANCE","interval":"4h","n_bars":100}'

# Query OHLCV
curl "http://localhost:41920/api/v1/market-data/ohlcv/BINANCE/BTCUSD?interval=4h&limit=10"

# Run backtest
curl -X POST http://localhost:41920/api/v1/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"strategy_id":"ma-cross-btc-5m","symbol":"BTCUSD","exchange":"BINANCE","interval":"4h","start_date":"2025-01-01","end_date":"2026-01-01","initial_capital":10000}'
```

Full API collection: `tests/http/` (Bruno)

## Configuration

All settings via `.env` — see `.env.example` for full list.

## Development

```bash
just install                         # Install (creates .venv via uv sync)
source .venv/bin/activate            # Activate (Windows: .venv\Scripts\activate)
just dev                             # Run server
just test                            # Run tests
just qa                              # Lint + format + type check
```

## Documentation

- [System Architecture](./docs/system-architecture.md)
- [Code Standards](./docs/code-standards.md)
- [Codebase Summary](./docs/codebase-summary.md)
- [Deployment Guide](./docs/deployment-guide.md)
- [Project Overview](./docs/project-overview-pdr.md)

## License

MIT
