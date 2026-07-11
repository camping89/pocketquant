# Backtest Rubric Scorecard Module

Built an offline quant-analyst rubric (`scripts/rubric/`) that grades every
finished backtest run on three axes — Performance, Robustness, Design-integrity
— from the stored result, the trade path, and the strategy source. Read-only DB
by default; writes only a new top-level `scorecard` field behind `--persist`.

## What it does

- **Empirical metrics** (quantstats formulas) reusing `PerformanceCalculatorDomainService`
  for profit_factor/drawdown/win-loss; adds Calmar/MAR/Ulcer/UPI/recovery/
  tail_ratio/CSR/CPC/gain_to_pain/SQN/Kelly/RoR/cost_to_edge.
- **Reconciliation**: planned R:R, realized R-multiple, and a gross-vs-net edge
  split (bps) — the split is what separates *cost-killed* from *no-edge*.
- **Robustness**: PSR (`math.erf` normal CDF, no scipy) + a sequencing bootstrap
  over trade order → maxDD percentiles.
- **Trade-path MAE/MFE**: offline excursions from bar high/low between entry/exit.
- **Static AST audit**: degrees of freedom, SL/TP geometry, entry-frequency,
  lookahead safety — parsed from strategy source, never executed.
- **Scoring**: threshold bands → 0-4 per metric → weighted-sum per axis →
  overall = **min of the three axes** (weakest-axis dominates). `RUBRIC_VERSION`
  versioned; `docs/backtest-rubric/methodology.md` documents every band + formula.
- **Renderers**: comparison md, per-run scorecards md, self-contained html, json.

## Findings it reproduced

The rubric independently reproduced the master-report diagnosis on the 6 finished
runs (5 canonical after dedup): `engulfing`/`pullback` = *no directional edge*
(gross ≈ 0 bps), `hitnrun2` = *cost-killed* (gross +5.46 bps, net −1.54, profit
factor 2.12 but cost_to_edge 0.78). Pullback's `mae_to_stop` 0.90 quantifies the
"SL too tight" conclusion; realized R-mean −0.039 and win-rate 42.9% match exactly.

## What was tricky

- **Prod-guard vs lazy connect.** The test conftest refuses to run when
  `MONGODB_URL` points at prod (direnv loads it), so every Mongo client had to be
  built *inside* a function, never at import. Pure-math tests then import the
  package freely; running them still needs a local `MONGODB_URL` override because
  the guard fires at `pytest_configure`, before collection.
- **String config_snapshot.** Every `config_snapshot` value is stored as a string
  (`"10000.0"`, `"0.5"`, `"{}"`) — coerced to float/dict at the load boundary.
- **Two metric-basis bugs caught in review.** `recovery_factor` was fed the sum of
  per-trade fractional returns (notional basis) against an equity-basis maxDD —
  fixed to use `total_return`. And `--dry-run` was defined `default=True` and never
  read, so it implied a protection that only `--persist`'s absence actually gave;
  it now genuinely overrides `--persist`.

## Deliberate non-fixes

- **PSR basis** mixes the stored annualized per-bar Sharpe with per-trade
  skew/kurtosis/n. The sign is reliable (negative Sharpe → PSR≈0); the magnitude
  is directional, not calibrated. Consistent with the plan decision and the
  crypto-1m caveat — documented in the docstring, not "corrected".
- **SQN** uses R-multiples (van Tharp textbook), not net returns — the code was
  right and the methodology doc contradicted itself; the doc was reconciled to the
  code.

71 pure-math unit tests, ruff + pyright clean, zero reverse imports from `src/`.
