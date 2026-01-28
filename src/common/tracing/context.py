"""ContextVar for async-safe request ID propagation."""

import contextvars
from uuid import uuid4

request_id_contextvar: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one."""
    correlation_id = request_id_contextvar.get()
    return correlation_id if correlation_id else str(uuid4())


def set_correlation_id(request_id: str) -> contextvars.Token:
    """Set correlation ID in context."""
    return request_id_contextvar.set(request_id)
