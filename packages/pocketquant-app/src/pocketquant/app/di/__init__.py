"""Dishka DI providers — one per domain slice.

Adding a new service:
  1. Add a @provide method in the appropriate provider
  2. Dishka auto-resolves constructor deps via type hints
  3. Use generator factories (yield) for services needing cleanup

Adding a new CQRS handler:
  1. Add @handles(RequestType) decorator to your Handler subclass
  2. Add a `provide(YourHandler, scope=Scope.APP)` line in HandlerProvider
"""

from pocketquant.app.di.backtest_worker import BacktestWorkerProvider
from pocketquant.app.di.core import CoreProvider
from pocketquant.app.di.execution import ExecutionProvider
from pocketquant.app.di.handlers import HandlerProvider
from pocketquant.app.di.infrastructure import InfrastructureProvider
from pocketquant.app.di.market_data import MarketDataProvider
from pocketquant.app.di.persistence import PersistenceProvider

__all__ = [
    "BacktestWorkerProvider",
    "CoreProvider",
    "ExecutionProvider",
    "HandlerProvider",
    "InfrastructureProvider",
    "MarketDataProvider",
    "PersistenceProvider",
]
