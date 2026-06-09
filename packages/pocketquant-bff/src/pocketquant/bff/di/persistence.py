"""Database, Cache, and repository providers for bff.

Isolated copy of app PersistenceProvider — bff has no migrations or indexes,
it connects to a schema the headless app has already prepared.
"""

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from pocketquant.core.config import Settings
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.redis import Cache
from pocketquant.infrastructure.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.infrastructure.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.infrastructure.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.infrastructure.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.infrastructure.persistence.repositories.job_history_repository import (
    JobHistoryRepository,
)
from pocketquant.infrastructure.persistence.repositories.optimization_repository import (
    OptimizationRepository,
)
from pocketquant.infrastructure.persistence.repositories.order_repository import OrderRepository
from pocketquant.infrastructure.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.infrastructure.persistence.repositories.symbol_repository import SymbolRepository
from pocketquant.infrastructure.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)
from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)


class BffPersistenceProvider(Provider):
    @provide(scope=Scope.APP)
    async def get_database(self, settings: Settings) -> AsyncIterator[Database]:
        """Connect MongoDB. Disconnect on bff shutdown."""
        database = Database()
        await database.connect(settings)
        yield database
        await database.disconnect()

    @provide(scope=Scope.APP)
    async def get_cache(self, settings: Settings) -> AsyncIterator[Cache]:
        """Connect Redis. Disconnect on bff shutdown."""
        cache = Cache()
        await cache.connect(settings)
        yield cache
        await cache.disconnect()

    # Repositories — auto-resolved via BaseRepository.__init__(database: Database)
    bar_repository = provide(BarRepository, scope=Scope.APP)
    order_repository = provide(OrderRepository, scope=Scope.APP)
    position_repository = provide(PositionRepository, scope=Scope.APP)
    backtest_repository = provide(BacktestRepository, scope=Scope.APP)
    backtest_request_repository = provide(BacktestRequestRepository, scope=Scope.APP)
    backtest_order_repository = provide(BacktestOrderRepository, scope=Scope.APP)
    backtest_trade_repository = provide(BacktestTradeRepository, scope=Scope.APP)
    optimization_repository = provide(OptimizationRepository, scope=Scope.APP)
    symbol_repository = provide(SymbolRepository, scope=Scope.APP)
    sync_status_repository = provide(SyncStatusRepository, scope=Scope.APP)
    job_history_repository = provide(JobHistoryRepository, scope=Scope.APP)
    subscription_repository = provide(SubscriptionRepository, scope=Scope.APP)
    tracked_symbol_repository = provide(TrackedSymbolRepository, scope=Scope.APP)
