"""Test scheduled sync jobs directly (without APScheduler).

Runs the same functions that the scheduler triggers periodically:
  - _sync_all_symbols: re-syncs all previously tracked symbols (every 6h)
  - _sync_daily_data:  syncs only 1d interval symbols (weekdays 9-17)

Both functions iterate sync_status records and dispatch SyncSymbolCommand
through the mediator for each tracked symbol.

Prerequisites:
    just up
    # Must have synced at least one symbol first (creates sync_status records)

Usage:
    python testscripts/test_sync_jobs.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _bootstrap import bootstrap, teardown

from src.application.market_data.sync_jobs import _sync_all_symbols, _sync_daily_data


async def main() -> None:
    print("=" * 50)
    print("Testing Scheduled Sync Jobs")
    print("=" * 50)

    ctx = await bootstrap()

    try:
        print("\n[1] Testing _sync_daily_data (syncs 1d interval symbols, 10 bars each)...")
        try:
            await _sync_daily_data(ctx.mediator, ctx.sync_status_repo)
            print("    [OK] _sync_daily_data completed")
        except Exception as e:
            print(f"    [WARN] _sync_daily_data error: {e}")

        print("\n[2] Testing _sync_all_symbols (syncs ALL tracked symbols, 500 bars each)...")
        try:
            await _sync_all_symbols(ctx.mediator, ctx.sync_status_repo)
            print("    [OK] _sync_all_symbols completed")
        except Exception as e:
            print(f"    [WARN] _sync_all_symbols error: {e}")

    finally:
        await teardown(ctx)

    print("\n" + "=" * 50)
    print("All job tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
