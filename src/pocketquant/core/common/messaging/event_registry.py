"""Event handler decorator and auto-registration."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from pocketquant.core.domain.shared.events import DomainEvent

if TYPE_CHECKING:
    from pocketquant.core.common.messaging.event_bus import EventBus

T = TypeVar("T", bound=Callable)


def event_handler(*event_types: type[DomainEvent]) -> Callable[[T], T]:
    """Decorator to mark a method as an event handler.

    Usage:
        @event_handler(OrderFilledEvent)
        async def _on_order_filled(self, event: OrderFilledEvent) -> None:
            ...

        @event_handler(BarCompletedEvent, QuoteReceivedEvent)
        async def _on_market_event(self, event: DomainEvent) -> None:
            ...
    """

    def decorator(method: T) -> T:
        # Mark method with its event types for inspection
        if not hasattr(method, "_event_types"):
            method._event_types = []  # type: ignore[attr-defined]
        method._event_types.extend(event_types)  # type: ignore[attr-defined]
        return method

    return decorator


class EventRegistry:
    """Registry for auto-discovering and binding event handlers."""

    def __init__(self) -> None:
        self._registered: list[tuple[type[DomainEvent], object, str]] = []

    def register_instance(self, instance: object, event_bus: EventBus) -> int:
        """Register all decorated handlers from an instance.

        Args:
            instance: Object with @event_handler decorated methods
            event_bus: EventBus to subscribe handlers to

        Returns:
            Number of handlers registered
        """
        count = 0
        # Scan instance for methods with _event_types attribute
        for attr_name in dir(instance):
            if attr_name.startswith("_") and not attr_name.startswith("__"):
                try:
                    method = getattr(instance, attr_name)
                    if callable(method) and hasattr(method, "_event_types"):
                        event_types = getattr(method, "_event_types", [])
                        for event_type in event_types:
                            event_bus.subscribe(event_type, method)
                            self._registered.append((event_type, instance, attr_name))
                            count += 1
                except AttributeError:
                    continue
        return count

    def get_registered(self) -> list[tuple[type[DomainEvent], object, str]]:
        """Get list of registered handlers for debugging."""
        return self._registered.copy()

    def clear(self) -> None:
        """Clear registration tracking (for testing)."""
        self._registered.clear()


_registry = EventRegistry()


def get_event_registry() -> EventRegistry:
    """Get the global event registry."""
    return _registry
