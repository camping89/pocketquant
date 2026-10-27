import inspect
from collections.abc import Callable
from typing import Any, TypeVar

from pocketquant.core.domain.shared.events import DomainEvent

TEvent = TypeVar("TEvent", bound=DomainEvent)


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type, list[Callable[[Any], Any]]] = {}

    def subscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], Any]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[TEvent], handler: Callable[[TEvent], Any]) -> bool:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def publish(self, event: DomainEvent) -> None:
        """Publish event to all subscribers (FIFO order).

        A raising handler does not stop the others; the first error is re-raised
        after every handler ran. The list is copied because a handler may
        subscribe or unsubscribe while it awaits.
        """
        errors: list[Exception] = []
        for handler in list(self._handlers.get(type(event), [])):
            try:
                result = handler(event)
                if inspect.iscoroutine(result):
                    await result
            except Exception as exc:  # noqa: BLE001 - re-raised below
                errors.append(exc)
        if errors:
            raise errors[0]
