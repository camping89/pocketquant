"""Handler for updating tracked symbol metadata."""

from pocketquant.api.market_data.handlers.tracked_symbols.update.command import (
    UpdateTrackedSymbolCommand,
)
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)


@handles(UpdateTrackedSymbolCommand)
class UpdateTrackedSymbolHandler(Handler[UpdateTrackedSymbolCommand, dict]):
    """Update metadata on an existing tracked symbol. 404 if not found."""

    def __init__(self, tracked_symbol_repository: TrackedSymbolRepository) -> None:
        self._repo = tracked_symbol_repository

    async def handle(self, request: UpdateTrackedSymbolCommand) -> dict:
        # Currently no mutable metadata beyond the composite symbol itself —
        # update is a no-op placeholder that validates existence.
        # Extend fields in command when needed.
        found = await self._repo.update(request.symbol, {})
        if not found:
            raise NotFoundError(
                f"Tracked symbol '{request.symbol}' not found",
                error_code="TRACKED_SYMBOL_NOT_FOUND",
            )
        logger.info("tracked_symbols.updated", symbol=request.symbol)
        return {"symbol": request.symbol, "status": "updated"}
