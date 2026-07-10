"""Recompute finished backtest runs at a target slippage.

Re-executes existing runs through the backtest engine at ``--slippage-bps`` and
overwrites the same run_id in place. The engine is the source of truth: slippage
is baked into every fill price and propagates into PnL, equity curve, Sharpe,
drawdown and profit factor, so only a full replay yields internally-consistent
metrics — hand-patching stored metrics is not correct.

Each run inherits its own ``config_snapshot`` (symbol/interval/range/params);
only ``slippage_bps`` is overridden. Orders/trades are deleted before the replay
(save is upsert-by-fresh-id, so stale docs would otherwise linger) and the
display ``name`` is restored afterwards (the engine writes the config name, not
the label). A built-in verification asserts slippage math, gross-PnL identity
and order/trade count consistency per run.

Usage:
    uv run python scripts/recompute_backtest_slippage.py --run-id <id> [--run-id <id> ...]
    uv run python scripts/recompute_backtest_slippage.py --all-finished [--dry-run]

Selection:
    --all-finished    all runs with status=finished AND slippage_bps != target
    --run-id          explicit id(s), repeatable; recomputed regardless of slippage

A run whose config_snapshot predates the isoformat-string date shape, or whose
bars for the snapshot range are gone, surfaces as a per-run error/degenerate
result (not a silent pass) — see the verification below.

Idempotent: delete-then-replay is repeatable, so a failed run can be re-run
safely. Per-run failures are isolated (one bad run does not abort the batch) and
listed in the summary; exit is non-zero if any run failed.

Exit codes: 0 = all target runs recomputed + verified; 1 = one or more runs
failed or failed verification; 2 = bad invocation / MONGODB_URL unset.

MONGODB_URL must be set in environment (never a CLI flag). The per-run save is
~26k individual upserts, ~26 min/run over the remote VPS link but seconds
against local Mongo — run inside the app container on the VPS:
`docker exec pocketquant-app python scripts/recompute_backtest_slippage.py ...`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from pydantic import ValidationError

from pocketquant.core.common.constants import COLLECTION_BACKTEST_RUNS
from pocketquant.core.common.logging import get_logger, setup_logging
from pocketquant.core.config import Settings, get_settings
from pocketquant.core.domain.backtest import BacktestResult
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.backtest.backtest_dispatch import BacktestDispatchDeps, run_single

logger = get_logger("scripts.recompute_backtest_slippage")

# Verification tolerances / sample sizes.
_REL_TOL = 1e-4          # relative error on price/PnL identities
_TP_PROXIMITY = 1e-3     # exit within 0.1% of raw TP counts as a TP-hit exit
_PNL_SAMPLE = 20         # trades to check gross-PnL identity on


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=None,
        dest="run_ids",
        help="Explicit run id to recompute (repeatable). Mutually exclusive with --all-finished.",
    )
    parser.add_argument(
        "--all-finished",
        action="store_true",
        help="Recompute every finished run whose slippage_bps != target.",
    )
    parser.add_argument(
        "--slippage-bps",
        type=float,
        default=0.5,
        help="Target slippage in basis points (default 0.5).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the target runs + planned actions and exit without mutating.",
    )
    return parser.parse_args(argv)


async def _select_run_ids(db: Database, args: argparse.Namespace) -> list[str]:
    """Resolve the target run ids from explicit --run-id or the --all-finished filter."""
    if args.run_ids:
        return list(dict.fromkeys(args.run_ids))  # de-dup, preserve order

    collection = db.get_collection(COLLECTION_BACKTEST_RUNS)
    cursor = collection.find(
        {"status": "finished", "config_snapshot.slippage_bps": {"$ne": args.slippage_bps}},
        {"_id": 1},
    ).sort("started_at", 1)
    return [doc["_id"] async for doc in cursor]


def _verify(
    target: float,
    before: BacktestResult,
    after: BacktestResult,
    trades: list[Any],
    order_count: int,
) -> list[str]:
    """Return a list of verification failures (empty = all checks passed)."""
    failures: list[str] = []

    snap_slip = after.config_snapshot.get("slippage_bps")
    if snap_slip != target:
        failures.append(f"config_snapshot.slippage_bps={snap_slip} != target {target}")
    if after.status != "finished":
        failures.append(f"status={after.status} != finished")

    # A replay that produced no trades where the original had some means the bars
    # were gone or the engine failed mid-run — and the original was already
    # overwritten. Flag it loudly (re-run at the old slippage restores from bars).
    if before.metrics.total_trades > 0 and after.metrics.total_trades == 0:
        failures.append(
            f"degenerate replay: before={before.metrics.total_trades} trades, after=0 "
            "(missing bars or engine failure; original overwritten — re-run to restore)"
        )

    total_trades = after.metrics.total_trades
    if total_trades != len(trades):
        failures.append(f"metrics.total_trades={total_trades} != {len(trades)} trade docs")
    # Orders can outnumber 2×trades (open-at-end entries, expired/rejected orders,
    # partial exits), so only the floor is invariant: every trade has ≥1 order.
    if trades and order_count == 0:
        failures.append(f"{len(trades)} trades but 0 order docs")

    # TP-exit slippage math: exit fills at TP get slippage applied against the
    # exit side (LONG exits SELL → tp·(1−s); SHORT exits BUY → tp·(1+s)). Identify
    # a TP-hit exit by proximity to the raw TP (slippage ≪ the SL/TP gap), then
    # require every such exit to match the slippage-adjusted price exactly.
    s = target / 1e4
    tp_exits = 0
    tp_matched = 0
    for t in trades:
        if t.tp_price is None or t.tp_price <= 0:
            continue
        if abs(t.exit_price - t.tp_price) > _TP_PROXIMITY * t.tp_price:
            continue
        tp_exits += 1
        expected = t.tp_price * (1 - s) if t.direction == "LONG" else t.tp_price * (1 + s)
        if abs(t.exit_price - expected) <= _REL_TOL * max(abs(expected), 1.0):
            tp_matched += 1
    if tp_exits and tp_matched != tp_exits:
        failures.append(f"TP-exit slippage math: only {tp_matched}/{tp_exits} TP exits matched")

    # Gross-PnL identity: pnl == sign·(exit − entry)·qty (commission tracked
    # separately; stored pnl is gross).
    for t in trades[:_PNL_SAMPLE]:
        sign = 1.0 if t.direction == "LONG" else -1.0
        expected_pnl = sign * (t.exit_price - t.entry_price) * t.quantity
        if abs(t.pnl - expected_pnl) > _REL_TOL * max(abs(expected_pnl), 1.0):
            failures.append(
                f"gross-PnL mismatch trade {t.trade_id}: pnl={t.pnl} != {expected_pnl}"
            )
            break

    return failures


async def _recompute_one(
    deps: BacktestDispatchDeps,
    run_repo: BacktestRepository,
    order_repo: BacktestOrderRepository,
    trade_repo: BacktestTradeRepository,
    run_id: str,
    target: float,
    dry_run: bool,
) -> dict[str, Any]:
    """Recompute a single run; returns a summary row (never raises)."""
    row: dict[str, Any] = {"run_id": run_id, "status": "pending", "failures": []}
    try:
        before = await run_repo.get(run_id)
        if before is None:
            row["status"] = "missing"
            row["failures"] = ["run not found"]
            return row

        old_slip = before.config_snapshot.get("slippage_bps")
        row["before"] = {
            "slippage_bps": old_slip,
            "total_return": before.metrics.total_return,
            "sharpe": before.metrics.sharpe_ratio,
            "trades": before.metrics.total_trades,
            "name": before.name,
        }

        if dry_run:
            row["status"] = "dry-run"
            return row

        # Fresh ids on replay → stale orders/trades must be cleared first, then
        # replayed immediately. A delete-then-failed-replay leaves the run stale
        # or empty; the degenerate-replay check flags it and the caller re-runs
        # that id (idempotent).
        await order_repo.delete_by_run(run_id)
        await trade_repo.delete_by_run(run_id)

        payload = {**before.config_snapshot, "slippage_bps": target}
        await run_single(deps, payload, run_id=run_id)
        await run_repo.set_name(run_id, before.name)  # engine wrote config name, not the label

        after = await run_repo.get(run_id)
        if after is None:
            row["status"] = "error"
            row["failures"] = ["run doc missing after replay"]
            return row
        trades = await trade_repo.list_by_run(run_id)
        orders = await order_repo.list_by_run(run_id)
        failures = _verify(target, before, after, trades, len(orders))

        row["after"] = {
            "slippage_bps": after.config_snapshot.get("slippage_bps"),
            "total_return": after.metrics.total_return,
            "sharpe": after.metrics.sharpe_ratio,
            "trades": after.metrics.total_trades,
        }
        row["failures"] = failures
        row["status"] = "ok" if not failures else "verify-failed"
        if failures:
            logger.error("recompute.verify_failed", run_id=run_id, failures=failures)
    except Exception as exc:  # per-run isolation: one bad run must not abort the batch
        row["status"] = "error"
        row["failures"] = [f"{type(exc).__name__}: {exc}"]
        logger.error("recompute.run_failed", run_id=run_id, error=str(exc), exc_info=True)
    return row


def _print_summary(rows: list[dict[str, Any]], target: float) -> None:
    print(f"\n=== Recompute summary (target slippage {target} bps) ===")
    for r in rows:
        rid = r["run_id"]
        status = r["status"]
        if "before" in r and "after" in r:
            b, a = r["before"], r["after"]
            print(
                f"[{status:>13}] {rid}  "
                f"slip {b['slippage_bps']}→{a['slippage_bps']}  "
                f"ret {b['total_return']:.4f}→{a['total_return']:.4f}  "
                f"sharpe {b['sharpe']:.3f}→{a['sharpe']:.3f}  "
                f"trades {b['trades']}→{a['trades']}"
            )
        elif "before" in r:
            b = r["before"]
            print(
                f"[{status:>13}] {rid}  slip {b['slippage_bps']}→{target}  "
                f"ret {b['total_return']:.4f}  sharpe {b['sharpe']:.3f}  trades {b['trades']}  "
                f"(name={b['name']!r})"
            )
        else:
            print(f"[{status:>13}] {rid}")
        for f in r["failures"]:
            print(f"                  ! {f}")


async def run_recompute(args: argparse.Namespace) -> int:
    if args.run_ids and args.all_finished:
        logger.error(
            "recompute.bad_args", reason="--run-id and --all-finished are mutually exclusive"
        )
        return 2
    if not args.run_ids and not args.all_finished:
        logger.error("recompute.bad_args", reason="pass --run-id or --all-finished")
        return 2

    try:
        settings: Settings = get_settings()
    except ValidationError as exc:
        # Most commonly MONGODB_URL unset (mongodb_url is a required setting).
        logger.error("recompute.settings_invalid", error=str(exc))
        return 2
    setup_logging(settings)

    db = Database()
    try:
        await db.connect(settings)
    except Exception as exc:
        logger.error("recompute.mongo_connection_failed", error=str(exc))
        return 2

    try:
        run_ids = await _select_run_ids(db, args)
        if not run_ids:
            logger.info("recompute.no_targets", all_finished=args.all_finished)
            print("No target runs matched the selection.")
            return 0

        logger.info(
            "recompute.start",
            targets=len(run_ids),
            slippage_bps=args.slippage_bps,
            dry_run=args.dry_run,
        )

        run_repo = BacktestRepository(db)
        order_repo = BacktestOrderRepository(db)
        trade_repo = BacktestTradeRepository(db)
        bar_repo = BarRepository(db)
        deps = BacktestDispatchDeps(
            bar_repo=bar_repo,
            backtest_repo=run_repo,
            order_repo=order_repo,
            trade_repo=trade_repo,
        )

        rows: list[dict[str, Any]] = []
        for run_id in run_ids:
            rows.append(
                await _recompute_one(
                    deps, run_repo, order_repo, trade_repo,
                    run_id, args.slippage_bps, args.dry_run,
                )
            )
    finally:
        await db.disconnect()

    _print_summary(rows, args.slippage_bps)

    if args.dry_run:
        return 0
    failed = [r for r in rows if r["status"] not in ("ok", "dry-run")]
    if failed:
        logger.error("recompute.completed_with_failures", failed=len(failed), total=len(rows))
        return 1
    logger.info("recompute.completed", total=len(rows))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run_recompute(args))


if __name__ == "__main__":
    sys.exit(main())
