"""One-time idempotent migration: split embedded backtest_runs into 4 collections.

Pre-migration: a single ``backtest_runs`` document embedded every fill
(``trades[]``) and every position (``positions[]``). Post-migration the schema is:
  - ``backtest_runs``        — slim (metrics + equity_curve + open_positions)
  - ``backtest_orders``      — one doc per Order (with embedded events[]+fills[])
  - ``backtest_trades``      — one doc per round-trip Trade (entry + exit)
  - ``backtest_optimization_runs`` — renamed from ``optimization_runs``

This script:
  1. Backs up ``backtest_runs`` and ``optimization_runs`` to
     ``*_backup_YYMMDD`` collections.
  2. Reconstructs orders from each run's old ``trades[]`` (a fill under old
     naming → a MARKET Order with one Fill).
  3. Reconstructs trades from each run's old ``positions[]`` where
     ``exit_time != null``; the rest become ``open_positions``.
  4. Slims the run doc (``$unset`` trades+positions, ``$set`` open_positions
     and the idempotency marker).
  5. Renames ``optimization_runs`` → ``backtest_optimization_runs`` (only if
     destination is empty and source exists).
  6. Verifies residuals; non-zero residual exits non-zero.

Idempotent — re-runs skip already-migrated docs via the
``_migration.v2_storage_split.completed_at`` marker.

Usage:
    python -m scripts.one_time_split_backtest_collections --dry-run
    python -m scripts.one_time_split_backtest_collections --validate-only
    python -m scripts.one_time_split_backtest_collections           # real run
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient
from pymongo.errors import BulkWriteError

MARKER_PATH = "_migration.v2_storage_split.completed_at"


@dataclass
class MigrationStats:
    runs_total: int = 0
    runs_skipped_marker: int = 0
    runs_skipped_running: int = 0
    runs_migrated: int = 0
    orders_extracted: int = 0
    trades_extracted: int = 0
    open_lots: int = 0
    optimization_renamed: bool = False


def _today_yymmdd() -> str:
    return datetime.now(UTC).strftime("%y%m%d")


# ---- per-doc conversion ----------------------------------------------------


def _convert_fills_to_orders(run_doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Old TradeRecord shape → backtest_orders doc (MARKET, FILLED, embedded one fill+events)."""
    run_id = run_doc["_id"]
    strategy_id = run_doc.get("strategy_id") or ""
    snap = run_doc.get("config_snapshot") or {}
    symbol = snap.get("symbol") or run_doc.get("symbol") or ""
    orders: list[dict[str, Any]] = []
    for old_fill in run_doc.get("trades", []) or []:
        if not isinstance(old_fill, dict):
            continue
        ts = old_fill.get("timestamp")
        order_id = old_fill.get("order_id") or str(uuid.uuid4())
        side = (old_fill.get("side") or "BUY").lower()
        if side not in ("buy", "sell"):
            side = "buy"
        orders.append(
            {
                "_id": order_id,
                "run_id": run_id,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "side": side,
                "order_type": "market",  # assumption — pre-migration strategies MARKET-only
                "quantity": old_fill.get("quantity", 0.0),
                "price": None,
                "sl_price": old_fill.get("sl_price"),
                "tp_price": old_fill.get("tp_price"),
                "status": "filled",
                "submitted_at": ts,
                "last_updated_at": ts,
                "events": [
                    {
                        "timestamp": ts,
                        "from_status": None,
                        "to_status": "submitted",
                        "reason": "migrated",
                    },
                    {
                        "timestamp": ts,
                        "from_status": "submitted",
                        "to_status": "filled",
                        "reason": "migrated",
                    },
                ],
                "fills": [
                    {
                        "fill_id": str(uuid.uuid4()),
                        "symbol": symbol,
                        "side": side,
                        "quantity": old_fill.get("quantity", 0.0),
                        "price": old_fill.get("price", 0.0),
                        "commission": old_fill.get("commission", 0.0),
                        "slippage": 0.0,
                        "timestamp": ts,
                    }
                ],
                "resulting_trade_id": None,
            }
        )
    return orders


