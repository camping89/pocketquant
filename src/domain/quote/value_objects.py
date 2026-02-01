"""Quote value objects."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class Price(BaseModel):
    """Immutable price value."""

    model_config = ConfigDict(frozen=True)

    value: float

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    def __float__(self) -> float:
        return self.value


class QuoteTick(BaseModel):
    """Immutable tick data from real-time feed."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    exchange: str
    timestamp: datetime
    price: float
    volume: float | None = None
    bid: float | None = None
    ask: float | None = None

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Price must be non-negative")
        return v

    @field_validator("volume")
    @classmethod
    def validate_volume(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Volume must be non-negative")
        return v

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.symbol}"
