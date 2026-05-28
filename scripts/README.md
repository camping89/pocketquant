# scripts/

> **Scope:** Data-ops scripts (audit, backfill, resync). NOT deployment.
> For deployment, see `.github/workflows/cicd.yml` (CI/CD pipeline) + `deploy/vps/` (VPS-side scripts called by the pipeline).

Operational scripts. Run from repository root.

- `audit_bar_quality.py` — diagnostic, no writes. Flat-bar / zero-volume / abnormal-volume sweep across tracked symbols, outputs Markdown report.
- `backfill_1m_from_binance.py` — backfill missing 1m bars.
- `backfill_regression_window.py` — backfill specific date ranges.
- `resync_2y_from_binance.py` — resync 2-year history per symbol.

## Conventions

- All scripts read `MONGODB_URL` (and related secrets) from environment — never CLI flags.
- Diagnostic / dry-run by default where applicable; explicit flag required for destructive writes.
- One-time migrations are not retained here once executed in production — they live only in the git history of the plans/PR that introduced them.
