"""Handler auto-discovery decorator and registry for CQRS mediator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator.handler import Handler

if TYPE_CHECKING:
    from pocketquant.core.common.mediator.mediator import Mediator

logger = get_logger(__name__)

# Attribute name stored on decorated handler classes
_HANDLES_ATTR = "_handles_request_type"


def handles(request_type: type) -> Any:
    """Class decorator to mark a Handler with the request type it handles.

    Usage:
        @handles(SyncSymbolCommand)
        class SyncSymbolHandler(Handler[SyncSymbolCommand, SyncResponse]):
            ...
    """

    def decorator(cls: type) -> type:
        if not (isinstance(cls, type) and issubclass(cls, Handler)):
            raise TypeError(f"@handles can only decorate Handler subclasses, got {cls}")
        setattr(cls, _HANDLES_ATTR, request_type)
        return cls

    return decorator


def get_request_type(handler: Handler) -> type | None:
    """Read the request type from a @handles-decorated handler instance."""
    return getattr(type(handler), _HANDLES_ATTR, None)


class HandlerRegistry:
    """Registry for auto-discovering and registering CQRS handlers."""

    def register_all(self, mediator: Mediator, handlers: list[Handler]) -> int:
        """Register all @handles-decorated handlers with mediator.

        Reads _handles_request_type from each handler class.
        Mediator.register() enforces one-handler-per-request-type rule.

        Returns:
            Number of handlers registered.
        """
        count = 0
        for handler in handlers:
            request_type = get_request_type(handler)
            if request_type is None:
                raise TypeError(f"{type(handler).__name__} is not decorated with @handles")
            mediator.register(request_type, handler)
            count += 1

        logger.info("handlers_registered", count=count)
        return count
