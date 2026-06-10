"""Handler for adding a tracked symbol (idempotent upsert)."""

from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.common.time import utc_now
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.execution.market_data.handlers.tracked_symbols.add.command import (
    AddTrackedSymbolCommand,
)

logger = get_logger(__name__)


@handles(AddTrackedSymbolCommand)
class AddTrackedSymbolHandler(Handler[AddTrackedSymbolCommand, dict]):
    """Upsert composite symbol into tracked_symbols. Returns current state."""

    def __init__(self, tracked_symbol_repository: TrackedSymbolRepository) -> None:
        self._repo = tracked_symbol_repository

    async def handle(self, request: AddTrackedSymbolCommand) -> dict:
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
