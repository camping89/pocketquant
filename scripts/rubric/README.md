# Backtest Rubric

Offline scorecard that grades every finished backtest run on three axes —
**Performance · Robustness · Design-integrity** → A–F. Reads the stored result,
the trade path, and the strategy source. Read-only by default; the trading path
is never touched.

Full methodology (threshold bands, formulas, caveats): [`docs/backtest-rubric/methodology.md`](../../docs/backtest-rubric/methodology.md).

## Run

```bash
# Score all finished runs → 4 artifacts, no DB writes (default)
uv run python scripts/rubric/run_rubric.py --all-finished

# One or more specific runs
uv run python scripts/rubric/run_rubric.py --run-id <run_id> [--run-id <run_id> ...]

# Write the scorecard field into the DB (opt-in)
uv run python scripts/rubric/run_rubric.py --all-finished --persist
```

`MONGODB_URL` must be in the environment (never a CLI flag). `--dry-run` forces
no writes even if `--persist` is passed.

## Output (`scripts/rubric/output/`, override with `--out`)

| File | Content |
|---|---|
| `comparison.md` | One row per run, ranked weakest-first |
| `scorecards.md` | Per-run breakdown: metrics + reconciliation + MAE/MFE + audit |
| `scorecards.html` | Self-contained, opens via `file://` |
| `scorecards.json` | Machine-readable, versioned |

```bash
open scripts/rubric/output/scorecards.html
```

## Scoring

- Each metric → 0–4 via industry threshold bands.
- metric → axis: weighted sum (N/A metrics dropped, weights re-normalized).
- axis → overall: **min** (weakest-axis dominates — a robustness F drags the
  whole run down even with A-grade performance).
- Grade: A ≥ 3.5, B ≥ 2.5, C ≥ 1.5, D ≥ 0.5, F < 0.5.
- `RUBRIC_VERSION` in `scoring.py`; bump it when any band/weight/formula changes.

## Modules

| File | Role |
|---|---|
| `data_access.py` | Lazy Mongo read: runs, trades, bars, dedup |
| `reconciliation.py` | Planned R:R, realized R-multiple, gross-vs-net edge split |
| `empirical_metrics.py` | Calmar/MAR/Ulcer/tail/SQN/cost-to-edge (reuses `PerformanceCalculatorDomainService`) |
| `robustness.py` | PSR (`math.erf`, no scipy) + sequencing bootstrap |
| `trade_path_analysis.py` | Offline MAE/MFE from bar high/low |
| `static_audit.py` | AST audit of strategy source (DoF, geometry, lookahead) |
| `scoring.py` | Thresholds, weights, grades |
| `render_markdown.py` / `render_html.py` | Artifact renderers |
| `run_rubric.py` | CLI orchestration + persist |

## Notes

- **Connection is lazy** — clients are built inside functions, never at import,
  so pure-math tests import the package without connecting.
- **Persist is scoped** — writes only a new top-level `scorecard` field via
  `$set`; never touches `verdict`/`metrics`/`equity_curve`/`config_snapshot`.
  Idempotent (re-run same version = overwrite).
- **Crypto-1m caveat** — thresholds come from equity/daily research; on 1m crypto
  they are directional references, not calibrated cutoffs.

## Tests

```bash
MONGODB_URL="mongodb://localhost:27017/x" REDIS_URL="redis://localhost:6379/1" \
  uv run python -m pytest tests/scripts/rubric/ -q
```

Pure math, no DB. The local `MONGODB_URL` override is required because the test
prod-guard refuses to run when the env points at production.
