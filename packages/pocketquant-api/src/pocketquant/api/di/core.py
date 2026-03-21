"""Core app-level providers: Settings, EventBus, Mediator.

These are foundational singletons with no async lifecycle — they are
created once at startup and live for the entire app lifetime.
"""

from dishka import Provider, Scope, provide
from pocketquant.core.common.mediator.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings, get_settings


class CoreProvider(Provider):
    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return get_settings()

    @provide(scope=Scope.APP)
    def get_event_bus(self) -> EventBus:
        return EventBus(max_history=100)

    @provide(scope=Scope.APP)
    def get_mediator(self) -> Mediator:
        return Mediator()
