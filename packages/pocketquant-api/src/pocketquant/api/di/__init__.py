"""Dishka DI providers — one per domain slice.

Adding a new service:
  1. Add a @provide method in the appropriate provider
  2. Dishka auto-resolves constructor deps via type hints
  3. Use generator factories (yield) for services needing cleanup

Adding a new CQRS handler:
  1. Add @handles(RequestType) decorator to your Handler subclass
  2. Add a `provide(YourHandler, scope=Scope.APP)` line in HandlerProvider
"""

from pocketquant.api.di.core import CoreProvider
from pocketquant.api.di.handlers import HandlerProvider
from pocketquant.api.di.infrastructure import InfrastructureProvider
from pocketquant.api.di.market_data import MarketDataProvider
from pocketquant.api.di.persistence import PersistenceProvider
from pocketquant.api.di.trading import TradingProvider

__all__ = [
    "CoreProvider",
    "HandlerProvider",
    "InfrastructureProvider",
    "MarketDataProvider",
    "PersistenceProvider",
    "TradingProvider",
]
