# CLAUDE.md — PocketQuant

**Last Updated:** 2026-03-21 | **Status:** v1.0 production | **Architecture:** 4-package uv workspace monorepo

## Monorepo Structure

4 packages under `packages/`, sharing `pocketquant.*` namespace:

```
packages/
├── pocketquant-core/       # 0 deps — domain, common, persistence, infra ports
├── pocketquant-backtest/   # → core — backtest engine, optimization, PaperBroker
├── pocketquant-trading/    # → core — live trading, OKX broker, strategy orchestration
└── pocketquant-api/        # → core + backtest + trading — FastAPI, DI, composition root
```

**Dependency graph:** core ← {backtest, trading} ← api

## Package Imports

```python
# Core domain
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.persistence.repositories import BarRepository
from pocketquant.core.infrastructure.brokers import IBroker, PaperBroker, IBrokerFactory
from pocketquant.core.config import Settings

# Backtest
from pocketquant.backtest.domain.entities import BacktestResult, OptimizationResult
from pocketquant.backtest.engine.backtest_app_service import BacktestAppService
from pocketquant.backtest.persistence.backtest_repository import BacktestRepository

# Trading
from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
from pocketquant.trading.app_services.order_app_service import OrderAppService
from pocketquant.trading.brokers.okx.okx_broker import OKXBroker

# API (composition root)
from pocketquant.api.di.container import create_container
from pocketquant.api.di.broker_factory import BrokerFactory
from pocketquant.api.market_data.app_services.bar_app_service import BarAppService
```

## Domain Structure (Three-Tier DDD)

Domain entities live in `pocketquant-core`:
- **Top-level** (collection-backed): `domain/{bar,order,position,symbol,sync_status}/`
- **Concepts** (non-persisted logic): `concepts/{quote,risk,strategy}/`
- **Shared** (cross-cutting): `domain/shared/{enums,events,value_objects}.py`

Backtest domain lives in `pocketquant-backtest/domain/`.

Standard file names per folder: `entities.py`, `events.py`, `value_objects.py`, `enums.py`, `interfaces.py`, `services/`

## DI Container (Dishka)

6 providers in `pocketquant.api.di/`:
- CoreProvider: Settings, EventBus, Mediator
- PersistenceProvider: Database, Cache, repositories
- InfrastructureProvider: BrokerFactory, TradingView, JobScheduler
- MarketDataProvider: BarAppService, QuoteAppService, sync jobs
- TradingProvider: OrderAppService, PositionAppService, StrategyAppService
- HandlerProvider: All CQRS handlers

Routes use `FromDishka[Mediator]` + `DishkaRoute` (NOT `Depends()`)

## Key Architecture Decisions

- **IBrokerFactory protocol** in core — StrategyAppService depends on protocol, BrokerFactory (api) implements it
- **PaperBroker in core** — shared by backtest engine and paper trading mode
- **Backtest repos in backtest package** — `backtest_repository.py`, `optimization_repository.py` live in backtest, not core (avoid circular deps)
- **Namespace packages** — no `__init__.py` at `pocketquant/` level (PEP 420)

## Schema Consolidation

No empty subclasses. Use base classes directly:
- Repository methods work with domain entities directly (Bar.to_mongo(), Bar.from_mongo())

## Known Issues

See `docs/migration-doubts-and-notes.md` for post-migration notes and unresolved questions.
