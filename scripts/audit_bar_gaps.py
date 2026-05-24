"""Audit bar-data gaps around historical missed-`sync_backfill` days.

For each (date, symbol, interval), compares the actual bar count in
``bars`` collection over a ``[date_start, date_start + window_hours]`` window
against the expected count (``window_hours * 60 / interval_minutes``).

Useful after a sync_backfill miss to verify whether the 100-min cascade
lookback (sync_1m) self-healed the gap or whether manual repair is needed.

Usage:
    uv run python scripts/audit_bar_gaps.py --dates 2026-05-08,2026-05-11,2026-05-21
    uv run python scripts/audit_bar_gaps.py --dates 2026-05-21 --window-hours 12

Exit codes: 0 = parity for every (date, symbol, interval), 1 = at least one gap
or Mongo connection failure.

MONGODB_URL must be set in environment (never passed as CLI flag).
"""

from __future__ import annotations

import argparse
import asyncio
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.core.persistence.mongodb import Database

logger = get_logger("scripts.audit_bar_gaps")

# Intervals to audit — matches sync_jobs.SYNC_INTERVALS minute mapping.
_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


@dataclass(frozen=True)
class AuditRow:
    date: str
    symbol: str
    interval: str
    expected: int
    actual: int

    @property
    def gap(self) -> int:
        return max(0, self.expected - self.actual)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dates",
        required=True,
        help="Comma-separated YYYY-MM-DD dates to audit, e.g. 2026-05-08,2026-05-11",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=6,
        help="Window after midnight UTC of each date (default 6h)",
    )
    return parser.parse_args(argv)


def expected_bars(interval: str, window_hours: int) -> int:
    """Count bars whose open timestamp falls in [start, start + window_hours).

    Bars are at offsets 0, m, 2m, ... < total_minutes — so the count is
    ``ceil(total_minutes / interval_minutes)``. Floor-division under-counts when
    window_hours straddles a partial interval (e.g. 6h window with 4h bars =
    2 bars at 00:00 and 04:00, NOT 1).
    """
    minutes = _INTERVAL_MINUTES.get(interval)
    if not minutes:
        return 0
    total_minutes = window_hours * 60
    return max(1, math.ceil(total_minutes / minutes))


def parse_date(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=UTC)


async def list_tracked_symbols(db: Database) -> list[str]:
    cursor = db.get_collection("tracked_symbols").find({}, {"symbol": 1})
    out: list[str] = []
    async for doc in cursor:
        symbol = doc.get("symbol")
        if symbol:
            out.append(symbol)
    return out


async def audit_one(
    db: Database,
    *,
    date: datetime,
    symbol: str,
    interval: str,
    window_hours: int,
) -> AuditRow:
    """Count actual 1m/5m/.../1d bars in window; compare against expected."""
    start = date
    end = date + timedelta(hours=window_hours)
    count = await db.get_collection("bars").count_documents(
        {
            "symbol": symbol,
            "interval": interval,
            "datetime": {"$gte": start, "$lt": end},
        }
    )
    return AuditRow(
        date=date.strftime("%Y-%m-%d"),
        symbol=symbol,
        interval=interval,
        expected=expected_bars(interval, window_hours),
        actual=count,
    )


def render_table(rows: list[AuditRow]) -> str:
    """Plain-text table; sort by gap desc so worst offenders surface first."""
    rows = sorted(rows, key=lambda r: (-r.gap, r.date, r.symbol, r.interval))
    header = f"{'Date':<11} {'Symbol':<22} {'Interval':<8} {'Expected':>8} {'Actual':>7} {'Gap':>6}"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in rows:
        lines.append(
            f"{r.date:<11} {r.symbol:<22} {r.interval:<8} "
            f"{r.expected:>8} {r.actual:>7} {r.gap:>6}"
        )
    return "\n".join(lines)


async def run_audit(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings)

    dates = [parse_date(d) for d in args.dates.split(",") if d.strip()]
    if not dates:
        logger.error("audit_bar_gaps.no_dates")
        return 1

    db = Database()
    try:
        await db.connect(settings)
    except Exception as exc:
        logger.error("audit_bar_gaps.mongo_connection_failed", error=str(exc))
        return 1

    try:
        symbols = await list_tracked_symbols(db)
        if not symbols:
            logger.warning("audit_bar_gaps.no_tracked_symbols")
            print("No tracked symbols — nothing to audit.")
            return 0

        rows: list[AuditRow] = []
        for date in dates:
            for symbol in symbols:
                for interval in _INTERVAL_MINUTES:
                    rows.append(
                        await audit_one(
                            db,
                            date=date,
                            symbol=symbol,
                            interval=interval,
                            window_hours=args.window_hours,
                        )
                    )

        print(render_table(rows))
        total_gap = sum(r.gap for r in rows)
        print(f"\nTotal missing bars across audit: {total_gap}")
        return 1 if total_gap > 0 else 0
    finally:
        await db.disconnect()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_audit(args))


if __name__ == "__main__":
    sys.exit(main())
