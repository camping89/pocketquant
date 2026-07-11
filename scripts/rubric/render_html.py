"""Self-contained HTML report — inline CSS, no framework, opens via file://.

A comparison table (ranked, weakest first) plus a collapsible section per run
with the full breakdown. Grade drives colour (A green → F red). All dynamic text
is escaped. KISS: static editorial + <details>, no chart library.
"""

from __future__ import annotations

import html

from scripts.rubric.scoring import RUBRIC_VERSION
from scripts.rubric.types import ScorecardResult

_CAVEAT = (
    "Thresholds derive from equity/daily research; on 1m crypto they are "
    "directional references, not calibrated cutoffs. Scores describe run health, "
    "not future performance."
)

_GRADE_COLOR = {
    "A": "#1a9850",
    "B": "#66bd63",
    "C": "#fee08b",
    "D": "#fc8d59",
    "F": "#d73027",
}

_CSS = """
:root { font-family: -apple-system, system-ui, sans-serif; }
body { max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a;
  background: #fafafa; line-height: 1.5; }
h1 { margin-bottom: .25rem; }
.version { color: #666; font-family: monospace; }
.caveat { background: #fff3cd; border-left: 4px solid #ffc107; padding: .75rem 1rem;
  border-radius: 4px; margin: 1rem 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; background: #fff; }
th, td { border: 1px solid #ddd; padding: .5rem .6rem; text-align: left; font-size: .9rem; }
th { background: #f0f0f0; }
.grade { font-weight: 700; padding: .1rem .5rem; border-radius: 3px; color: #111; }
details { background: #fff; border: 1px solid #ddd; border-radius: 6px;
  margin: .75rem 0; padding: .5rem 1rem; }
summary { cursor: pointer; font-weight: 600; font-size: 1.05rem; }
.diagnosis { font-style: italic; color: #444; }
.na { color: #999; }
h3 { margin: 1rem 0 .25rem; text-transform: capitalize; }
"""


def _esc(value: object) -> str:
    if value is None:
        return '<span class="na">—</span>'
    if isinstance(value, float):
        return html.escape(f"{value:.3f}")
    return html.escape(str(value))


def _grade_badge(grade: str, score: float) -> str:
    color = _GRADE_COLOR.get(grade, "#ccc")
    return (
        f'<span class="grade" style="background:{color}">'
        f"{html.escape(grade)} ({score:.2f})</span>"
    )


def _comparison_rows(results: list[ScorecardResult]) -> str:
    ranked = sorted(results, key=lambda r: r.overall_score)
    rows = []
    for i, r in enumerate(ranked, 1):
        a = r.axes
        rows.append(
            f"<tr><td>{i}</td><td>{html.escape(r.strategy_code)}</td>"
            f"<td>{html.escape(r.symbol)} {html.escape(r.interval)}</td>"
            f"<td>{_grade_badge(a['performance'].grade, a['performance'].score)}</td>"
            f"<td>{_grade_badge(a['robustness'].grade, a['robustness'].score)}</td>"
            f"<td>{_grade_badge(a['design_integrity'].grade, a['design_integrity'].score)}</td>"
            f"<td>{_grade_badge(r.overall_grade, r.overall_score)}</td>"
            f'<td class="diagnosis">{html.escape(r.diagnosis)}</td></tr>'
        )
    return "\n".join(rows)


def _axis_table(r: ScorecardResult) -> str:
    parts = []
    for axis_key, axis in r.axes.items():
        rows = "".join(
            f"<tr><td>{html.escape(b['metric'])}</td><td>{_esc(b['value'])}</td>"
            f"<td>{'N/A' if b['points'] is None else b['points']}</td>"
            f"<td>{_esc(b['weight'])}</td></tr>"
            for b in axis.breakdown
        )
        parts.append(
            f"<h3>{html.escape(axis_key)} — "
            f"{_grade_badge(axis.grade, axis.score)}</h3>"
            "<table><tr><th>Metric</th><th>Value</th><th>Points</th>"
            f"<th>Weight</th></tr>{rows}</table>"
        )
    return "".join(parts)


def _detail_blocks(r: ScorecardResult) -> str:
    recon, exc, audit = r.reconciliation, r.excursions, r.audit
    recon_html = (
        "<h3>Reconciliation</h3><ul>"
        f"<li>Planned R:R mean/median: {_esc(recon.get('planned_rr_mean'))} / "
        f"{_esc(recon.get('planned_rr_median'))}</li>"
        f"<li>Realized R mean/median: {_esc(recon.get('realized_r_mean'))} / "
        f"{_esc(recon.get('realized_r_median'))}</li>"
        f"<li>Gross {_esc(recon.get('gross_edge_bps'))} bps · "
        f"Friction {_esc(recon.get('friction_bps'))} bps · "
        f"Net {_esc(recon.get('net_edge_bps'))} bps</li></ul>"
    )
    exc_html = (
        "<h3>Trade-path MAE/MFE</h3><ul>"
        f"<li>MFE capture: {_esc(exc.get('mfe_capture_mean'))}</li>"
        f"<li>MAE-to-stop: {_esc(exc.get('mae_to_stop_mean'))}</li>"
        f"<li>MAE_R p50/p90: {_esc(exc.get('mae_r_p50'))} / {_esc(exc.get('mae_r_p90'))}</li>"
        f"<li>Low coverage: {_esc(exc.get('low_coverage'))}</li></ul>"
    )
    audit_html = (
        "<h3>Static audit</h3><ul>"
        f"<li>Degrees of freedom: {_esc(audit.get('degrees_of_freedom'))}</li>"
        f"<li>Direction bias: {_esc(audit.get('direction_bias'))}</li>"
        f"<li>SL/TP geometry: {_esc(audit.get('sl_tp_geometry'))}</li>"
        f"<li>Entry frequency: {_esc(audit.get('entry_frequency_class'))}</li>"
        f"<li>Lookahead safety: {_esc(audit.get('lookahead_safety'))}</li></ul>"
    )
    return recon_html + exc_html + audit_html


def render_html(results: list[ScorecardResult]) -> str:
    details = []
    for r in sorted(results, key=lambda x: x.overall_score):
        alias_note = (
            f" <small>(+{len(r.aliases)} dedup alias)</small>" if r.aliases else ""
        )
        details.append(
            "<details><summary>"
            f"{_grade_badge(r.overall_grade, r.overall_score)} "
            f"{html.escape(r.strategy_code)} — {html.escape(r.run_id)}{alias_note}"
            "</summary>"
            f'<p class="diagnosis">{html.escape(r.diagnosis)}</p>'
            f"{_axis_table(r)}{_detail_blocks(r)}</details>"
        )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Backtest Rubric</title>"
        f"<style>{_CSS}</style></head><body>"
        "<h1>Backtest Rubric</h1>"
        f'<p class="version">RUBRIC_VERSION = {html.escape(RUBRIC_VERSION)}</p>'
        f'<div class="caveat"><strong>Caveat.</strong> {html.escape(_CAVEAT)}</div>'
        "<h2>Comparison (weakest first)</h2>"
        "<table><tr><th>Rank</th><th>Strategy</th><th>Symbol/Interval</th>"
        "<th>Performance</th><th>Robustness</th><th>Design-integrity</th>"
        "<th>Overall</th><th>Diagnosis</th></tr>"
        f"{_comparison_rows(results)}</table>"
        "<h2>Per-run detail</h2>"
        f"{''.join(details)}"
        "</body></html>"
    )
