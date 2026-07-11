"""Markdown renderers: a cross-run comparison table and a per-run scorecard.

Both carry the rubric version and the crypto-1m caveat in their header. The
comparison table ranks runs by overall score (weakest first surfaces the
sickest run). Number formatting tolerates None (metric N/A).
"""

from __future__ import annotations

from scripts.rubric.scoring import RUBRIC_VERSION
from scripts.rubric.types import ScorecardResult

_CAVEAT = (
    "Thresholds derive from equity/daily research; on 1m crypto they are "
    "directional references, not calibrated cutoffs. Scores describe run "
    "health, not future performance."
)


def _fmt(value: object, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _header(title: str) -> str:
    return (
        f"# {title}\n\n"
        f"`RUBRIC_VERSION = {RUBRIC_VERSION}`\n\n"
        f"> **Caveat.** {_CAVEAT}\n"
    )


def render_comparison_table(results: list[ScorecardResult]) -> str:
    """One row per run, ranked by overall score (weakest first)."""
    ranked = sorted(results, key=lambda r: r.overall_score)
    lines = [
        _header("Backtest Rubric — Comparison"),
        "",
        "| Rank | Strategy | Symbol/Interval | Performance | Robustness | "
        "Design-integrity | Overall | Diagnosis |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked, 1):
        a = r.axes
        lines.append(
            f"| {i} | {r.strategy_code} | {r.symbol} {r.interval} | "
            f"{a['performance'].grade} ({_fmt(a['performance'].score, 2)}) | "
            f"{a['robustness'].grade} ({_fmt(a['robustness'].score, 2)}) | "
            f"{a['design_integrity'].grade} ({_fmt(a['design_integrity'].score, 2)}) | "
            f"**{r.overall_grade}** ({_fmt(r.overall_score, 2)}) | {r.diagnosis} |"
        )
    return "\n".join(lines) + "\n"


def render_scorecard(r: ScorecardResult) -> str:
    """Full per-run detail: axis breakdowns, reconciliation, MAE/MFE, audit."""
    lines = [
        f"## {r.strategy_code} — {r.run_id}",
        "",
        f"- **Overall:** {r.overall_grade} ({_fmt(r.overall_score, 2)}) "
        "— weakest-axis minimum",
        f"- **Symbol/Interval:** {r.symbol} {r.interval}",
        f"- **Name:** {r.name or '—'}",
        f"- **Diagnosis:** {r.diagnosis}",
    ]
    if r.aliases:
        lines.append(f"- **Dedup aliases:** {', '.join(r.aliases)}")
    lines.append("")

    for axis_key, axis in r.axes.items():
        lines.append(f"### {axis_key} — {axis.grade} ({_fmt(axis.score, 2)})")
        lines.append("")
        lines.append("| Metric | Value | Points | Weight |")
        lines.append("|---|---|---|---|")
        for b in axis.breakdown:
            pts = "N/A" if b["points"] is None else str(b["points"])
            lines.append(
                f"| {b['metric']} | {_fmt(b['value'])} | {pts} | {_fmt(b['weight'], 2)} |"
            )
        lines.append("")

    recon = r.reconciliation
    lines += [
        "### Reconciliation (design vs realized)",
        "",
        f"- Planned R:R (mean / median): {_fmt(recon.get('planned_rr_mean'))} / "
        f"{_fmt(recon.get('planned_rr_median'))}",
        f"- Realized R-multiple (mean / median): {_fmt(recon.get('realized_r_mean'))} / "
        f"{_fmt(recon.get('realized_r_median'))}",
        f"- Gross edge: {_fmt(recon.get('gross_edge_bps'))} bps · "
        f"Friction: {_fmt(recon.get('friction_bps'))} bps · "
        f"Net edge: {_fmt(recon.get('net_edge_bps'))} bps",
        "",
    ]

    exc = r.excursions
    lines += [
        "### Trade-path MAE/MFE (offline approximation)",
        "",
        f"- MFE capture (winners): {_fmt(exc.get('mfe_capture_mean'))}",
        f"- MAE-to-stop: {_fmt(exc.get('mae_to_stop_mean'))}",
        f"- MAE_R p50/p90: {_fmt(exc.get('mae_r_p50'))} / {_fmt(exc.get('mae_r_p90'))}",
        f"- MFE_R p50/p90: {_fmt(exc.get('mfe_r_p50'))} / {_fmt(exc.get('mfe_r_p90'))}",
        f"- Low coverage: {exc.get('low_coverage')} "
        f"({exc.get('low_coverage_trades')}/{exc.get('total_trades')} trades)",
        "",
    ]

    audit = r.audit
    lines += [
        "### Static audit (strategy definition)",
        "",
        f"- Degrees of freedom: {_fmt(audit.get('degrees_of_freedom'))} "
        f"({', '.join(audit.get('params', [])) or '—'})",
        f"- Direction bias: {audit.get('direction_bias')}",
        f"- SL/TP geometry: {audit.get('sl_tp_geometry')}",
        f"- Entry frequency: {audit.get('entry_frequency_class')}",
        f"- Lookahead safety: {audit.get('lookahead_safety')}",
        "",
    ]
    return "\n".join(lines)


def render_scorecards_document(results: list[ScorecardResult]) -> str:
    """Header + every per-run scorecard concatenated."""
    parts = [_header("Backtest Rubric — Per-run Scorecards"), ""]
    parts += [render_scorecard(r) for r in results]
    return "\n".join(parts)
