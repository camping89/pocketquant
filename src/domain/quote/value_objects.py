"""Quote value objects."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Price:
    """Immutable price value."""

    value: float

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("Price must be non-negative")

    def __float__(self) -> float:
        return self.value


@dataclass(frozen=True)
class QuoteTick:
    """Immutable tick data from real-time feed."""

    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None

    def __post_init__(self) -> None:
        if self.price < 0:
            raise ValueError("Price must be non-negative")
        if self.volume is not None and self.volume < 0:
            raise ValueError("Volume must be non-negative")

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.symbol}"
