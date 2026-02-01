"""Symbol value objects."""

from pydantic import BaseModel, ConfigDict, field_validator


class SymbolInfo(BaseModel):
    """Immutable symbol metadata."""

    model_config = ConfigDict(frozen=True)

    code: str
    exchange: str
    name: str | None = None
    asset_type: str | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v:
            raise ValueError("Symbol code is required")
        return v

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, v: str) -> str:
        if not v:
            raise ValueError("Exchange is required")
        return v

    @property
    def symbol_key(self) -> str:
        """Return 'EXCHANGE:SYMBOL' format."""
        return f"{self.exchange}:{self.code}"
