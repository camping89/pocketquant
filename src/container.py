"""Dishka DI container factory and handler registration.

Adding a new provider:
  1. Create a Provider subclass in src/providers/
  2. Import and add it to PROVIDERS below
  3. Add it to src/providers/__init__.py exports
"""

from dishka import AsyncContainer, make_async_container

from src.common.mediator.handler_registry import HandlerRegistry
from src.common.mediator.mediator import Mediator
from src.providers import (
    CoreProvider,
    HandlerProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
    TradingProvider,
)
from src.providers.handler_provider import ALL_HANDLER_TYPES

# Order matters: later providers may depend on earlier ones.
PROVIDERS = [
    CoreProvider(),
    PersistenceProvider(),
    InfrastructureProvider(),
    MarketDataProvider(),
    TradingProvider(),
    HandlerProvider(),
]


def create_container() -> AsyncContainer:
    """Create the dishka DI container with all providers."""
    return make_async_container(*PROVIDERS)


async def register_handlers(container: AsyncContainer) -> None:
    """Resolve all CQRS handlers from container and register with Mediator."""
    mediator = await container.get(Mediator)
    registry = HandlerRegistry()

    handlers = [await container.get(ht) for ht in ALL_HANDLER_TYPES]
    registry.register_all(mediator, handlers)