def _convert_positions_to_trades_and_open_lots(
    run_doc: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Old PositionRecord → (closed trades, open_lots).

    Entry/exit order_id cannot be reconstructed from old PositionRecord shape;
    backfilled as None.
    """
    run_id = run_doc["_id"]
    strategy_id = run_doc.get("strategy_id") or ""
    snap = run_doc.get("config_snapshot") or {}
    symbol_default = snap.get("symbol") or run_doc.get("symbol") or ""
    trades: list[dict[str, Any]] = []
    open_lots: list[dict[str, Any]] = []
    for old_pos in run_doc.get("positions", []) or []:
        if not isinstance(old_pos, dict):
            continue
        symbol = old_pos.get("symbol") or symbol_default
        direction = old_pos.get("direction") or "LONG"
        entry_price = old_pos.get("entry_price", 0.0)
        entry_time = old_pos.get("entry_time")
        quantity = old_pos.get("quantity", 0.0)
        sl_price = old_pos.get("sl_price")
        tp_price = old_pos.get("tp_price")
        exit_price = old_pos.get("exit_price")
        exit_time = old_pos.get("exit_time")
        commission = old_pos.get("commission", 0.0)
        pnl = old_pos.get("pnl", 0.0)

        if exit_price is not None and exit_time is not None:
            duration = 0.0
            if entry_time is not None and hasattr(exit_time, "timestamp"):
                try:
                    duration = (exit_time - entry_time).total_seconds()
                except (TypeError, AttributeError):
                    duration = 0.0
            trades.append(
                {
                    "_id": str(uuid.uuid4()),
                    "run_id": run_id,
                    "strategy_id": strategy_id,
                    "symbol": symbol,
                    "direction": direction,
                    "entry_order_id": None,
                    "entry_price": entry_price,
                    "entry_time": entry_time,
                    "quantity": quantity,
                    "exit_order_id": None,
                    "exit_price": exit_price,
                    "exit_time": exit_time,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "pnl": pnl,
                    "commission": commission,
                    "duration_seconds": duration,
                }
            )
        else:
            open_lots.append(
                {
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": entry_price,
                    "entry_time": entry_time,
                    "quantity": quantity,
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "entry_order_id": None,
                    "entry_commission_portion": commission,
                }
            )
    return trades, open_lots


# ---- per-doc orchestration -------------------------------------------------


async def _migrate_one_run(
    db: AsyncDatabase,
    run_doc: dict[str, Any],
    *,
    dry_run: bool,
    exclude_running: bool,
) -> tuple[str, int, int, int]:
    """Migrate a single run doc. Returns (status, orders_extracted, trades_extracted, open_lots).

    Status: 'migrated' | 'skipped_marker' | 'skipped_running' | 'skipped_empty'.
    """
    run_id = run_doc["_id"]
    marker = (run_doc.get("_migration") or {}).get("v2_storage_split", {}).get("completed_at")
    if marker is not None:
        return ("skipped_marker", 0, 0, 0)

    if exclude_running and run_doc.get("status") == "running":
        return ("skipped_running", 0, 0, 0)

    orders = _convert_fills_to_orders(run_doc)
    trades, open_lots = _convert_positions_to_trades_and_open_lots(run_doc)

    if not orders and not trades and not open_lots:
        # Subscription cache stub / empty doc — only set the marker.
        if not dry_run:
            await db["backtest_runs"].update_one(
                {"_id": run_id},
                {
                    "$set": {
                        "_migration.v2_storage_split": {
                            "completed_at": datetime.now(UTC),
                            "orders_extracted": 0,
                            "trades_extracted": 0,
                            "open_positions": 0,
                        }
                    },
                    "$unset": {"trades": "", "positions": ""},
                },
            )
        return ("skipped_empty", 0, 0, 0)

    if dry_run:
        return ("migrated", len(orders), len(trades), len(open_lots))

    if orders:
        try:
            await db["backtest_orders"].insert_many(orders, ordered=False)
        except BulkWriteError as e:
            # Duplicates from previous partial run are OK — log count.
            print(
                f"WARN: backtest_orders partial insert for run {run_id}: {len(e.details.get('writeErrors', []))} dup",
                file=sys.stderr,
            )
    if trades:
        try:
            await db["backtest_trades"].insert_many(trades, ordered=False)
        except BulkWriteError as e:
            print(
                f"WARN: backtest_trades partial insert for run {run_id}: {len(e.details.get('writeErrors', []))} dup",
                file=sys.stderr,
            )

    await db["backtest_runs"].update_one(
        {"_id": run_id},
        {
            "$set": {
                "open_positions": open_lots,
                "_migration.v2_storage_split": {
                    "completed_at": datetime.now(UTC),
                    "orders_extracted": len(orders),
                    "trades_extracted": len(trades),
                    "open_positions": len(open_lots),
                },
            },
            "$unset": {"trades": "", "positions": ""},
        },
    )
    return ("migrated", len(orders), len(trades), len(open_lots))


# ---- collection-level helpers ---------------------------------------------


async def _backup_collection(db: AsyncDatabase, src: str, dst: str) -> int:
    """Copy src to dst. Skips if src empty or dst already non-empty."""
    src_count = await db[src].count_documents({})
    if src_count == 0:
        return 0
    if await db[dst].count_documents({}) > 0:
        print(f"WARN: backup dst {dst} non-empty; skipping backup", file=sys.stderr)
        return 0
    docs = [doc async for doc in db[src].find({})]
    if docs:
        await db[dst].insert_many(docs, ordered=False)
    return len(docs)


async def _rename_optimization_collection(db: AsyncDatabase) -> bool:
    """Rename `optimization_runs` → `backtest_optimization_runs` if conditions met."""
    names = await db.list_collection_names()
    src = "optimization_runs"
    dst = "backtest_optimization_runs"
    if src not in names:
        return False  # nothing to rename
    if dst in names and await db[dst].count_documents({}) > 0:
        print(f"INFO: {dst} already exists with data; skipping rename", file=sys.stderr)
        return False
    # If dst exists empty, drop it first so renameCollection can proceed.
    if dst in names:
        await db[dst].drop()
    db_name = db.name
    await db.client.admin.command(
        {"renameCollection": f"{db_name}.{src}", "to": f"{db_name}.{dst}"}
    )
    return True


# ---- residual verification -------------------------------------------------


async def _verify(db: AsyncDatabase) -> dict[str, int | bool]:
    """Post-migration sanity check. Returns metrics dict."""
    legacy = await db["backtest_runs"].count_documents(
        {"$or": [{"trades": {"$exists": True}}, {"positions": {"$exists": True}}]}
    )
    unmigrated = await db["backtest_runs"].count_documents({MARKER_PATH: {"$exists": False}})
    orders_count = await db["backtest_orders"].count_documents({})
    trades_count = await db["backtest_trades"].count_documents({})
    names = await db.list_collection_names()
    return {
        "legacy_field_count": legacy,
        "unmigrated_count": unmigrated,
        "orders_count": orders_count,
        "trades_count": trades_count,
        "legacy_optimization_collection_exists": "optimization_runs" in names,
        "new_optimization_collection_exists": "backtest_optimization_runs" in names,
    }


# ---- top-level orchestration ----------------------------------------------


async def run(
    *,
    mongo_uri: str,
    db_name: str,
    dry_run: bool,
    exclude_running: bool,
    validate_only: bool,
) -> MigrationStats:
    """Top-level entrypoint. Returns aggregate stats."""
    client = AsyncMongoClient(mongo_uri)
    stats = MigrationStats()
    try:
        db = client[db_name]

        if validate_only:
            residuals = await _verify(db)
            print("validate_only", residuals)
            return stats

        # 1. Backup
        if not dry_run:
            today = _today_yymmdd()
            n1 = await _backup_collection(db, "backtest_runs", f"backtest_runs_backup_{today}")
            n2 = await _backup_collection(
                db, "optimization_runs", f"optimization_runs_backup_{today}"
            )
            print(f"BACKUP backtest_runs={n1} optimization_runs={n2}")

        # 2. Per-run extraction + slim
        cursor = db["backtest_runs"].find(
            {} if exclude_running is False else {"status": {"$ne": "running"}}
        )
        async for run_doc in cursor:
            stats.runs_total += 1
            status, n_orders, n_trades, n_open = await _migrate_one_run(
                db, run_doc, dry_run=dry_run, exclude_running=exclude_running
            )
            if status == "migrated":
                stats.runs_migrated += 1
                stats.orders_extracted += n_orders
                stats.trades_extracted += n_trades
                stats.open_lots += n_open
            elif status == "skipped_marker":
                stats.runs_skipped_marker += 1
            elif status == "skipped_running":
                stats.runs_skipped_running += 1

        # 3. Optimization rename
        if not dry_run:
            stats.optimization_renamed = await _rename_optimization_collection(db)

        # 4. Residual verification
        residuals = await _verify(db)
        print(
            f"DONE runs_total={stats.runs_total} migrated={stats.runs_migrated} "
            f"skipped_marker={stats.runs_skipped_marker} skipped_running={stats.runs_skipped_running} "
            f"orders={stats.orders_extracted} trades={stats.trades_extracted} "
            f"open_lots={stats.open_lots} optimization_renamed={stats.optimization_renamed} "
            f"residuals={residuals} dry_run={dry_run}"
        )

        if not dry_run and residuals["legacy_field_count"] > 0:
            print("ERROR: residual legacy fields > 0", file=sys.stderr)
            sys.exit(1)
        return stats
    finally:
        await client.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGODB_URL"))
    parser.add_argument("--db-name", default=os.environ.get("MONGODB_DATABASE", "pocketquant"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--no-exclude-running",
        action="store_true",
        help="Also migrate docs with status=='running' (default: skip them).",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run residual verification only; no writes.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not args.mongo_uri:
        print("ERROR: --mongo-uri or MONGODB_URL env var is required.", file=sys.stderr)
        sys.exit(2)
    asyncio.run(
        run(
            mongo_uri=args.mongo_uri,
            db_name=args.db_name,
            dry_run=args.dry_run,
            exclude_running=not args.no_exclude_running,
            validate_only=args.validate_only,
        )
    )


if __name__ == "__main__":
    main()
