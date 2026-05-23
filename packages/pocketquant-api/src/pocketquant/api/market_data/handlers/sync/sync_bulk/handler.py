"""Handler for bulk sync command."""

from pocketquant.api.market_data.handlers.sync.dto import SyncResponse
from pocketquant.api.market_data.handlers.sync.sync_bulk.command import BulkSyncCommand
from pocketquant.api.market_data.handlers.sync.sync_one.command import SyncSymbolCommand
from pocketquant.api.market_data.handlers.sync.sync_one.handler import SyncSymbolHandler
from pocketquant.core.common.mediator import Handler, handles
from pocketquant.core.domain.bar.entities import SOURCE_BULK_SYNC


@handles(BulkSyncCommand)
class BulkSyncHandler(Handler[BulkSyncCommand, list[SyncResponse]]):  # type: ignore[type-arg]
    """Handle syncing multiple composite symbols in sequence."""

    def __init__(self, sync_symbol_handler: SyncSymbolHandler):
        self._sync_symbol_handler = sync_symbol_handler

    async def handle(self, request: BulkSyncCommand) -> list[SyncResponse]:
        results = []
        for symbol in request.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=symbol,
                interval=request.interval,
                n_bars=request.n_bars,
                source=SOURCE_BULK_SYNC,
            )
            result = await self._sync_symbol_handler.handle(sync_cmd)
            results.append(result)
        return results
