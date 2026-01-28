"""Mediator exceptions."""


class HandlerNotFoundError(Exception):
    """Raised when no handler is registered for a request type."""

    def __init__(self, request_type: type):
        self.request_type = request_type
        super().__init__(f"No handler registered for {request_type.__name__}")
