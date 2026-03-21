"""Handler for bulk sync command."""

from pocketquant.core.common.mediator import Handler, handles
from pocketquant.api.market_data.handlers.sync.dto import SyncResponse
from pocketquant.api.market_data.handlers.sync.sync_bulk.command import BulkSyncCommand
from pocketquant.api.market_data.handlers.sync.sync_one.command import SyncSymbolCommand
from pocketquant.api.market_data.handlers.sync.sync_one.handler import SyncSymbolHandler


@handles(BulkSyncCommand)
class BulkSyncHandler(Handler[BulkSyncCommand, list[SyncResponse]]):  # type: ignore[type-arg]
    """Handle syncing multiple symbols."""

    def __init__(self, sync_symbol_handler: SyncSymbolHandler):
        self._sync_symbol_handler = sync_symbol_handler

    async def handle(self, request: BulkSyncCommand) -> list[SyncResponse]:
        results = []
        for sym in request.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=sym["symbol"],
                exchange=sym["exchange"],
                interval=request.interval,
                n_bars=request.n_bars,
            )
            result = await self._sync_symbol_handler.handle(sync_cmd)
            results.append(result)
        return results
