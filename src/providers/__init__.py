"""Dishka DI providers — one per domain slice.

Adding a new service:
  1. Add a @provide method in the appropriate provider
  2. Dishka auto-resolves constructor deps via type hints
  3. Use generator factories (yield) for services needing cleanup

Adding a new CQRS handler:
  1. Add @handles(RequestType) decorator to your Handler subclass
  2. Add a `provide(YourHandler, scope=Scope.APP)` line in HandlerProvider
"""

from src.providers.core_provider import CoreProvider
from src.providers.handler_provider import HandlerProvider
from src.providers.infrastructure_provider import InfrastructureProvider
from src.providers.market_data_provider import MarketDataProvider
from src.providers.persistence_provider import PersistenceProvider
from src.providers.trading_provider import TradingProvider

__all__ = [
    "CoreProvider",
    "HandlerProvider",
    "InfrastructureProvider",
    "MarketDataProvider",
    "PersistenceProvider",
    "TradingProvider",
]
