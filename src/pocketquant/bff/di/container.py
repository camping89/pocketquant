"""bff DI container factory."""

from dishka import AsyncContainer, make_async_container

from pocketquant.bff.di.core import BffCoreProvider
from pocketquant.bff.di.market_data import BffMarketDataProvider
from pocketquant.bff.di.persistence import BffPersistenceProvider
from pocketquant.bff.di.services import BffServiceProvider


def create_bff_container() -> AsyncContainer:
    return make_async_container(
        BffCoreProvider(),
        BffPersistenceProvider(),
        BffMarketDataProvider(),
        BffServiceProvider(),
    )
