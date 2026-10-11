"""tracked_symbols feature service — CRUD on the tracked composite-symbol list.

Request DTOs keep their original class names so OpenAPI schema components
stay stable (routes expose them as request bodies).
"""

from pydantic import BaseModel, Field, field_validator

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.time import utc_now
from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_PATTERN
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)


class AddTrackedSymbolCommand(BaseModel):
    """Add composite ``{code}:{exchange}`` symbol to tracked_symbols. Idempotent — 200 if exists."""

    symbol: str = Field(
        ...,
        min_length=3,
        max_length=65,
        description="Composite symbol e.g. BTCUSDT:BINANCE",
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def upper_and_validate(cls, v: str) -> str:
        v = v.strip().upper()
        if not COMPOSITE_SYMBOL_PATTERN.match(v):
            raise ValueError("Must be composite {CODE}:{EXCHANGE} format")
        return v


class TrackedSymbolService:
    """CRUD on tracked_symbols backed by the Mongo repository."""

    def __init__(self, tracked_symbol_repository: TrackedSymbolRepository) -> None:
        self._repo = tracked_symbol_repository

    async def add(self, request: AddTrackedSymbolCommand) -> dict:
        """Upsert composite symbol into tracked_symbols. Returns current state."""
        ts = TrackedSymbol(
            symbol=request.symbol,
            created_at=utc_now(),
            seeded_from="admin",
        )
        await self._repo.upsert(ts)
        logger.info("tracked_symbols.added", symbol=request.symbol)
        return {
            "symbol": ts.symbol,
            "created_at": ts.created_at.isoformat(),
            "seeded_from": ts.seeded_from,
        }

    async def update(self, symbol: str) -> dict:
        # Currently no mutable metadata beyond the composite symbol itself —
        # update is a no-op placeholder that validates existence.
        found = await self._repo.update(symbol, {})
        if not found:
            raise NotFoundError(
                f"Tracked symbol '{symbol}' not found",
                error_code="TRACKED_SYMBOL_NOT_FOUND",
            )
        logger.info("tracked_symbols.updated", symbol=symbol)
        return {"symbol": symbol, "status": "updated"}

    async def remove(self, symbol: str) -> dict:
        """Delete composite symbol from tracked_symbols. 404 if not found."""
        deleted = await self._repo.delete(symbol)
        if not deleted:
            raise NotFoundError(
                f"Tracked symbol '{symbol}' not found",
                error_code="TRACKED_SYMBOL_NOT_FOUND",
            )
        logger.info("tracked_symbols.removed", symbol=symbol)
        return {"symbol": symbol, "status": "removed"}

    async def list_all(self) -> list[dict]:
        """Return all tracked composite symbols."""
        symbols = await self._repo.list_all()
        return [
            {
                "symbol": ts.symbol,
                "created_at": ts.created_at.isoformat(),
                "seeded_from": ts.seeded_from,
            }
            for ts in symbols
        ]
