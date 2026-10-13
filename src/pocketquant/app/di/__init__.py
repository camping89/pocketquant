"""Dishka DI: three providers (infrastructure, adapters, services).

Adding a new service:
  1. Add a @provide method or a `provide(...)` line in the owning provider
  2. Dishka auto-resolves constructor deps via type hints
  3. Use generator factories (yield) for services needing cleanup

STRICT_VALIDATION rejects a type registered twice, so every type has exactly
one provider.
"""

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


def create_container(settings: Settings | None = None) -> AsyncContainer:
    return make_async_container(
        InfrastructureProvider(),
        AdaptersProvider(),
        ServicesProvider(),
        context={Settings: settings or get_settings()},
        validation_settings=STRICT_VALIDATION,
    )
