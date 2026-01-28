"""Symbol value objects."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolInfo:
    """Immutable symbol metadata."""

    code: str
    exchange: str
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("Symbol code is required")
        if not self.exchange:
            raise ValueError("Exchange is required")

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.code}"
