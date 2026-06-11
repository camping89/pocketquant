"""bff DI providers — isolated from app (option C: each package owns its providers)."""

from pocketquant.bff.di.container import create_bff_container
from pocketquant.bff.di.core import BffCoreProvider
from pocketquant.bff.di.market_data import BffMarketDataProvider
from pocketquant.bff.di.persistence import BffPersistenceProvider

__all__ = [
    "BffCoreProvider",
    "BffPersistenceProvider",
    "BffMarketDataProvider",
    "create_bff_container",
]
