"""Dishka DI providers — one per domain slice.

Adding a new service:
  1. Add a @provide method in the appropriate provider
  2. Dishka auto-resolves constructor deps via type hints
  3. Use generator factories (yield) for services needing cleanup

Adding a new CQRS handler:
  1. Add @handles(RequestType) decorator to your Handler subclass
  2. Add a `provide(YourHandler, scope=Scope.APP)` line in HandlerProvider
"""

from src.di.core import CoreProvider
from src.di.handlers import HandlerProvider
from src.di.infrastructure import InfrastructureProvider
from src.di.market_data import MarketDataProvider
from src.di.persistence import PersistenceProvider
from src.di.trading import TradingProvider

__all__ = [
    "CoreProvider",
    "HandlerProvider",
    "InfrastructureProvider",
    "MarketDataProvider",
    "PersistenceProvider",
    "TradingProvider",
]
