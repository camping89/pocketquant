"""Section 3: Query OHLCV Data
===============================
After syncing data (Section 2), use this to query and inspect stored bars.
Tests the read path: OHLCVRepository.find() and cache behavior.

Prerequisites:
    Run debug-02-sync-btc-4h.py first to have data in DB.

Usage:
    python testscripts/debug-03-query-ohlcv.py
    python testscripts/debug-03-query-ohlcv.py --symbol ETHUSD --interval 1h --limit 20
    python testscripts/debug-03-query-ohlcv.py --start 2026-01-01 --end 2026-02-01
"""

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings
from src.domain.shared.value_objects import Interval
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository


async def main(
    symbol: str, exchange: str, interval: str, limit: int,
    start_date: str | None, end_date: str | None,
) -> None:
    settings = get_settings()

    print("=" * 60)
    print(f"Section 3: Query OHLCV — {exchange}:{symbol} @ {interval}")
    print("=" * 60)

    db = Database()
    await db.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    try:
        repo = OHLCVRepository(db)

        # Parse optional date filters
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        # --- 3a: Count total bars ---
        total = await repo.count(symbol, exchange, Interval(interval))
        print(f"\n[3a] Total bars in DB: {total}")

        if total == 0:
            print("     No data! Run debug-02-sync-btc-4h.py first.")
            return

        # --- 3b: Get latest bar ---
        latest = await repo.get_latest(symbol, exchange, Interval(interval))
        print(f"\n[3b] Latest bar:")
        if latest:
            print(f"     Datetime: {latest.datetime}")
            print(f"     OHLCV:    O={latest.open:.2f} H={latest.high:.2f} L={latest.low:.2f} C={latest.close:.2f} V={latest.volume:.0f}")

        # --- 3c: Query with filters ---
        filter_desc = f"limit={limit}"
        if start_dt:
            filter_desc += f", start={start_date}"
        if end_dt:
            filter_desc += f", end={end_date}"
        print(f"\n[3c] Querying bars ({filter_desc}):")

        bars = await repo.find(
            symbol, exchange, Interval(interval),
            start_date=start_dt, end_date=end_dt, limit=limit,
        )

        if not bars:
            print("     No bars match the filter.")
            return

        print(f"     Returned {len(bars)} bars\n")

        # Print table header
        print(f"     {'Datetime':<22} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
        print("     " + "-" * 76)

        for bar in bars:
            print(
                f"     {str(bar.datetime):<22} "
                f"{bar.open:>10.2f} {bar.high:>10.2f} {bar.low:>10.2f} {bar.close:>10.2f} "
                f"{bar.volume:>12.0f}"
            )

        # --- 3d: Basic stats ---
        closes = [b.close for b in bars]
        volumes = [b.volume for b in bars]
        print(f"\n[3d] Quick stats over {len(bars)} bars:")
        print(f"     Close range: {min(closes):.2f} — {max(closes):.2f}")
        print(f"     Avg volume:  {sum(volumes) / len(volumes):,.0f}")
        print(f"     Date range:  {bars[0].datetime} → {bars[-1].datetime}")

    finally:
        await cache.disconnect()
        await db.disconnect()

    print("\n" + "=" * 60)
    print("Query complete.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug: query OHLCV data")
    parser.add_argument("--symbol", default="BTCUSD")
    parser.add_argument("--exchange", default="BINANCE")
    parser.add_argument("--interval", default="4h")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--start", dest="start_date", default=None, help="e.g. 2026-01-01")
    parser.add_argument("--end", dest="end_date", default=None, help="e.g. 2026-02-01")
    args = parser.parse_args()

    asyncio.run(main(args.symbol, args.exchange, args.interval, args.limit, args.start_date, args.end_date))
