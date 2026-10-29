from dishka import STRICT_VALIDATION, AsyncContainer, make_async_container

from pocketquant.app.di.adapters import AdaptersProvider
from pocketquant.app.di.infrastructure import InfrastructureProvider
from pocketquant.app.di.services import ServicesProvider
from pocketquant.core.config import Settings, get_settings

__all__ = [
    "AdaptersProvider",
    "InfrastructureProvider",
    "ServicesProvider",
    "create_container",
]


# STRICT_VALIDATION rejects a type registered twice, so every type has exactly one
# provider.
def create_container(settings: Settings | None = None) -> AsyncContainer:
    return make_async_container(
        InfrastructureProvider(),
        AdaptersProvider(),
        ServicesProvider(),
        context={Settings: settings or get_settings()},
        validation_settings=STRICT_VALIDATION,
    )
