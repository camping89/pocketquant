"""Dishka DI container factory and handler registration."""

from dishka import AsyncContainer, make_async_container
from pocketquant.api.di import (
    CoreProvider,
    HandlerProvider,
    InfrastructureProvider,
    MarketDataProvider,
    PersistenceProvider,
    TradingProvider,
)
from pocketquant.api.di.handlers import ALL_HANDLER_TYPES
from pocketquant.core.common.mediator.handler_registry import HandlerRegistry
from pocketquant.core.common.mediator.mediator import Mediator

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
