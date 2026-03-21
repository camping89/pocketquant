"""Base domain event class."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from pocketquant.core.common.uuid import UUID, generate_id


@dataclass(frozen=True, eq=False)
class DomainEvent:
    """Base class for all domain events."""

    event_id: UUID = field(default_factory=generate_id)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
