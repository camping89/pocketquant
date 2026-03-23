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
just install                   # 2. Install all packages (uv sync → creates .venv)

# 3. Activate virtual environment
# Unix/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

just up                        # 4. Start MongoDB + Redis
just dev                       # 5. Run dev server with hot reload
(Or can hit F5 to debug the api app - aka entry point of the whole application)
# API docs → http://localhost:41920/api/v1/docs (local dev)
```

## Commands

```
just install       Create .venv + install all workspace packages
just up            Start Docker (MongoDB $MONGO_PORT + Redis $REDIS_PORT)
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

## API

Swagger docs: `http://localhost:41920/api/v1/docs` — HTTP collection: `tests/http/` (Bruno)

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

## Deployment

See [Deployment Guide](./docs/deployment-guide.md) for VPS setup, CI/CD, and port configuration.

## License

MIT
