"""Backfill / re-sync OHLCV bars from Binance public klines REST API.

One tool, two scopes — both fetch from Binance's free, unauthenticated
`/api/v3/klines` endpoint with start/end pagination (beyond TradingView REST's
5000-bar cap):

- **Targeted** (`--symbol`): backfill one symbol/interval over an explicit
  window. Insert-only by default — a surgical gap-filler.
- **Bulk** (no `--symbol`): process every tracked BINANCE symbol (optionally
  narrowed by `--symbols`). With `--replace` this is the full re-sync:
  delete the window, re-fetch clean 1m, cascade-rebuild higher tfs. Resumable
  via an on-disk checkpoint so a multi-day run skips already-done symbols.

Window — pick ONE:
    --start ISO --end ISO     explicit [start, end) range
    --days N                  rolling: end = floor(now,1min) - 1s, start = end - N days

Examples:
    # Targeted gap-fill, dry-run
    uv run python scripts/backfill/binance_bars.py \\
        --symbol BTCUSDT --start 2026-04-30T08:54:00Z --end 2026-05-03T21:34:00Z --dry-run

    # Bulk 2-year re-sync of all tracked symbols (delete + refetch + cascade)
    uv run python scripts/backfill/binance_bars.py --days 730 --replace

    # Re-sync a subset, no cascade
    uv run python scripts/backfill/binance_bars.py \\
        --days 730 --replace --symbols BTCUSDT,ETHUSDT --no-cascade

MONGODB_URL is read from the environment (preferred) or --mongodb-url. On the VPS
it holds an internal docker hostname, so prefix prod runs with
`docker exec pocketquant-app` (see docs/deployment.md -> 2-Year Bar Re-Sync).

Exit codes: 0 = success, 1 = Mongo connection failure, no data fetched, or any
per-symbol failure in a bulk run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import Settings, get_settings
from pocketquant.core.domain.bar.entities import SOURCE_REST_BACKFILL
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.binance.binance_mappers import (
    INTERVAL_TO_BINANCE,
    kline_to_bar,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)
from pocketquant.engine.market_data.app_services.cascade_aggregator import (
    CASCADE_TFS,
    cascade_for_symbol,
)

logger = get_logger("scripts.backfill.binance_bars")

BINANCE_API_BASE = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"
MAX_LIMIT_PER_CALL = 1000
INTER_CALL_SLEEP_SEC = 0.1

# Timeframes a bulk --replace deletes before refetching 1m. The cascade rebuilds
# 5m..1d from the clean 1m source, so the whole canonical set is dropped first.
CANONICAL_TFS: list[Interval] = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]

CHECKPOINT_PATH = Path("/tmp/binance-backfill-checkpoint.json")


@dataclass(frozen=True)
class BackfillConfig:
    symbol: str | None  # None => all tracked BINANCE symbols (bulk mode)
    symbols_filter: frozenset[str] | None  # subset of tracked symbols, bulk mode
    exchange: str
    interval: Interval  # fetch interval (1m for cascade-based bulk runs)
    start: datetime
    end: datetime
    replace: bool  # delete the window before insert (re-sync) vs insert-only (gap-fill)
    cascade: bool  # rebuild higher tfs from 1m after insert (bulk only)
    dry_run: bool
    mongodb_url: str | None

    @property
    def is_bulk(self) -> bool:
        return self.symbol is None


def _parse_iso_utc(value: str) -> datetime:
    """Parse ISO 8601 UTC timestamp (accepts trailing 'Z')."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _rolling_window(days: int) -> tuple[datetime, datetime]:
    """Rolling window: end = floor(now,1min) - 1s, start = end - days.

    The -1s on a minute floor excludes the in-progress minute so a partial bar
    is never fetched as if complete.
    """
    now = datetime.now(UTC)
    end_dt = now.replace(second=0, microsecond=0) - timedelta(seconds=1)
    start_dt = end_dt - timedelta(days=days)
    return start_dt, end_dt


