"""Event handler type definition."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.domain.shared.domain_event import DomainEvent

T = TypeVar("T", bound=DomainEvent)

EventHandler = Callable[[T], Awaitable[None] | None]
"""Type alias for event handlers - can be sync or async."""
