"""Application service registry — replaces dependency-injector container.

All services are initialized at startup in the lifespan context manager
and stored as a frozen dataclass. Routes access services via FastAPI
Depends() functions in src/dependencies.py.
"""

from dataclasses import dataclass

from src.application.market_data.bar_manager import BarManager
from src.application.market_data.quote_service import QuoteService
from src.application.strategy.strategy_engine import StrategyEngine
from src.application.trading.order_manager import OrderManager
from src.application.trading.position_tracker import PositionTracker
from src.common.health import HealthCoordinator
from src.common.mediator.mediator import Mediator
from src.common.messaging import EventBus
from src.config import Settings
from src.features.risk.check_risk.handler import RiskCheckHandler
from src.infrastructure.brokers import BrokerFactory
from src.infrastructure.scheduling.scheduler import JobScheduler
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.backtest_repository import BacktestRepository
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.optimization_repository import OptimizationRepository
from src.persistence.repositories.order_repository import OrderRepository
from src.persistence.repositories.position_repository import PositionRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository


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
