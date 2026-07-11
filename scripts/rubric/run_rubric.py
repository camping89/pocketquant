"""Rubric CLI — load → metric → score → render → (optional) persist.

Runs the full offline rubric over one or all finished runs and writes four
artifacts (comparison md, per-run scorecards md, json, html) into ``--out``.
``--dry-run`` is the default and mutates nothing; ``--persist`` writes an
idempotent top-level ``scorecard`` field on each canonical run doc.

Usage:
    uv run python scripts/rubric/run_rubric.py --all-finished
    uv run python scripts/rubric/run_rubric.py --run-id <id> [--run-id <id> ...]
    uv run python scripts/rubric/run_rubric.py --all-finished --persist

MONGODB_URL must be set in the environment (never a CLI flag). Read-only by
default; persist only touches the new ``scorecard`` field — never ``verdict``,
``metrics``, ``equity_curve`` or ``config_snapshot``.

Exit codes: 0 = all selected runs scored; 1 = one or more runs failed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

import numpy as np
from pymongo import MongoClient

# Run directly (``uv run python scripts/rubric/run_rubric.py``) puts this file's
# dir on sys.path[0], not the repo root, so the ``scripts`` package is not
# importable. Insert the repo root (two levels up) before the package imports —
# these imports sit after the bootstrap by necessity (E402 suppressed).
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.rubric.data_access import (  # noqa: E402
    dedup_runs,
    list_finished_runs,
    load_bars,
    load_run,
    load_trades,
)
from scripts.rubric.empirical_metrics import compute_metrics  # noqa: E402
from scripts.rubric.render_html import render_html  # noqa: E402
from scripts.rubric.render_markdown import (  # noqa: E402
    render_comparison_table,
    render_scorecards_document,
)
from scripts.rubric.robustness import compute_robustness  # noqa: E402
from scripts.rubric.scoring import RUBRIC_VERSION, score_run  # noqa: E402
from scripts.rubric.static_audit import audit_strategy  # noqa: E402
from scripts.rubric.trade_path_analysis import compute_excursions  # noqa: E402
from scripts.rubric.types import ScorecardResult  # noqa: E402

_DEFAULT_OUT = "scripts/rubric/output"
_CAVEAT = (
    "Thresholds derive from equity/daily research; on 1m crypto they are "
    "directional references. Scores describe run health, not future performance."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--run-id", action="append", dest="run_ids", default=None)
    p.add_argument("--all-finished", action="store_true")
    p.add_argument("--out", default=_DEFAULT_OUT)
    p.add_argument("--persist", action="store_true", help="Write scorecard field (opt-in).")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Force no DB writes even if --persist is passed. Redundant by "
        "default (writes require --persist), but explicit and overriding.",
    )
    p.add_argument("--seed", type=int, default=12345)
    return p.parse_args(argv)


def _score_one(canonical: str, aliases: list[str], seed: int) -> ScorecardResult:
    """Full pipeline for one canonical run."""
    run = load_run(canonical)
    trades = load_trades(canonical)
    metrics = compute_metrics(run, trades)

    net_pnls = np.array([t.pnl - t.commission for t in trades], dtype=float)
    returns = np.array(
        [
            (t.pnl - t.commission) / (t.entry_price * t.quantity)
            for t in trades
            if t.entry_price * t.quantity
        ],
        dtype=float,
    )
    robustness = compute_robustness(
        run.metrics, returns, net_pnls, run.initial_capital, seed=seed
    )

    if trades:
        window_start = min(t.entry_time for t in trades)
        window_end = max(t.exit_time for t in trades)
        bars = load_bars(run.symbol, run.interval, window_start, window_end)
    else:
        bars = np.empty(0)
    excursions = compute_excursions(trades, bars)

    audit = audit_strategy(run.strategy_code)
    return score_run(
        run_id=canonical,
        strategy_code=run.strategy_code,
        symbol=run.symbol,
        interval=run.interval,
        name=run.name,
        metrics=metrics,
        robustness=robustness,
        excursions=excursions,
        audit=audit,
        aliases=aliases,
    )


def _write_artifacts(results: list[ScorecardResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.md").write_text(render_comparison_table(results))
    (out_dir / "scorecards.md").write_text(render_scorecards_document(results))
    (out_dir / "scorecards.html").write_text(render_html(results))
    payload = {
        "rubric_version": RUBRIC_VERSION,
        "caveat": _CAVEAT,
        "runs": [dataclasses.asdict(r) for r in results],
    }
    (out_dir / "scorecards.json").write_text(
        json.dumps(payload, default=str, indent=2)
    )


def _scorecard_doc(result: ScorecardResult) -> dict:
    """The nested ``scorecard`` object persisted on the canonical run doc."""
    return {
        "rubric_version": result.rubric_version,
        "generated_note": _CAVEAT,
        "axes": {
            name: {"score": ax.score, "grade": ax.grade, "breakdown": ax.breakdown}
            for name, ax in result.axes.items()
        },
        "overall_score": result.overall_score,
        "overall_grade": result.overall_grade,
        "metrics": result.metrics,
        "reconciliation": result.reconciliation,
        "excursions": result.excursions,
        "audit": result.audit,
        "diagnosis": result.diagnosis,
        "aliases": result.aliases,
    }


def _persist(results: list[ScorecardResult]) -> int:
    """Idempotent ``$set`` of the ``scorecard`` field on canonical + alias-ref.

    Never touches verdict/metrics/equity_curve/config_snapshot. Re-running with
    the same version overwrites the same field (no append). Returns count written.
    """
    url = os.environ.get("MONGODB_URL")
    if not url:
        raise RuntimeError("MONGODB_URL must be set to persist")
    client = MongoClient(url, serverSelectionTimeoutMS=10_000)
    try:
        coll = client[os.environ.get("MONGODB_DATABASE", "pocketquant")]["backtest_runs"]
        written = 0
        for r in results:
            coll.update_one(
                {"_id": r.run_id}, {"$set": {"scorecard": _scorecard_doc(r)}}
            )
            written += 1
            for alias in r.aliases:
                coll.update_one(
                    {"_id": alias},
                    {
                        "$set": {
                            "scorecard": {
                                "rubric_version": r.rubric_version,
                                "canonical_ref": r.run_id,
                            }
                        }
                    },
                )
                written += 1
        return written
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.run_ids and args.all_finished:
        print("error: --run-id and --all-finished are mutually exclusive", file=sys.stderr)
        return 1
    if not args.run_ids and not args.all_finished:
        print("error: pass --run-id or --all-finished", file=sys.stderr)
        return 1

    selection = list(dict.fromkeys(args.run_ids)) if args.run_ids else list_finished_runs()
    canonical_pairs = dedup_runs(selection)
    print(
        f"Selected {len(selection)} run(s) → {len(canonical_pairs)} canonical "
        f"(rubric {RUBRIC_VERSION})."
    )

    results: list[ScorecardResult] = []
    failures: list[tuple[str, str]] = []
    for canonical, aliases in canonical_pairs:
        try:
            result = _score_one(canonical, aliases, args.seed)
            results.append(result)
            print(
                f"  [ok] {result.strategy_code:<28} {canonical[:13]} "
                f"→ {result.overall_grade} ({result.overall_score:.2f})"
            )
        except Exception as exc:  # per-run isolation: one bad run must not abort
            failures.append((canonical, f"{type(exc).__name__}: {exc}"))
            print(f"  [fail] {canonical[:13]}: {exc}", file=sys.stderr)

    if not results:
        print("No runs scored.", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    _write_artifacts(results, out_dir)
    print(f"Wrote 4 artifacts to {out_dir}/")

    should_persist = args.persist and not args.dry_run
    if should_persist:
        written = _persist(results)
        print(f"Persisted scorecard to {written} doc(s) (canonical + alias-ref).")
    elif args.persist and args.dry_run:
        print("--dry-run overrides --persist: no DB writes.")
    else:
        print("Dry-run: no DB writes. Pass --persist to write the scorecard field.")

    for canonical, err in failures:
        print(f"  ! failed: {canonical} — {err}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
