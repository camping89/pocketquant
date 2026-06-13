"""Backfill OHLCV bars from Binance public klines REST API.

Surgical gap-filler: backfill a specific [start,end] window for one
symbol/interval, beyond TradingView REST's 5000-bar cap. Distinct from
resync_2y_from_binance.py, which resyncs a bulk rolling window across all
tracked symbols. Uses the free, unauthenticated `/api/v3/klines` endpoint
with start/end pagination.

Example (dry-run):
    uv run python scripts/backfill_1m_from_binance.py \\
        --symbol BTCUSDT --exchange BINANCE \\
        --start 2026-04-30T08:54:00Z --end 2026-05-03T21:34:00Z \\
        --dry-run

Override Mongo URL via env (preferred) or CLI flag:
    MONGODB_URL='mongodb://...' uv run python scripts/backfill_1m_from_binance.py ...
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

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

logger = get_logger("scripts.backfill_1m_from_binance")

BINANCE_API_BASE = "https://api.binance.com"
KLINES_ENDPOINT = "/api/v3/klines"
MAX_LIMIT_PER_CALL = 1000
INTER_CALL_SLEEP_SEC = 0.1


@dataclass(frozen=True)
class BackfillConfig:
    symbol: str
    exchange: str
    interval: Interval
    start: datetime
    end: datetime
    dry_run: bool
    mongodb_url: str | None


def _parse_iso_utc(value: str) -> datetime:
    """Parse ISO 8601 UTC timestamp (accepts trailing 'Z')."""
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_args(argv: list[str] | None = None) -> BackfillConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT")
    parser.add_argument("--exchange", default="BINANCE", help="Exchange tag (default BINANCE)")
    parser.add_argument(
        "--interval",
        default="1m",
        choices=[i.value for i in INTERVAL_TO_BINANCE],
        help="Bar interval (default 1m)",
    )
    parser.add_argument("--start", required=True, help="ISO 8601 UTC, e.g. 2026-04-30T08:54:00Z")
    parser.add_argument("--end", required=True, help="ISO 8601 UTC, e.g. 2026-05-03T21:34:00Z")
    parser.add_argument("--dry-run", action="store_true", help="Fetch + map + log, no DB writes")
    parser.add_argument(
        "--mongodb-url",
        default=None,
        help="Override Settings.mongodb_url (env MONGODB_URL also honored)",
    )
    args = parser.parse_args(argv)

    symbol = args.symbol.strip().upper()
    if not symbol:
        parser.error("--symbol must be non-empty")

    start = _parse_iso_utc(args.start)
    end = _parse_iso_utc(args.end)
    if not start < end:
        parser.error("--start must be strictly before --end")

    return BackfillConfig(
        symbol=symbol,
        exchange=args.exchange.strip().upper(),
        interval=Interval(args.interval),
        start=start,
        end=end,
        dry_run=bool(args.dry_run),
        mongodb_url=args.mongodb_url,
    )


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


def _build_settings(cfg: BackfillConfig) -> Settings:
    """Build Settings, applying optional MongoDB URL override (CLI > env > .env)."""
    override = cfg.mongodb_url or os.environ.get("MONGODB_URL")
    if override:
        os.environ["MONGODB_URL"] = override
        get_settings.cache_clear()
    return get_settings()


async def run_backfill(cfg: BackfillConfig) -> int:
    settings = _build_settings(cfg)
    setup_logging(settings)

    mongo_host = str(settings.mongodb_url).split("@")[-1].split("/")[0]
    # Composite {code}:{exchange} — the system-wide bar key; a bare code would
    # write bars the rest of the system can't query.
    composite_symbol = f"{cfg.symbol}:{cfg.exchange}"
    binance_interval, bar_duration_ms = INTERVAL_TO_BINANCE[cfg.interval]
    start_ms = int(cfg.start.timestamp() * 1000)
    end_ms = int(cfg.end.timestamp() * 1000)
    expected_bars = max(0, (end_ms - start_ms) // bar_duration_ms + 1)

    logger.info(
        "backfill.start",
        symbol=cfg.symbol,
        exchange=cfg.exchange,
        interval=cfg.interval.value,
        start=cfg.start.isoformat(),
        end=cfg.end.isoformat(),
        expected_bars=expected_bars,
        mongo_host=mongo_host,
        dry_run=cfg.dry_run,
    )

    db = Database()
    bar_repo: BarRepository | None = None
    if not cfg.dry_run:
        await db.connect(settings)
        bar_repo = BarRepository(db)
        await bar_repo.ensure_indexes()

    fetched_total = 0
    inserted_total = 0
    chunk_idx = 0

    try:
        async with httpx.AsyncClient(base_url=BINANCE_API_BASE) as http:
            cursor_ms = start_ms
            while cursor_ms <= end_ms:
                chunk_idx += 1
                klines = await fetch_klines(
                    http,
                    cfg.symbol,
                    cfg.interval,
                    cursor_ms,
                    end_ms,
                    limit=MAX_LIMIT_PER_CALL,
                )
                if not klines:
                    logger.info("backfill.chunk_empty", chunk=chunk_idx, cursor_ms=cursor_ms)
                    break

                bars = [kline_to_bar(k, composite_symbol, cfg.interval) for k in klines]
                # Sanity assertion: open_time aligned to bar boundary
                for k in klines:
                    if int(k[0]) % bar_duration_ms != 0:
                        raise RuntimeError(
                            f"open_time {k[0]} not aligned to {binance_interval} boundary"
                        )

                fetched_total += len(bars)
                if cfg.dry_run or bar_repo is None:
                    logger.info(
                        "backfill.chunk_dry_run",
                        chunk=chunk_idx,
                        fetched=len(bars),
                        first=bars[0].datetime.isoformat() if bars[0].datetime else None,
                        last=bars[-1].datetime.isoformat() if bars[-1].datetime else None,
                    )
                else:
                    inserted = await bar_repo.insert_many(bars, source=SOURCE_REST_BACKFILL)
                    inserted_total += inserted
                    logger.info(
                        "backfill.chunk_inserted",
                        chunk=chunk_idx,
                        fetched=len(bars),
                        inserted=inserted,
                        skipped=len(bars) - inserted,
                        first=bars[0].datetime.isoformat() if bars[0].datetime else None,
                        last=bars[-1].datetime.isoformat() if bars[-1].datetime else None,
                    )

                last_open_ms = int(klines[-1][0])
                next_cursor = last_open_ms + bar_duration_ms
                if next_cursor <= cursor_ms:
                    # Defensive: prevent infinite loop if Binance ever returns
                    # a row at/before cursor.
                    logger.warning(
                        "backfill.cursor_no_advance",
                        cursor_ms=cursor_ms,
                        next_cursor=next_cursor,
                    )
                    break
                cursor_ms = next_cursor

                if len(klines) < MAX_LIMIT_PER_CALL:
                    # Fewer than limit -> reached end of range.
                    break

                await asyncio.sleep(INTER_CALL_SLEEP_SEC)
    finally:
        if not cfg.dry_run:
            await db.disconnect()

    logger.info(
        "backfill.summary",
        chunks=chunk_idx,
        expected=expected_bars,
        fetched=fetched_total,
        inserted=inserted_total,
        dry_run=cfg.dry_run,
    )

    if cfg.dry_run:
        return 0
    if fetched_total == 0:
        logger.error("backfill.no_data_fetched")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    cfg = parse_args(argv)
    return asyncio.run(run_backfill(cfg))


if __name__ == "__main__":
    sys.exit(main())