def parse_args(argv: list[str] | None = None) -> BackfillConfig:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--symbol", default=None, help="Single trading pair, e.g. BTCUSDT")
    parser.add_argument(
        "--symbols",
        default=None,
        help="Bulk mode: comma-separated subset of tracked symbols, e.g. BTCUSDT,ETHUSDT",
    )
    parser.add_argument("--exchange", default="BINANCE", help="Exchange tag (default BINANCE)")
    parser.add_argument(
        "--interval",
        default="1m",
        choices=[i.value for i in INTERVAL_TO_BINANCE],
        help="Fetch interval (default 1m; cascade rebuilds higher tfs)",
    )
    # Window — explicit range XOR rolling --days.
    parser.add_argument("--start", default=None, help="ISO 8601 UTC, e.g. 2026-04-30T08:54:00Z")
    parser.add_argument("--end", default=None, help="ISO 8601 UTC, e.g. 2026-05-03T21:34:00Z")
    parser.add_argument(
        "--days", type=int, default=None, help="Rolling lookback window in days (e.g. 730)"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete bars in the window before insert (re-sync). Default: insert-only gap-fill",
    )
    parser.add_argument(
        "--no-cascade",
        action="store_true",
        help="Skip rebuilding 5m..1d from 1m after insert (bulk runs)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan + fetch only, no DB writes")
    parser.add_argument(
        "--mongodb-url",
        default=None,
        help="Override Settings.mongodb_url (env MONGODB_URL also honored)",
    )
    args = parser.parse_args(argv)

    # Window: exactly one of (--start AND --end) or --days.
    has_range = args.start is not None and args.end is not None
    has_days = args.days is not None
    if has_range == has_days:
        parser.error("provide either --start AND --end, or --days (not both, not neither)")

    if has_days:
        if args.days <= 0:
            parser.error("--days must be positive")
        start, end = _rolling_window(args.days)
    else:
        if args.start is None or args.end is None:
            parser.error("--start and --end must be given together")
        start = _parse_iso_utc(args.start)
        end = _parse_iso_utc(args.end)
        if not start < end:
            parser.error("--start must be strictly before --end")

    symbol = args.symbol.strip().upper() if args.symbol else None
    if symbol == "":
        parser.error("--symbol must be non-empty")
    symbols_filter = (
        frozenset(s.strip().upper() for s in args.symbols.split(",") if s.strip())
        if args.symbols
        else None
    )

    return BackfillConfig(
        symbol=symbol,
        symbols_filter=symbols_filter,
        exchange=args.exchange.strip().upper(),
        interval=Interval(args.interval),
        start=start,
        end=end,
        replace=bool(args.replace),
        cascade=not args.no_cascade,
        dry_run=bool(args.dry_run),
        mongodb_url=args.mongodb_url,
    )


def _load_checkpoint() -> dict[str, str]:
    """Load checkpoint map {symbol: 'done'} from disk. Empty dict if missing/corrupt."""
    try:
        return json.loads(CHECKPOINT_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_checkpoint(state: dict[str, str]) -> None:
    """Write checkpoint atomically: write to .tmp then os.replace (POSIX-atomic)."""
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, CHECKPOINT_PATH)


def _build_settings(mongodb_url: str | None) -> Settings:
    """Build Settings, applying optional MongoDB URL override (CLI > env > .env)."""
    override = mongodb_url or os.environ.get("MONGODB_URL")
    if override:
        os.environ["MONGODB_URL"] = override
        get_settings.cache_clear()
    return get_settings()


