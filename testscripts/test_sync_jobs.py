"""Script to manually test sync jobs without scheduler."""

import asyncio

from src.common.cache import Cache
from src.common.database import Database
from src.common.logging import get_logger, setup_logging
from src.common.mediator import Mediator
from src.common.messaging import EventBus
from src.config import get_settings
from src.features.market_data.jobs.sync_jobs import (
    set_mediator,
    sync_all_symbols,
    sync_daily_data,
)
from src.features.market_data.sync import SyncSymbolCommand, SyncSymbolHandler
from src.infrastructure.tradingview import TradingViewProvider

logger = get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    setup_logging(settings)

    print("=" * 50)
    print("Testing Sync Jobs")
    print("=" * 50)

    await Database.connect(settings)
    await Cache.connect(settings)

    try:
        mediator = Mediator()
        event_bus = EventBus(max_history=100)
        tv_provider = TradingViewProvider(settings)

        sync_handler = SyncSymbolHandler(tv_provider, event_bus)
        mediator.register(SyncSymbolCommand, sync_handler)
        set_mediator(mediator)

        print("\n[1] Testing sync_daily_data job...")
        await sync_daily_data()
        print("[OK] sync_daily_data completed")

        print("\n[2] Testing sync_all_symbols job...")
        await sync_all_symbols()
        print("[OK] sync_all_symbols completed")

    finally:
        await Cache.disconnect()
        await Database.disconnect()

    print("\n" + "=" * 50)
    print("All job tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
