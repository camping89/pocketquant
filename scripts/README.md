# scripts/

> **Scope:** Data-ops scripts (audit, backfill) and the code metric gate. NOT deployment.
> For deployment, see `.github/workflows/cicd.yml` (CI/CD pipeline) + `deploy/vps/` (VPS-side scripts called by the pipeline).

Operational scripts. Run from repository root.

- `audit_bar_quality.py` — diagnostic, no writes. Flat-bar / zero-volume / abnormal-volume sweep across tracked symbols, outputs Markdown report.
- `migrate_symbol_asset_class.py` — one-time. Stamps pre-asset-class symbol documents with
  `asset_class`/`calendar_id`/`contract_spec` and drops `asset_type`. Dry-run by default;
  `--apply` writes. Idempotent — skips documents that already carry `asset_class`.
- `seed_exness_symbols.py` — seeds `XAUUSD:EXNESS`, `EURUSD:EXNESS` and `BTCUSD:EXNESS` into
  `symbols` + `tracked_symbols` with `asset_class=cfd`, each instrument's session calendar and tick
  size. Dry-run by default; `--apply` writes. Idempotent. Run it before the first sync reaches these
  symbols.
- `code_metrics.py` — CI gate, no writes. Measures tiny functions and pure delegations over `src/pocketquant`; `--ratchet` fails when either is above the ceiling in `[tool.code-metrics]` of `pyproject.toml`. Tests: `tests/scripts/test_code_metrics.py`.
- `backfill/binance_bars.py` — fetch OHLCV bars from Binance klines. Targeted (`--symbol` + explicit `--start/--end` window, insert-only gap-fill) or bulk (all tracked symbols, rolling `--days` window, optional `--replace` delete + cascade-rebuild, resumable via checkpoint). Test beside it (`backfill/test_binance_bars.py`) runs via `pytest scripts/backfill/`, excluded from the default suite.
- `backfill/provider_bars.py` — deep history for one composite symbol through the routed data provider its suffix names (`--symbol XAUUSD:EXNESS --interval 1m --days 30`), beyond the 5000-bar request cap. Uses `--rate-fraction` (default 0.5) of the Exness request rate, refuses while `EXNESS_LIVE_TRADING` is true, `--dry-run` writes nothing. Tests: `tests/scripts/test_provider_bars.py`.

## Conventions

- All scripts read `MONGODB_URL` (and related secrets) from environment — never CLI flags.
- Diagnostic / dry-run by default where applicable; explicit flag required for destructive writes.
- One-time migrations are not retained here once executed in production — they live only in the git history of the plans/PR that introduced them.
