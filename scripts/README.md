# scripts/

> **Scope:** Data-ops scripts (audit, backfill) and the code metric gate. NOT deployment.
> For deployment, see `.github/workflows/cicd.yml` (CI/CD pipeline) + `deploy/vps/` (VPS-side scripts called by the pipeline).

Operational scripts. Run from repository root. Each script's `--help` owns its flags, defaults and usage notes.

- `audit_bar_quality.py` — diagnostic, no writes.
- `migrate_symbol_asset_class.py` — one-time symbol migration. Dry-run by default.
- `seed_exness_symbols.py` — seeds the Exness symbols. Dry-run by default. Run it before the first sync reaches these symbols.
- `code_metrics.py` — CI gate, no writes. The ceiling is `[tool.code-metrics]` in `pyproject.toml`.
- `backfill/binance_bars.py` — Binance kline backfill. Its test runs via `pytest scripts/backfill/` and is excluded from the default suite.
- `backfill/provider_bars.py` — deep history for one composite symbol through the provider its suffix names.

## Conventions

- All scripts read `MONGODB_URL` (and related secrets) from environment — never CLI flags.
- Diagnostic / dry-run by default where applicable; explicit flag required for destructive writes.
- One-time migrations are not retained here once executed in production — they live only in the git history of the plans/PR that introduced them.
