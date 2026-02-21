"""Section 4: Sync Status & Symbols
=====================================
Check what symbols have been synced, their status, and bar counts.
Useful for understanding which data is available before running strategies.

The sync_status collection tracks every symbol+exchange+interval combo
that has been synced at least once (via API or scheduled jobs).

Prerequisites:
    just up

Usage:
    python testscripts/debug-04-sync-status.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.persistence.mongodb import Database
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository


async def main() -> None:
    settings = get_settings()

    print("=" * 60)
    print("Section 4: Sync Status & Symbols")
    print("=" * 60)

    db = Database()
    await db.connect(settings)

    try:
        symbol_repo = SymbolRepository(db)
        sync_status_repo = SyncStatusRepository(db)

        # --- 4a: All tracked symbols ---
        print("\n[4a] Tracked Symbols (symbol_repository):")
        symbols = await symbol_repo.find_all()
        if not symbols:
            print("     No symbols tracked yet. Run a sync first.")
        else:
            for s in symbols:
                print(f"     {s.exchange}:{s.symbol}  active={s.is_active}  type={s.asset_type}")

        # --- 4b: All sync statuses ---
        print(f"\n[4b] Sync Statuses ({len(symbols)} symbols tracked):")
        statuses = await sync_status_repo.find_all()
        if not statuses:
            print("     No sync records. Run debug-02-sync-btc-4h.py first.")
        else:
            print(f"     {'Symbol':<12} {'Exchange':<10} {'Interval':<10} {'Status':<12} {'Bars':>6} {'Last Bar':<22} {'Error'}")
            print("     " + "-" * 90)
            for s in statuses:
                error = s.error_message[:30] if s.error_message else ""
                last_bar = str(s.last_bar_at)[:19] if s.last_bar_at else "—"
                print(
                    f"     {s.symbol:<12} {s.exchange:<10} {s.interval:<10} "
                    f"{s.status:<12} {s.bar_count or 0:>6} {last_bar:<22} {error}"
                )

        # --- 4c: Summary ---
        if statuses:
            completed = [s for s in statuses if s.status == "completed"]
            errored = [s for s in statuses if s.status == "error"]
            syncing = [s for s in statuses if s.status == "syncing"]
            print(f"\n[4c] Summary:")
            print(f"     Completed: {len(completed)}")
            print(f"     Errored:   {len(errored)}")
            print(f"     Syncing:   {len(syncing)}")
            print(f"     Total:     {len(statuses)} sync records")

    finally:
        await db.disconnect()

    print("\n" + "=" * 60)
    print("Status check complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
