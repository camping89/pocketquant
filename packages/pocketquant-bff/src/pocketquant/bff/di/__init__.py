"""bff DI providers — isolated from app (option C: each package owns its providers)."""

from pocketquant.bff.di.container import create_bff_container, register_bff_handlers
from pocketquant.bff.di.core import BffCoreProvider
from pocketquant.bff.di.handlers import BffHandlerProvider
from pocketquant.bff.di.market_data import BffMarketDataProvider
from pocketquant.bff.di.persistence import BffPersistenceProvider

__all__ = [
    "BffCoreProvider",
    "BffPersistenceProvider",
    "BffMarketDataProvider",
    "BffHandlerProvider",
    "create_bff_container",
    "register_bff_handlers",
]
