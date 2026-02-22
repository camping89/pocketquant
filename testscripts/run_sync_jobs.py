"""Manually trigger scheduled sync jobs without waiting for APScheduler.

These jobs (_sync_all_symbols, _sync_daily_data) normally fire on cron/interval
and are NOT exposed via REST API. This is the only way to invoke them on-demand
for debugging or verifying sync logic after changes.

Requires: `just up` + at least one previously synced symbol.

Usage:
    python testscripts/run_sync_jobs.py
"""

import asyncio
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.market_data.sync_jobs import _sync_all_symbols, _sync_daily_data
from src.container import AppContainer, register_all_handlers


async def main() -> None:
    print("=" * 50)
    print("Triggering Scheduled Sync Jobs")
    print("=" * 50)

    # Wire up via the app's DI container (DB, cache, repos, handlers)
    container = AppContainer()
    await container.init_resources()
    register_all_handlers(container)

    mediator = container.mediator()
    sync_status_repo = container.sync_status_repository()

    try:
        print("\n[1] _sync_daily_data (1d interval symbols, 10 bars each)...")
        try:
            await _sync_daily_data(mediator, sync_status_repo)
            print("    [OK] completed")
        except Exception as e:
            print(f"    [WARN] {e}")

        print("\n[2] _sync_all_symbols (ALL tracked symbols, 500 bars each)...")
        try:
            await _sync_all_symbols(mediator, sync_status_repo)
            print("    [OK] completed")
        except Exception as e:
            print(f"    [WARN] {e}")

    finally:
        await container.shutdown_resources()

    print("\n" + "=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