def _estimate_wall_time(symbol_count: int, start: datetime, end: datetime) -> str:
    minutes = max(1, int((end - start).total_seconds() // 60))
    calls_per_symbol = (minutes + MAX_LIMIT_PER_CALL - 1) // MAX_LIMIT_PER_CALL
    total_calls = symbol_count * calls_per_symbol
    estimated_secs = total_calls * INTER_CALL_SLEEP_SEC + symbol_count * 5
    return f"~{estimated_secs / 60:.0f} min"


async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: Interval,
    start_ms: int,
    end_ms: int,
    limit: int = MAX_LIMIT_PER_CALL,
) -> list[list]:
    binance_interval, _ = INTERVAL_TO_BINANCE[interval]
    params = {
        "symbol": symbol.upper(),
        "interval": binance_interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": limit,
    }
    resp = await client.get(KLINES_ENDPOINT, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


async def _fetch_window(
    http: httpx.AsyncClient,
    cfg: BackfillConfig,
    composite_symbol: str,
    code: str,
) -> list:
    """Page Binance klines across [start, end) and map to Bar entities.

    Bars at/after cfg.end are dropped: a minute-floored rolling end can still
    surface the in-progress bar, which the unique index would later refuse to
    overwrite with the completed one — leaving a permanent partial bar.
    """
    binance_interval, bar_duration_ms = INTERVAL_TO_BINANCE[cfg.interval]
    start_ms = int(cfg.start.timestamp() * 1000)
    end_ms = int(cfg.end.timestamp() * 1000)

    bars: list = []
    cursor_ms = start_ms
    chunk_idx = 0
    while cursor_ms <= end_ms:
        chunk_idx += 1
        klines = await fetch_klines(http, code, cfg.interval, cursor_ms, end_ms)
        if not klines:
            break

        for k in klines:
            if int(k[0]) % bar_duration_ms != 0:
                raise RuntimeError(f"open_time {k[0]} not aligned to {binance_interval} boundary")
        bars.extend(kline_to_bar(k, composite_symbol, cfg.interval) for k in klines)

        last_open_ms = int(klines[-1][0])
        next_cursor = last_open_ms + bar_duration_ms
        if next_cursor <= cursor_ms:
            logger.warning("backfill.cursor_no_advance", cursor_ms=cursor_ms, next=next_cursor)
            break
        cursor_ms = next_cursor
        if len(klines) < MAX_LIMIT_PER_CALL:
            break
        await asyncio.sleep(INTER_CALL_SLEEP_SEC)

    return [b for b in bars if b.datetime is not None and b.datetime < cfg.end]


async def _process_symbol(
    code: str,
    cfg: BackfillConfig,
    http: httpx.AsyncClient,
    bar_repo: BarRepository,
) -> dict:
    """Run the (optional delete ->) fetch -> insert (-> cascade) cycle for one symbol."""
    t0 = time.monotonic()
    composite_symbol = f"{code}:{cfg.exchange}"

    deleted = 0
    if cfg.replace:
        # Re-sync drops the full canonical tf set so the cascade can rebuild
        # 5m..1d cleanly from the refetched 1m source.
        deleted = await bar_repo.delete_many_by_range(
            composite_symbol, CANONICAL_TFS, cfg.start, cfg.end
        )
        logger.info("backfill.deleted", symbol=composite_symbol, deleted_count=deleted)

    bars = await _fetch_window(http, cfg, composite_symbol, code)
    logger.info("backfill.fetched", symbol=composite_symbol, bar_count=len(bars))

    inserted = await bar_repo.insert_many(bars, source=SOURCE_REST_BACKFILL)

    cascade_counts: dict[Interval, int] = {}
    if cfg.cascade and cfg.interval == Interval.MINUTE_1:
        lookback_minutes = max(1, int((cfg.end - cfg.start).total_seconds() // 60))
        cascade_counts = await cascade_for_symbol(composite_symbol, lookback_minutes, bar_repo)
        logger.info(
            "backfill.cascade_complete",
            symbol=composite_symbol,
            tfs={k.value: v for k, v in cascade_counts.items()},
        )

    return {
        "symbol": code,
        "deleted": deleted,
        "fetched": len(bars),
        "inserted": inserted,
        "cascade": {k.value: v for k, v in cascade_counts.items()},
        "elapsed_s": round(time.monotonic() - t0, 1),
    }


async def _resolve_bulk_symbols(cfg: BackfillConfig, db: Database) -> list[str]:
    """Return tracked BINANCE symbol codes, narrowed by cfg.symbols_filter."""
    tracked_repo = TrackedSymbolRepository(db)
    all_symbols = await tracked_repo.list_all()
    codes: list[str] = []
    for ts in all_symbols:
        if ts.exchange.upper() != "BINANCE":
            logger.warning("backfill.skip_non_binance", symbol=ts.symbol, exchange=ts.exchange)
            continue
        code = ts.symbol.upper()
        if cfg.symbols_filter and code not in cfg.symbols_filter:
            continue
        codes.append(code)
    return codes


def _print_dry_run(cfg: BackfillConfig, codes: list[str]) -> None:
    cascade_status = "enabled" if cfg.cascade and cfg.interval == Interval.MINUTE_1 else "disabled"
    span_days = (cfg.end - cfg.start).days
    print("\n--- DRY RUN PLAN ---")
    print(f"Mode: {'bulk' if cfg.is_bulk else 'targeted'}")
    print(f"Symbols ({len(codes)}): {', '.join(codes)}")
    print(f"Window: {cfg.start.isoformat()} -> {cfg.end.isoformat()} ({span_days} days)")
    print(f"Interval: {cfg.interval.value}")
    print(f"Replace (delete first): {cfg.replace}")
    print(f"Cascade: {cascade_status} ({[tf.value for tf in CASCADE_TFS]})")
    print(f"Estimated wall time: {_estimate_wall_time(len(codes), cfg.start, cfg.end)}")
    if cfg.is_bulk:
        print(f"Checkpoint: {CHECKPOINT_PATH}")
    print("--- END DRY RUN ---\n")


async def run_backfill(cfg: BackfillConfig) -> int:
    settings = _build_settings(cfg.mongodb_url)
    setup_logging(settings)

    mongo_host = str(settings.mongodb_url).split("@")[-1].split("/")[0]
    logger.info(
        "backfill.start",
        mode="bulk" if cfg.is_bulk else "targeted",
        symbol=cfg.symbol,
        symbols_filter=sorted(cfg.symbols_filter) if cfg.symbols_filter else None,
        interval=cfg.interval.value,
        start=cfg.start.isoformat(),
        end=cfg.end.isoformat(),
        replace=cfg.replace,
        cascade=cfg.cascade,
        dry_run=cfg.dry_run,
        mongo_host=mongo_host,
    )

    db = Database()
    try:
        await db.connect(settings)
    except Exception as exc:
        logger.error("backfill.mongo_connection_failed", error=str(exc))
        return 1

    # Resolve the symbol work-list (single code, or all tracked BINANCE).
    if cfg.is_bulk:
        codes = await _resolve_bulk_symbols(cfg, db)
    else:
        assert cfg.symbol is not None
        codes = [cfg.symbol]

    if not codes:
        logger.warning("backfill.no_symbols_to_process")
        await db.disconnect()
        return 0

    if cfg.dry_run:
        await db.disconnect()
        _print_dry_run(cfg, codes)
        return 0

    # Checkpoint resume only applies to bulk runs (a single --symbol is one unit).
    checkpoint = _load_checkpoint() if cfg.is_bulk else {}
    pending = [c for c in codes if checkpoint.get(c) != "done"]
    if cfg.is_bulk:
        logger.info(
            "backfill.checkpoint_loaded", done=len(codes) - len(pending), pending=len(pending)
        )

    bar_repo = BarRepository(db)
    await bar_repo.ensure_indexes()

    results: list[dict] = []
    total_t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=BINANCE_API_BASE) as http:
            for idx, code in enumerate(pending, start=1):
                logger.info("backfill.symbol_start", symbol=code, progress=f"{idx}/{len(pending)}")
                try:
                    metrics = await _process_symbol(code, cfg, http, bar_repo)
                    results.append(metrics)
                    if cfg.is_bulk:
                        checkpoint[code] = "done"
                        _save_checkpoint(checkpoint)
                except Exception as exc:
                    logger.error(
                        "backfill.symbol_failed", symbol=code, error=str(exc), exc_info=True
                    )
                    results.append({"symbol": code, "error": str(exc)})
    finally:
        await db.disconnect()

    total_elapsed = round(time.monotonic() - total_t0, 1)
    total_inserted = sum(r.get("inserted", 0) for r in results)
    total_fetched = sum(r.get("fetched", 0) for r in results)
    failed = [r["symbol"] for r in results if "error" in r]

    logger.info(
        "backfill.summary",
        symbols_processed=len(results),
        total_inserted=total_inserted,
        failed=failed,
        total_elapsed_s=total_elapsed,
    )

    print("\n=== BACKFILL SUMMARY ===")
    for r in results:
        if "error" in r:
            print(f"  {r['symbol']}: FAILED - {r['error']}")
        else:
            print(
                f"  {r['symbol']}: inserted={r['inserted']:,} "
                f"deleted={r['deleted']:,} elapsed={r['elapsed_s']}s"
            )
    print(f"Total wall time: {total_elapsed}s ({total_elapsed / 60:.1f} min)")
    print(f"Total bars inserted: {total_inserted:,}")
    if failed:
        print(f"Failed symbols ({len(failed)}): {', '.join(failed)}")
        return 1
    if total_fetched == 0:
        logger.error("backfill.no_data_fetched")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    return asyncio.run(run_backfill(cfg))


if __name__ == "__main__":
    sys.exit(main())
