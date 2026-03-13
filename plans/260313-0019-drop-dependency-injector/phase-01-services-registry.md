# Phase 1: Create Services Registry Dataclass

**Priority:** High | **Status:** Pending | **Effort:** S

## Overview

Replace `AppContainer` with a plain Python `@dataclass` that holds all initialized service instances. This becomes the single source of truth for all dependencies.

## Context Links

- Current container: `src/container.py` (366 LOC)
- Brainstorm decision: Option B — Plain Python + Depends()

## Requirements

- Typed fields for every service (IDE autocomplete, pyright validation)
- No library dependency — stdlib `dataclasses` only
- Group fields by domain (persistence, messaging, market data, trading, strategy, infra)

## Implementation Steps

1. Create `src/services.py` with `Services` dataclass
2. Fields mirror current container providers (exact same types):

```python
# src/services.py
from dataclasses import dataclass
from src.config import Settings
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.common.messaging import EventBus
from src.common.mediator.mediator import Mediator
from src.common.health import HealthCoordinator
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.tradingview import TradingViewProvider
from src.infrastructure.scheduling.scheduler import JobScheduler
from src.application.market_data.bar_manager import BarManager
from src.application.market_data.quote_service import QuoteService
from src.application.trading.order_manager import OrderManager
from src.application.trading.position_tracker import PositionTracker
from src.application.strategy.strategy_engine import StrategyEngine
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository

@dataclass(frozen=True)
class Services:
    """Application service registry. All services initialized at startup."""
    # Config
    settings: Settings

    # Persistence
    database: Database
    cache: Cache

    # Repositories
    order_repository: OrderRepository
    position_repository: PositionRepository
    backtest_repository: BacktestRepository
    ohlcv_repository: OHLCVRepository
    symbol_repository: SymbolRepository
    sync_status_repository: SyncStatusRepository
    optimization_repository: OptimizationRepository

    # Core messaging
    event_bus: EventBus
    mediator: Mediator

    # Infrastructure
    job_scheduler: JobScheduler
    tv_provider: TradingViewProvider
    broker_factory: BrokerFactory
    risk_handler: RiskCheckHandler
    health_coordinator: HealthCoordinator

    # Market data services
    bar_manager: BarManager
    quote_service: QuoteService

    # Trading services (lifecycle-managed)
    order_manager: OrderManager
    position_tracker: PositionTracker
    strategy_engine: StrategyEngine
```

3. Use `frozen=True` — services are immutable after startup (prevents accidental reassignment)

## Todo

- [ ] Create `src/services.py` with Services dataclass
- [ ] Verify all provider types from container.py are covered
- [ ] Run `pyright src/services.py` to check imports

## Success Criteria

- All current container providers have corresponding typed fields
- `pyright` passes with no errors
- No `dependency-injector` imports
