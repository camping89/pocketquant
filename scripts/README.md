# scripts/

> **Scope:** Data-ops scripts (audit, backfill). NOT deployment.
> For deployment, see `.github/workflows/cicd.yml` (CI/CD pipeline) + `deploy/vps/` (VPS-side scripts called by the pipeline).

Operational scripts. Run from repository root.

- `audit_bar_quality.py` — diagnostic, no writes. Flat-bar / zero-volume / abnormal-volume sweep across tracked symbols, outputs Markdown report.
- `backfill/binance_bars.py` — fetch OHLCV bars from Binance klines. Targeted (`--symbol` + explicit `--start/--end` window, insert-only gap-fill) or bulk (all tracked symbols, rolling `--days` window, optional `--replace` delete + cascade-rebuild, resumable via checkpoint). Test beside it (`backfill/test_binance_bars.py`) runs via `pytest scripts/backfill/`, excluded from the default suite.

## Conventions

- All scripts read `MONGODB_URL` (and related secrets) from environment — never CLI flags.
- Diagnostic / dry-run by default where applicable; explicit flag required for destructive writes.
- One-time migrations are not retained here once executed in production — they live only in the git history of the plans/PR that introduced them.
