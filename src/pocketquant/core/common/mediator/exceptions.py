"""Mediator exceptions."""


class HandlerNotFoundError(Exception):
    """Raised when no handler is registered for a request type."""

    def __init__(self, request_type: type):
        self.request_type = request_type
        super().__init__(f"No handler registered for {request_type.__name__}")


class DuplicateHandlerError(Exception):
    """Raised when two handlers register for the same command/query."""

    def __init__(self, request_type: type, existing_handler: type, new_handler: type):
        self.request_type = request_type
        super().__init__(
            f"Duplicate handler for {request_type.__name__}: "
            f"{existing_handler.__name__} already registered, "
            f"cannot register {new_handler.__name__}"
        )
