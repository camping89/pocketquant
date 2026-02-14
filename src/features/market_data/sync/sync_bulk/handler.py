"""Handler for bulk sync command."""

from src.common.mediator import Handler, handles
from src.features.market_data.sync.dto import SyncResponse
from src.features.market_data.sync.sync_bulk.command import BulkSyncCommand
from src.features.market_data.sync.sync_one.command import SyncSymbolCommand
from src.features.market_data.sync.sync_one.handler import SyncSymbolHandler


@handles(BulkSyncCommand)
class BulkSyncHandler(Handler[BulkSyncCommand, list[SyncResponse]]):  # type: ignore[type-arg]
    """Handle syncing multiple symbols."""

    def __init__(self, sync_handler: SyncSymbolHandler):
        self.sync_handler = sync_handler

    async def handle(self, request: BulkSyncCommand) -> list[SyncResponse]:
        results = []
        for sym in request.symbols:
            sync_cmd = SyncSymbolCommand(
                symbol=sym["symbol"],
                exchange=sym["exchange"],
                interval=request.interval,
                n_bars=request.n_bars,
            )
            result = await self.sync_handler.handle(sync_cmd)
            results.append(result)
        return results
