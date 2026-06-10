"""Core bff providers: Settings, EventBus, Mediator.

Isolated copy of app CoreProvider — each package declares its own so there is
no cross-import between pocketquant.bff and pocketquant.app.
"""

from dishka import Provider, Scope, provide

from pocketquant.core.common.mediator.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings, get_settings


class BffCoreProvider(Provider):
    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return get_settings()

    @provide(scope=Scope.APP)
    def get_event_bus(self) -> EventBus:
        return EventBus(max_history=100)

    @provide(scope=Scope.APP)
    def get_mediator(self) -> Mediator:
        return Mediator()
