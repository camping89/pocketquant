"""Section 2: Sync BTC 4H Bars
================================
The main debugging target. Syncs BTC 4-hour bars from TradingView
and shows each step of the pipeline with detailed output.

Pipeline: SyncSymbolCommand → SyncSymbolHandler
  → TradingViewProvider.fetch_ohlcv()  (pulls from TradingView)
  → OHLCVRepository.upsert_many()     (stores in MongoDB)
  → SyncStatusRepository.upsert()     (tracks sync state)
  → Cache invalidation                (clears stale Redis keys)
  → EventBus publish                  (domain events)

Prerequisites:
    just up                            # MongoDB + Redis running
    python testscripts/debug-01-infra-health.py  # verify infra first

Usage:
    python testscripts/debug-02-sync-btc-4h.py
    python testscripts/debug-02-sync-btc-4h.py --symbol ETHUSD --exchange BINANCE
    python testscripts/debug-02-sync-btc-4h.py --interval 1d --bars 50
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.common.logging import get_logger, setup_logging
from src.config import get_settings
from src.domain.shared.value_objects import Interval
from src.features.market_data.sync import SyncSymbolCommand
from src.infrastructure.tradingview import TradingViewProvider
from src.persistence.mongodb import Database
from src.persistence.redis import Cache
from src.persistence.repositories.ohlcv_repository import OHLCVRepository
from src.persistence.repositories.symbol_repository import SymbolRepository
from src.persistence.repositories.sync_status_repository import SyncStatusRepository

logger = get_logger(__name__)


async def main(symbol: str, exchange: str, interval: str, n_bars: int) -> None:
    settings = get_settings()
    setup_logging(settings)

    print("=" * 60)
    print(f"Section 2: Sync {symbol} {interval} from {exchange}")
    print("=" * 60)

    db = Database()
    await db.connect(settings)
    cache = Cache()
    await cache.connect(settings)

    try:
        ohlcv_repo = OHLCVRepository(db)
        symbol_repo = SymbolRepository(db)
        sync_status_repo = SyncStatusRepository(db)

        # --- Step 1: Check current state BEFORE sync ---
        print("\n[Step 1] Current state before sync")
        existing_count = await ohlcv_repo.count(symbol, exchange, Interval(interval))
        latest = await ohlcv_repo.get_latest(symbol, exchange, Interval(interval))
        status = await sync_status_repo.find_one(symbol, exchange, Interval(interval))

        print(f"  Existing bars in DB: {existing_count}")
        print(f"  Latest bar datetime: {latest.datetime if latest else 'None'}")
        print(f"  Sync status record:  {status.status if status else 'None (never synced)'}")

        # --- Step 2: Test TradingView provider directly ---
        print(f"\n[Step 2] Fetching from TradingView provider...")
        print(f"  Symbol:   {symbol}")
        print(f"  Exchange: {exchange}")
        print(f"  Interval: {interval}")
        print(f"  N bars:   {n_bars}")

        tv_provider = TradingViewProvider(settings)
        records = await tv_provider.fetch_ohlcv(
            symbol=symbol,
            exchange=exchange,
            interval=Interval(interval),
            n_bars=n_bars,
        )

        if not records:
            print("  [FAIL] No data returned! Check symbol/exchange/interval combo.")
            print("  Common issues:")
            print("    - Wrong symbol: TradingView uses BTCUSD (not BTCUSDT) on BINANCE")
            print("    - Rate limit: anonymous tvdatafeed has limits")
            print("    - Try exchange='CRYPTO' instead of 'BINANCE'")
            return

        print(f"  [OK] Got {len(records)} records from TradingView")
        print(f"  First bar: {records[0].datetime} O={records[0].open} H={records[0].high} L={records[0].low} C={records[0].close} V={records[0].volume}")
        print(f"  Last bar:  {records[-1].datetime} O={records[-1].open} H={records[-1].high} L={records[-1].low} C={records[-1].close} V={records[-1].volume}")

        # --- Step 3: Upsert to MongoDB ---
        print(f"\n[Step 3] Upserting {len(records)} bars to MongoDB...")
        upserted = await ohlcv_repo.upsert_many(records)
        print(f"  [OK] Upserted {upserted} bars")

        # --- Step 4: Verify in DB ---
        print("\n[Step 4] Verifying stored data...")
        new_count = await ohlcv_repo.count(symbol, exchange, Interval(interval))
        new_latest = await ohlcv_repo.get_latest(symbol, exchange, Interval(interval))
        print(f"  Total bars now: {new_count} (was {existing_count})")
        print(f"  Latest bar:     {new_latest.datetime if new_latest else 'None'}")
        print(f"  Net new bars:   {new_count - existing_count}")

        # --- Step 5: Update sync status ---
        print("\n[Step 5] Updating sync status...")
        await sync_status_repo.upsert(
            symbol, exchange, Interval(interval), "completed",
            bar_count=new_count,
            last_bar_at=new_latest.datetime if new_latest else None,
        )
        updated_status = await sync_status_repo.find_one(symbol, exchange, Interval(interval))
        print(f"  Status: {updated_status.status}")
        print(f"  Bar count: {updated_status.bar_count}")

        # --- Step 6: Show sample of latest bars ---
        print(f"\n[Step 6] Last 5 bars in DB:")
        bars = await ohlcv_repo.find(symbol, exchange, Interval(interval), limit=5)
        for bar in bars:
            print(f"  {bar.datetime}  O={bar.open:.2f}  H={bar.high:.2f}  L={bar.low:.2f}  C={bar.close:.2f}  V={bar.volume:.0f}")

    finally:
        await cache.disconnect()
        await db.disconnect()

    print("\n" + "=" * 60)
    print("Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug: sync OHLCV bars")
    parser.add_argument("--symbol", default="BTCUSD", help="Symbol (default: BTCUSD)")
    parser.add_argument("--exchange", default="BINANCE", help="Exchange (default: BINANCE)")
    parser.add_argument("--interval", default="4h", help="Interval (default: 4h)")
    parser.add_argument("--bars", type=int, default=100, help="Number of bars (default: 100)")
    args = parser.parse_args()

    asyncio.run(main(args.symbol, args.exchange, args.interval, args.bars))
