"""bff DI container factory and handler registration."""

from dishka import AsyncContainer, make_async_container

from pocketquant.bff.di.core import BffCoreProvider
from pocketquant.bff.di.handlers import ALL_BFF_HANDLER_TYPES, BffHandlerProvider
from pocketquant.bff.di.market_data import BffMarketDataProvider
from pocketquant.bff.di.persistence import BffPersistenceProvider
from pocketquant.bff.di.services import BffServiceProvider
from pocketquant.core.common.mediator.handler_registry import HandlerRegistry
from pocketquant.core.common.mediator.mediator import Mediator


def create_bff_container() -> AsyncContainer:
    return make_async_container(
        BffCoreProvider(),
        BffPersistenceProvider(),
        BffMarketDataProvider(),
        BffHandlerProvider(),
        BffServiceProvider(),
    )


async def register_bff_handlers(container: AsyncContainer) -> None:
    """Resolve all bff CQRS handlers and register with Mediator."""
    mediator = await container.get(Mediator)
    registry = HandlerRegistry()
    handlers = [await container.get(ht) for ht in ALL_BFF_HANDLER_TYPES]
    registry.register_all(mediator, handlers)
