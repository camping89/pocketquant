"""Symbol aggregate root."""

from __future__ import annotations

from pydantic import BaseModel, Field, PrivateAttr

from src.common.uuid import UUID, generate_id
from src.domain.shared.domain_event import DomainEvent
from src.domain.symbol.value_objects import SymbolInfo


class SymbolAggregate(BaseModel):
    """Aggregate root for symbol management."""

    id: UUID = Field(default_factory=generate_id)
    info: SymbolInfo | None = None
    _events: list[DomainEvent] = PrivateAttr(default_factory=list)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SymbolAggregate):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    @classmethod
    def create(
        cls,
        code: str,
        exchange: str,
        name: str | None = None,
        asset_type: str | None = None,
    ) -> SymbolAggregate:
        """Factory method to create a new symbol aggregate."""
        info = SymbolInfo(
            code=code.upper(),
            exchange=exchange.upper(),
            name=name,
            asset_type=asset_type,
        )
        return cls(info=info)

    def deactivate(self) -> None:
        """Deactivate the symbol."""
        if self.info:
            self.info = SymbolInfo(
                code=self.info.code,
                exchange=self.info.exchange,
                name=self.info.name,
                asset_type=self.info.asset_type,
                is_active=False,
            )

    def activate(self) -> None:
        """Activate the symbol."""
        if self.info:
            self.info = SymbolInfo(
                code=self.info.code,
                exchange=self.info.exchange,
                name=self.info.name,
                asset_type=self.info.asset_type,
                is_active=True,
            )

    # -- Convenience properties for flat access --

    @property
    def symbol(self) -> str:
        return self.info.code if self.info else ""

    @property
    def exchange(self) -> str:
        return self.info.exchange if self.info else ""

    @property
    def name(self) -> str | None:
        return self.info.name if self.info else None

    @property
    def asset_type(self) -> str | None:
        return self.info.asset_type if self.info else None

    @property
    def is_active(self) -> bool:
        return self.info.is_active if self.info else True

    def get_uncommitted_events(self) -> list[DomainEvent]:
        return self._events.copy()

    def clear_events(self) -> None:
        self._events.clear()
