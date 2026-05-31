"""Audit OHLCV bar quality metrics across tracked symbols.

Runs a MongoDB aggregation pipeline to count flat bars (O==H==L==C),
zero-volume bars, and abnormal-volume bars per (symbol, exchange, interval).
Outputs a Markdown table to plans/reports/audit-{YYYYMMDD}-bar-quality.md.

Usage:
    uv run python scripts/audit_bar_quality.py [--days 730] [--output PATH]
    uv run python scripts/audit_bar_quality.py --symbol BTCUSDT --exchange BINANCE

Exit codes: 0 = success, 1 = Mongo connection failure.

MONGODB_URL must be set in environment (never passed as CLI flag). In prod it
holds the internal docker hostname (mongodb:27017), so run via the container:
`docker exec pocketquant-app python scripts/audit_bar_quality.py ...`.

Production run order (on the VPS):
    1. docker exec pocketquant-mongodb sh -c 'mongodump \\
          --uri="mongodb://$MONGO_INITDB_ROOT_USERNAME:$MONGO_INITDB_ROOT_PASSWORD@localhost:27017/pocketquant?authSource=admin" \\
          --db=pocketquant --collection=bars --archive' > /opt/pocketquant/bars-$(date +%Y%m%d).archive
    2. docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730    # pre-resync baseline
    3. docker exec pocketquant-app python scripts/resync_2y_from_binance.py --days 730 --dry-run
    4. docker exec pocketquant-app python scripts/resync_2y_from_binance.py --days 730
    5. docker exec pocketquant-app python scripts/audit_bar_quality.py --days 730    # post-resync comparison
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import get_settings
from pocketquant.infrastructure.persistence.mongodb import Database

logger = get_logger("scripts.audit_bar_quality")

# Volume threshold from researcher-02: 1m BTC bars > 5000 BTC/bar treated abnormal
ABNORMAL_VOLUME_THRESHOLD = 5_000.0

_REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--days", type=int, default=730, help="Lookback window in days (default 730)"
    )
    parser.add_argument("--symbol", default=None, help="Filter to single symbol, e.g. BTCUSDT")
    parser.add_argument("--exchange", default=None, help="Filter to single exchange, e.g. BINANCE")
    parser.add_argument(
        "--output",
        default=None,
        help="Output Markdown path (default plans/reports/audit-YYYYMMDD-bar-quality.md)",
    )
    return parser.parse_args(argv)


def _build_pipeline(
    start_dt: datetime,
    end_dt: datetime,
    symbol: str | None,
    exchange: str | None,
) -> list[dict]:
    """Build MongoDB aggregation pipeline for bar quality metrics."""
    match_filter: dict = {"datetime": {"$gte": start_dt, "$lt": end_dt}}
    if symbol:
        match_filter["symbol"] = symbol.upper()
    if exchange:
        match_filter["exchange"] = exchange.upper()

    return [
        {"$match": match_filter},
        {
            "$group": {
                "_id": {
                    "symbol": "$symbol",
                    "exchange": "$exchange",
                    "interval": "$interval",
                },
                "total": {"$sum": 1},
                "flat_bars": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$eq": ["$open", "$high"]},
                                    {"$eq": ["$open", "$low"]},
                                    {"$eq": ["$open", "$close"]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "zero_volume": {"$sum": {"$cond": [{"$eq": ["$volume", 0]}, 1, 0]}},
                "abnormal_volume": {
                    "$sum": {"$cond": [{"$gt": ["$volume", ABNORMAL_VOLUME_THRESHOLD]}, 1, 0]}
                },
            }
        },
        {"$sort": {"_id.exchange": 1, "_id.symbol": 1, "_id.interval": 1}},
    ]


def _render_markdown(rows: list[dict], start_dt: datetime, end_dt: datetime, days: int) -> str:
    """Render aggregation results as Markdown table."""
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Bar Quality Audit",
        "",
        f"- **Generated:** {generated}",
        f"- **Window:** {start_dt.date()} → {end_dt.date()} ({days}d)",
        f"- **Abnormal volume threshold:** >{ABNORMAL_VOLUME_THRESHOLD} (base asset / bar)",
        "",
        "| Symbol | Exchange | Interval | Total | Flat | Flat% "
        "| ZeroVol | ZeroVol% | AbnormalVol |",
        "|--------|----------|----------|------:|-----:|------:"
        "|--------:|---------:|------------:|",
    ]

    for row in rows:
        key = row["_id"]
        total = row["total"]
        flat = row["flat_bars"]
        zero = row["zero_volume"]
        abnormal = row["abnormal_volume"]
        flat_pct = f"{flat / total * 100:.1f}%" if total else "N/A"
        zero_pct = f"{zero / total * 100:.1f}%" if total else "N/A"
        lines.append(
            f"| {key['symbol']} | {key['exchange']} | {key['interval']} "
            f"| {total:,} | {flat:,} | {flat_pct} | {zero:,} | {zero_pct} | {abnormal:,} |"
        )

    if not rows:
        lines.append("| — | — | — | — | — | — | — | — | — |")

    return "\n".join(lines) + "\n"


async def run_audit(args: argparse.Namespace) -> int:
    settings = get_settings()
    setup_logging(settings)

    end_dt = datetime.now(UTC).replace(second=0, microsecond=0)
    start_dt = end_dt - timedelta(days=args.days)

    logger.info(
        "audit.start",
        days=args.days,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
    )

    db = Database()
    try:
        await db.connect(settings)
    except Exception as exc:
        logger.error("audit.mongo_connection_failed", error=str(exc))
        return 1

    try:
        collection = db.get_collection("bars")
        pipeline = _build_pipeline(start_dt, end_dt, args.symbol, args.exchange)
        # pymongo 4.16: aggregate() is a coroutine that returns AsyncCommandCursor.
        # Stubs are wrong (show it as non-awaitable) — suppress false positive.
        cursor = await collection.aggregate(pipeline)  # type: ignore[misc]
        rows: list[dict] = [doc async for doc in cursor]
        logger.info("audit.aggregation_complete", row_count=len(rows))
    except Exception as exc:
        logger.error("audit.aggregation_failed", error=str(exc))
        await db.disconnect()
        return 1

    await db.disconnect()

    md_content = _render_markdown(rows, start_dt, end_dt, args.days)

    date_str = datetime.now(UTC).strftime("%Y%m%d")
    output_path = (
        Path(args.output)
        if args.output
        else _REPO_ROOT / "plans" / "reports" / f"audit-{date_str}-bar-quality.md"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # encoding pinned: report contains non-ASCII (→) that crashes on Windows cp1252 default
    output_path.write_text(md_content, encoding="utf-8")
    logger.info("audit.report_saved", path=str(output_path))

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_audit(args))


if __name__ == "__main__":
    sys.exit(main())
