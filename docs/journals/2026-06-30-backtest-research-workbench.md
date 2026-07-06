# Backtest Research Workbench

Reframe `/backtest` from single-run ephemeral (reload loses it) into a deep-link-able statistical workbench: 4-tab stat dashboard, scoped history rail, cross-scope compare, orders drill-down, verdict edit. 4 linear phases (1 BE/TDD → 3 FE), executed seamlessly.

## Memorable Decisions

- **Extend the endpoint instead of spawning a new one.** Red-team caught `GET /runs` duplicating the existing `GET /backtest/strategy/{id}` → added optional `?symbol=&interval=` to the old route. Baseline diff becomes purely additive (1 new orders route + 2 params), removing no route.
- **The `symbol` composite `CODE:EXCHANGE` is a one-way invariant.** Denormalize top-level from `config_snapshot`, **uppercase at every write-site** (`started`/`finalize`/`from_mongo` fallback) to match the `.upper()` filter. Lesson from review M1: if you only normalize query-side, a future writer storing lowercase → silently empty history. One source of truth; the two sides must not assume different things.
- **Route names follow repo convention, not the plan.** The plan wrote `backtest.$runId.tsx`, but that TanStack file-route would nest under the parent layout (currently the form). Use trailing-underscore (`backtest_.$runId.tsx`, `backtest_.compare.tsx`) like the existing `monitor_.jobs.$jobId` → standalone detail, URL contract still correct at `/backtest/$runId`.
- **Do not recompute the aggregate on the FE.** `profitFactorByDirection` only computes the LONG/SHORT split; the aggregate reads BE's `metrics.profit_factor` directly — avoiding two divergent definitions (red-team M7).
- **Defer the monthly heatmap.** Persisted equity curve downsamples to ≤5000 (strided) → financial numbers are approximate for sparse-trade strategies. Risk&Time MVP = equity+underwater (drawdown exact at each point) + top-5 drawdown table.

## Stumbles

- **Wrong build commands in the plan.** The plan assumed `just lint && just types && just baseline`; the `justfile` only has `just test`. Real commands per CI: `uv run ruff check` / `pyright` / `lint-imports` / `pytest`; baseline regen = `BASELINE_UPDATE=1 uv run pytest tests/baseline`.
- **Prod-DB guard blocks pytest.** Shell env `MONGODB_URL` points to the prod VPS → conftest refuses to run. Testcontainers spins up ephemeral Mongo/Redis on its own, so just `env -u MONGODB_URL -u REDIS_URL uv run pytest`.
- **routeTree.gen.ts does not regen when `tsc -b` runs before `vite build`.** Had to run `npx vite build` once (the plugin writes the tree) before the full `npm run build` typecheck. `npx tsr generate` doesn't read the entrypoints config correctly.
- **"adjust state during render" + optimistic update clash (review H1).** VerdictPanel resets the textarea when the `verdict` prop changes — but both optimistic-write AND revert-on-fail flow through that prop, so the save-fail branch wipes the text the user just typed (violating Q6 "KEEP text"). Fix: track `runId` instead of `verdict` — reset only when switching to a DIFFERENT run, not when the verdict of the same run fluctuates.

## Results

BE 608 passed / 1 skipped · ruff + pyright + import-linter 7/7 ✓. FE lint 0 errors · build ✓ · vitest 8/8 (`stats-utils`). Code review DONE_WITH_CONCERNS → H1 + M1 + M2 closed; L1/L2/L3 noted (dedupe timestamp, normalize off `initial_capital` literal, sampling caveat) — tradeoff accepted.

Next plan `260630-0031-backtest-mae-mfe-excursion` (blockedBy this plan) is now unblocked: FE scatter needs the Trades tab + chart wrapper from phase 3.
