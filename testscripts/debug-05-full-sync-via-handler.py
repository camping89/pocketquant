"""Section 5: Full Sync via Handler (CQRS Pipeline)
=====================================================
Runs the sync through the full CQRS pipeline (Command → Mediator → Handler)
exactly like the API endpoint does. Useful for debugging the handler chain
without starting the HTTP server.

Pipeline:
    SyncSymbolCommand → Mediator.send() → SyncSymbolHandler.handle()
      → TradingViewProvider.fetch_ohlcv()
      → OHLCVRepository.upsert_many()
      → SymbolRepository.upsert()
      → SyncStatusRepository.upsert()
      → Cache invalidation
      → EventBus.publish_all(HistoricalDataSyncedEvent)

Compare with Section 2 which calls provider + repo directly (step-by-step).

Prerequisites:
    just up

Usage:
    python testscripts/debug-05-full-sync-via-handler.py
    python testscripts/debug-05-full-sync-via-handler.py --symbol ETHUSD --interval 1h --bars 50
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _bootstrap import bootstrap, teardown

from src.domain.shared.value_objects import Interval
from src.features.market_data.sync import SyncSymbolCommand


async def main(symbol: str, exchange: str, interval: str, n_bars: int) -> None:
    print("=" * 60)
    print(f"Section 5: Full Sync via CQRS — {symbol} {interval}")
    print("=" * 60)

    ctx = await bootstrap()

    try:
        # Build command (same as what the API route creates from request body)
        cmd = SyncSymbolCommand(
            symbol=symbol,
            exchange=exchange,
            interval=Interval(interval),
            n_bars=n_bars,
        )
        print(f"\n[1] Sending command: {cmd}")
        print("    Mediator → SyncSymbolHandler.handle()")

        # Dispatch through mediator (full CQRS path)
        result = await ctx.mediator.send(cmd)

        # SyncResponse fields
        print(f"\n[2] Result:")
        print(f"    Status:      {result.status}")
        print(f"    Bars synced: {result.bars_synced}")
        print(f"    Total bars:  {result.total_bars}")
        print(f"    Last bar at: {result.last_bar_at}")
        if result.message:
            print(f"    Message:     {result.message}")

        # Check events published
        print(f"\n[3] Domain events published: {len(ctx.event_bus.history)}")
        for event in ctx.event_bus.history:
            print(f"    - {type(event).__name__}: {event}")

    finally:
        await teardown(ctx)

    print("\n" + "=" * 60)
    print("Full sync pipeline complete.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug: full CQRS sync pipeline")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--exchange", default="BINANCE")
    parser.add_argument("--interval", default="4h")
    parser.add_argument("--bars", type=int, default=100)
    args = parser.parse_args()

    asyncio.run(main(args.symbol, args.exchange, args.interval, args.bars))
