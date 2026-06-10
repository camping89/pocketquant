"""One-shot: backfill bars corrupted by the in-progress-bar regression.

Plan: plans/260508-2147-binance-sync-in-progress-bar-fix/phase-02-backfill-regression-window.md

Window: --start (default 2026-05-08T07:30:00Z) → datetime.now(UTC)
Action per tracked symbol:
  1. Delete bars in window across all 6 intervals.
  2. Re-fetch fresh 1m bars via fixed BinanceClient (Phase 1).
  3. Cascade 1m → 5m/15m/1h/4h/1d.

Pre-requisites (run BEFORE invoking):
  - Phase 1 fix deployed (BinanceClient.fetch_ohlcv caps endTime).
  - sync_1m cron PAUSED (set ENABLE_JOBS=false + container restart, or pause via scheduler).
  - mongodump backup taken: bars collection.

Run inside the prod container:
  docker cp scripts/backfill_regression_window.py pocketquant-app:/tmp/
  docker exec pocketquant-app python /tmp/backfill_regression_window.py \
      --start 2026-05-08T07:30:00Z

Idempotent: rerunning is safe. Delete uses [start, now) range guard.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from pocketquant.app.market_data.app_services.cascade_aggregator import cascade_for_symbol

from pocketquant.app.di.container import create_container, register_handlers
from pocketquant.app.market_data.handlers.sync import SyncSymbolCommand
from pocketquant.core.common.logging import get_logger
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.domain.bar.entities import SOURCE_REST_BACKFILL
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

logger = get_logger("backfill_regression_window")

INTERVALS_TO_RESET = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string ending in Z or with +00:00 → aware UTC datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def _backfill_symbol(
    symbol: str,
    exchange: str,
    start: datetime,
    end: datetime,
    n_bars: int,
    lookback_minutes: int,
    *,
    mediator: Mediator,
    bar_repo: BarRepository,
) -> dict:
    """Reset, re-sync 1m, cascade for one (symbol, exchange) pair."""
    deleted = await bar_repo.delete_many_by_range(
        symbol=symbol,
        exchange=exchange,
        intervals=INTERVALS_TO_RESET,
        start_dt=start,
        end_dt=end,
    )
    cmd = SyncSymbolCommand(
        symbol=symbol,
        exchange=exchange,
        interval=Interval.MINUTE_1,
        n_bars=n_bars,
        source=SOURCE_REST_BACKFILL,
    )
    sync_result = await mediator.send(cmd)
    cascade_counts = await cascade_for_symbol(
        symbol=symbol,
        exchange=exchange,
        lookback_minutes=lookback_minutes,
        bar_repo=bar_repo,
    )
    return {
        "symbol": symbol,
        "exchange": exchange,
        "deleted": deleted,
        "fetched_1m": getattr(sync_result, "bars_fetched", None),
        "inserted_1m": getattr(sync_result, "bars_synced", None),
        "cascade": {tf.value: count for tf, count in cascade_counts.items()},
    }


async def run(args: argparse.Namespace) -> int:
    start = _parse_iso(args.start)
    end = datetime.now(UTC)

    if start >= end:
        print(f"ERROR: start {start.isoformat()} not before now {end.isoformat()}", file=sys.stderr)
        return 2

    minutes = int((end - start).total_seconds() / 60)
    n_bars = max(args.n_bars, minutes + 60)
    lookback = max(args.lookback_minutes, minutes + 60)

    container = create_container()
    await register_handlers(container)
    try:
        mediator = await container.get(Mediator)
        bar_repo = await container.get(BarRepository)
        ts_repo = await container.get(TrackedSymbolRepository)

        tracked = await ts_repo.list_all()
        if not tracked:
            print("No tracked symbols found — nothing to backfill.", file=sys.stderr)
            return 1

        if args.symbol:
            wanted = args.symbol.upper()
            tracked = [t for t in tracked if t.symbol.upper() == wanted]
            if not tracked:
                print(f"Tracked symbol {wanted} not found.", file=sys.stderr)
                return 1

        print("=" * 70)
        print(f"Backfill window: [{start.isoformat()}, {end.isoformat()})")
        print(f"Symbols: {len(tracked)} | n_bars(1m)={n_bars} | lookback={lookback}m")
        print("=" * 70)

        summaries: list[dict] = []
        for ts in tracked:
            print(f"\n→ {ts.exchange}:{ts.symbol}")
            try:
                summary = await _backfill_symbol(
                    symbol=ts.symbol,
                    exchange=ts.exchange,
                    start=start,
                    end=end,
                    n_bars=n_bars,
                    lookback_minutes=lookback,
                    mediator=mediator,
                    bar_repo=bar_repo,
                )
                summaries.append(summary)
                print(
                    f"   deleted={summary['deleted']} "
                    f"fetched_1m={summary['fetched_1m']} "
                    f"inserted_1m={summary['inserted_1m']} "
                    f"cascade={summary['cascade']}"
                )
            except Exception as exc:
                print(f"   FAILED: {exc!r}", file=sys.stderr)
                logger.exception("backfill_failed", symbol=ts.symbol, exchange=ts.exchange)

        print("\n" + "=" * 70)
        print(f"Done. {len(summaries)}/{len(tracked)} symbols backfilled cleanly.")
        for s in summaries:
            print(
                f"  {s['exchange']}:{s['symbol']} "
                f"del={s['deleted']} ins1m={s['inserted_1m']} cascade={s['cascade']}"
            )
        print("=" * 70)
        return 0
    finally:
        await container.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        default="2026-05-08T07:30:00Z",
        help="Window start (UTC ISO-8601). Default: 2026-05-08T07:30:00Z",
    )
    parser.add_argument(
        "--n-bars",
        type=int,
        default=500,
        help="Minimum n_bars to request from BinanceClient (1m). Auto-grows for wider windows.",
    )
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=500,
        help="Cascade lookback minutes. Auto-grows to cover the window.",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Restrict to a single tracked symbol (e.g. BTCUSDT). Default: all tracked.",
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
