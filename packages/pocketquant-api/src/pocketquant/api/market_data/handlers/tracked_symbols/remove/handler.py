"""Handler for removing a tracked symbol."""

from pocketquant.api.market_data.handlers.tracked_symbols.remove.command import (
    RemoveTrackedSymbolCommand,
)
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger(__name__)


@handles(RemoveTrackedSymbolCommand)
class RemoveTrackedSymbolHandler(Handler[RemoveTrackedSymbolCommand, dict]):
    """Delete composite symbol from tracked_symbols. 404 if not found."""

    def __init__(self, tracked_symbol_repository: TrackedSymbolRepository) -> None:
        self._repo = tracked_symbol_repository

    async def handle(self, request: RemoveTrackedSymbolCommand) -> dict:
        deleted = await self._repo.delete(request.symbol)
        if not deleted:
            raise NotFoundError(
                f"Tracked symbol '{request.symbol}' not found",
                error_code="TRACKED_SYMBOL_NOT_FOUND",
            )
        logger.info("tracked_symbols.removed", symbol=request.symbol)
        return {"symbol": request.symbol, "status": "removed"}
