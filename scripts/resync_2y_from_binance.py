"""Re-sync 2 years of OHLCV bars from Binance for all tracked symbols.

Deletes bars in [now-N days, now-1min] window for all canonical timeframes
(1m, 5m, 15m, 1h, 4h, 1d), re-fetches 1m from Binance, inserts, then
cascade-rebuilds higher tfs from the clean 1m source.

Resumable: writes /tmp/resync-checkpoint.json after each symbol completes.
Restart skips already-done symbols automatically.

Usage:
    uv run python scripts/resync_2y_from_binance.py [--days 730] [--dry-run]
    uv run python scripts/resync_2y_from_binance.py --symbols BTCUSDT,ETHUSDT
    uv run python scripts/resync_2y_from_binance.py --no-cascade

Exit codes: 0 = success, 1 = Mongo connection failure or partial failure.

MONGODB_URL must be set in environment (never passed as CLI flag). On the VPS it
holds an internal docker hostname, so prefix prod runs with
`docker exec pocketquant-app` (see docs/deployment.md → 2-Year Bar Re-Sync).

Production run order (multi-day option):
    Day 1: python scripts/resync_2y_from_binance.py --days 730 --symbols BTCUSDT,ETHUSDT,...
    Day 2: python scripts/resync_2y_from_binance.py --days 730 --symbols SOLUSDT,...
    (checkpoint persists across runs; done symbols skipped automatically)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.core.domain.bar.entities import SOURCE_REST_BACKFILL
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.execution.market_data.app_services.cascade_aggregator import (
    CASCADE_TFS,
    cascade_for_symbol,
)
from pocketquant.infrastructure.market_data.binance.binance_client import BinanceClient
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger("scripts.resync_2y_from_binance")

CANONICAL_TFS: list[Interval] = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

CHECKPOINT_PATH = Path("/tmp/resync-checkpoint.json")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=730, help="Lookback window in days (default 730)"
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbol subset, e.g. BTCUSDT,ETHUSDT",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan + estimate, NO DB writes",
    )
    parser.add_argument(
        "--no-cascade", action="store_true", help="Skip cascade aggregation step"
    )
    return parser.parse_args(argv)


def _load_checkpoint() -> dict[str, str]:
    """Load checkpoint map {symbol: 'done'} from disk. Returns empty dict if missing."""
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_checkpoint(state: dict[str, str]) -> None:
    """Write checkpoint atomically: write to .tmp then os.replace (POSIX-atomic)."""
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, CHECKPOINT_PATH)


def _compute_window(days: int) -> tuple[datetime, datetime]:
    """Return (start_dt, end_dt) where end = floor(now,1min) - 1s, start = end - days."""
    now = datetime.now(UTC)
    end_dt = now.replace(second=0, microsecond=0) - timedelta(seconds=1)
    start_dt = end_dt - timedelta(days=days)
    return start_dt, end_dt


def _estimate_wall_time(symbol_count: int, days: int) -> str:
    bars_per_symbol = days * 1440
    calls_per_symbol = (bars_per_symbol + 999) // 1000
    total_calls = symbol_count * calls_per_symbol
    estimated_secs = total_calls * 0.1 + symbol_count * 5  # 100ms/call + cascade overhead
    return f"~{estimated_secs / 60:.0f} min"


async def _resync_symbol(
    symbol: str,
    exchange: str,
    start_dt: datetime,
    end_dt: datetime,
    days: int,
    bar_repo: BarRepository,
    binance_client: BinanceClient,
    no_cascade: bool,
) -> dict:
    """Run full delete→fetch→insert→cascade cycle for one symbol. Returns metrics dict."""
    t0 = time.monotonic()

    # 1. Delete existing bars in window across all canonical tfs
    deleted = await bar_repo.delete_many_by_range(
        symbol, exchange, CANONICAL_TFS, start_dt, end_dt
    )
    logger.info("resync.deleted", symbol=symbol, deleted_count=deleted)

    # 2. Fetch 1m bars from Binance (chunked internally, 100ms inter-call)
    n_bars = days * 1440
    bars = await binance_client.fetch_ohlcv(symbol, exchange, Interval.MINUTE_1, n_bars=n_bars)
    # Drop any bars at or after end_dt (defends against in-progress bar from BinanceClient
    # paginating from wall-clock now). Repository unique index would silently skip the later
    # complete bar, leaving a partial bar permanently in the DB.
    bars = [b for b in bars if b.datetime < end_dt]
    logger.info("resync.fetched", symbol=symbol, bar_count=len(bars))

    # 3. Insert 1m bars (diff-aware upsert loop, idempotent)
    inserted = await bar_repo.insert_many(bars, source=SOURCE_REST_BACKFILL)

    elapsed = time.monotonic() - t0
    pct_done = inserted / max(n_bars, 1) * 100
    logger.info(
        "resync.symbol_progress",
        symbol=symbol,
        pct=round(pct_done, 1),
        bars_inserted=inserted,
        elapsed_s=round(elapsed, 1),
    )

    # 4. Cascade: rebuild 5m, 15m, 1h, 4h, 1d from clean 1m source
    cascade_counts: dict[Interval, int] = {}
    if not no_cascade:
        lookback_minutes = days * 1440
        cascade_counts = await cascade_for_symbol(symbol, exchange, lookback_minutes, bar_repo)
        logger.info(
            "resync.cascade_complete",
            symbol=symbol,
            tfs={k.value: v for k, v in cascade_counts.items()},
        )

    return {
        "symbol": symbol,
        "deleted": deleted,
        "fetched": len(bars),
        "inserted": inserted,
        "cascade": {k.value: v for k, v in cascade_counts.items()},
        "elapsed_s": round(time.monotonic() - t0, 1),
    }


async def run_resync(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings)

    start_dt, end_dt = _compute_window(args.days)
    symbol_filter = {s.strip().upper() for s in args.symbols.split(",")} if args.symbols else None

    logger.info(
        "resync.start",
        days=args.days,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        dry_run=args.dry_run,
        no_cascade=args.no_cascade,
        symbol_filter=list(symbol_filter) if symbol_filter else "all",
    )

    # Dry-run: connect to DB only to read tracked symbols then exit
    db = Database()
    try:
        await db.connect(settings)
    except Exception as exc:
        logger.error("resync.mongo_connection_failed", error=str(exc))
        return 1

    tracked_repo = TrackedSymbolRepository(db)
    all_symbols = await tracked_repo.list_all()
    await db.disconnect()

    # Filter to BINANCE; warn on others
    binance_symbols = []
    for ts in all_symbols:
        if ts.exchange.upper() != "BINANCE":
            logger.warning("resync.skip_non_binance", symbol=ts.symbol, exchange=ts.exchange)
            continue
        if symbol_filter and ts.symbol.upper() not in symbol_filter:
            continue
        binance_symbols.append(ts.symbol.upper())

    if not binance_symbols:
        logger.warning("resync.no_symbols_to_process")
        return 0

    if args.dry_run:
        estimate = _estimate_wall_time(len(binance_symbols), args.days)
        calls_per_symbol = (args.days * 1440 + 999) // 1000
        cascade_status = "disabled" if args.no_cascade else "enabled"
        cascade_tfs = [tf.value for tf in CASCADE_TFS]
        total_calls = len(binance_symbols) * calls_per_symbol
        print("\n--- DRY RUN PLAN ---")
        print(f"Symbols ({len(binance_symbols)}): {', '.join(binance_symbols)}")
        print(f"Window: {start_dt.date()} → {end_dt.date()} ({args.days}d)")
        print(f"Cascade: {cascade_status} ({cascade_tfs})")
        print(f"Estimated REST calls: {total_calls:,}")
        print(f"Estimated wall time: {estimate}")
        print(f"Checkpoint: {CHECKPOINT_PATH}")
        print("--- END DRY RUN ---\n")
        return 0

    # Load checkpoint — skip already-done symbols
    checkpoint = _load_checkpoint()
    pending = [s for s in binance_symbols if checkpoint.get(s) != "done"]
    logger.info(
        "resync.checkpoint_loaded",
        done=len(binance_symbols) - len(pending),
        pending=len(pending),
    )

    # Connect for actual work
    await db.connect(settings)
    bar_repo = BarRepository(db)
    await bar_repo.ensure_indexes()
    binance_client = BinanceClient(settings)

    results = []
    total_t0 = time.monotonic()

    try:
        for idx, symbol in enumerate(pending, start=1):
            logger.info("resync.symbol_start", symbol=symbol, progress=f"{idx}/{len(pending)}")
            try:
                metrics = await _resync_symbol(
                    symbol=symbol,
                    exchange="BINANCE",
                    start_dt=start_dt,
                    end_dt=end_dt,
                    days=args.days,
                    bar_repo=bar_repo,
                    binance_client=binance_client,
                    no_cascade=args.no_cascade,
                )
                results.append(metrics)
                checkpoint[symbol] = "done"
                _save_checkpoint(checkpoint)
            except Exception as exc:
                logger.error("resync.symbol_failed", symbol=symbol, error=str(exc), exc_info=True)
                results.append({"symbol": symbol, "error": str(exc)})
    finally:
        await db.disconnect()
        await binance_client.close()

    # Summary
    total_elapsed = round(time.monotonic() - total_t0, 1)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    failed = [r["symbol"] for r in results if "error" in r]

    logger.info(
        "resync.summary",
        symbols_processed=len(results),
        total_inserted=total_inserted,
        failed=failed,
        total_elapsed_s=total_elapsed,
    )

    print("\n=== RESYNC SUMMARY ===")
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']}: FAILED — {r['error']}")
        else:
            ins = r["inserted"]
            dlt = r["deleted"]
            ela = r["elapsed_s"]
            print(f"  {r['symbol']}: inserted={ins:,} deleted={dlt:,} elapsed={ela}s")
    print(f"Total wall time: {total_elapsed}s ({total_elapsed / 60:.1f} min)")
    print(f"Total 1m bars inserted: {total_inserted:,}")
    if failed:
        print(f"Failed symbols ({len(failed)}): {', '.join(failed)}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_resync(args))


if __name__ == "__main__":
    sys.exit(main())
