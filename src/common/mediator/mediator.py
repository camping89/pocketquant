"""CQRS Mediator - routes requests to registered handlers."""

from typing import Any

from src.common.mediator.exceptions import HandlerNotFoundError
from src.common.mediator.handler import Handler


class Mediator:
    """CQRS dispatcher - routes requests to handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type, Handler] = {}

    def register(self, request_type: type, handler: Handler) -> None:
        """Register a handler for a request type."""
        self._handlers[request_type] = handler

    def register_handler(self, handler: Handler, request_type: type) -> None:
        """Register a handler for a request type (alternative signature)."""
        self._handlers[request_type] = handler

    async def send(self, request: Any) -> Any:
        """Dispatch request to registered handler."""
        handler = self._handlers.get(type(request))
        if not handler:
            raise HandlerNotFoundError(type(request))
        return await handler.handle(request)

    def get_registered_types(self) -> list[type]:
        """List all registered request types (for debugging)."""
        return list(self._handlers.keys())

    def has_handler(self, request_type: type) -> bool:
        """Check if a handler is registered for a request type."""
        return request_type in self._handlers
