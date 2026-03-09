"""Symbol value objects."""

from dataclasses import dataclass

from src.domain.shared.value_objects import Symbol


@dataclass(frozen=True)
class SymbolInfo(Symbol):
    """Immutable symbol metadata extending shared Symbol.

    Inherits code/exchange fields and their validators from Symbol.
    Adds name, asset_type, and is_active for full symbol metadata.
    """

    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.code}"
