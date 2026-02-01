"""Base domain event class."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainEvent(BaseModel):
    """Base class for all domain events."""

    model_config = ConfigDict(frozen=True)

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DomainEvent):
            return NotImplemented
        return self.event_id == other.event_id

    def __hash__(self) -> int:
        return hash(self.event_id)
