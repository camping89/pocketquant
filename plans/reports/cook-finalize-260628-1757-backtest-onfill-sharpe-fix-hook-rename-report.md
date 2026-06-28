# Cook finalize report — backtest fill/Sharpe/rename/grid-opt

Plan: `plans/260628-1514-backtest-onfill-sharpe-fix-hook-rename/plan.md` (status → **done**)
Mode: `/cook` plan-execution. Branch `develop`. Date 2026-06-28.

## Scope reality

Working tree = 153 modified files, but only **~22 are this plan** (fill-routing, Sharpe, hook rename, grid-opt sandbox + tests + regenerated OpenAPI baseline). The other **~123 are an unrelated codebase-wide comment/docstring-stripping pass** (pure deletions) — NOT this plan. Commit scoping left to user (chose "tell me open items" first; commit deferred — user said "no need commit").

## Verification gates

| Gate | Result |
|---|---|
| pytest (`just test`) | **592 passed, 1 skipped, 0 failed** — stable across 5 consecutive runs |
| ruff | clean |
| pyright | clean (fixed 2 errs in `test_hitnrun2_backtest.py:267`: `**dict` spread → `risk=risk or RiskConfig()`) |
| import-linter | 7/7 contracts KEPT |
| code-reviewer subagent | **DONE** — all 10 acceptance criteria verified met; no regressions; no breaking contracts |

Repo has no `just lint`/`just types`/`just test-pkg` recipes (plan assumed them) — ran `ruff`/`pyright`/`lint-imports` directly.

### Code-reviewer Low findings — both fixed
1. `result_collector.py` downsample could yield 5001 points (comment claimed strict ≤5000). Fixed: final stride `kept[::stride]` then swap last element in-place (no append) → hard ≤5000.
2. `performance_calculator.py` numpy DoF RuntimeWarning on 2-point curves. Fixed: `sharpe_ratio`/`sortino_ratio` early-return on `len(returns) < 2` (and `< 2` downside for sortino). Behavior-identical (was nan→guarded 0.0).

## OpenAPI "drift" — resolved (was flagged for user)

Baseline `tests/baseline/openapi_app_snapshot.json` was **already regenerated** in working tree (21 `description` lines removed to match comment-stripped schema). Snapshot test PASSES consistently. The two single-test failures seen early (`test_openapi_snapshot`, then `test_job_history_repository`) were **flaky/order-dependent pre-existing infra tests** — both pass in isolation; full suite green 5×. No user decision needed.

## Prod re-smoke — DONE (user: "fix .env and resmoke prod")

Prod DBs reachable via app driver (the `/dev/tcp` reachability test was a false negative under zsh; pymongo + redis async clients both pinged OK). Ran **synchronous `POST /backtest/optimize`** (not async `/backtest/run` — local worker off with `ENABLE_JOBS=false`, so async would be drained by VPS old-code worker; optimize runs inline in local fixed code).

Grid: `hitnrun2 / BTCUSDT:BINANCE / 1h`, `entry_lookback_bars=[20,40]`, window 2026-01-01→2026-06-25.

| combo | entry | total_trades | win_rate | total_return | sharpe | sortino | maxDD |
|---|---|---|---|---|---|---|---|
| 0 | 40 | 262 | 67.2% | +2.19% | 11.25 | 26.56 | -1.06% |
| 1 | 20 | 296 | 56.1% | -0.94% | 0.83 | 0.27 | -3.01% |

- **Bug #1 fixed:** hundreds of trades/combo (was capped at 1). Strategy injection + fill routing live per-run.
- **Bug #2 fixed:** Sharpe sane + responsive (was -227/-30). Profitable combo → high Sharpe, losing combo → low.
- **Isolation (Phase 2+5):** distinct trade counts (262≠296) → no cross-talk; live `positions: 0` → sandbox doesn't leak phantoms into live engine.

Combo-0 Sharpe 11.25 slightly > ~10 guideline: explained by very-low-vol equity (maxDD -1.06%, 67% win) over a calm window, not a bug — contrast with combo-1's 0.83 confirms responsiveness.

## .env safety

Earlier session left `.env` = prod (`remote-db.env`) with NO backup. After re-smoke:
- Backed up prod config → `.env.remote-db.bak`
- Restored `.env` ← `all-local.env` (localhost Mongo/Redis, `ENABLE_JOBS=false`, 0 prod-host refs)
- Hardened `.gitignore`: `.env` → added `.env.*` so the prod-cred backup (and any future env variants) never get committed.

## Docs

No docs-manager run needed — `docs/system-architecture.md` already accurately documents `BacktestSandbox` per-run isolation (L500), renamed handlers (L518), fill routing by `subscription_id` (L522); `docs/code-standards.md` has event naming. These were updated as part of plan work; no stale hook names remain in src or docs.

## Known edges (documented, NOT fixed — pre-existing, out of scope)

- **M-1:** `HitNRun2._open_direction` set optimistically before submit → can stick if entry order risk/size-rejected (rare post state-machine fix).
- **L-1:** cumulative `realized_pnl` double-count on repeated partial-reduce — doesn't trigger (strategy full-closes via SL/TP).
- **Live OKX `on_order_update` unwired** (0 call-sites) → live fills won't publish `OrderFilledEvent`. Live OFF; follow-up plan when enabling live.

## Unresolved / awaiting user

1. **Commit** — deferred per user ("no need commit"). When ready: recommend committing ONLY the ~22 plan files + regenerated baseline + `.gitignore` hardening, separate from the 123-file comment-stripping pass.
2. Prod `backtest_optimization_runs` gained 1 doc from re-smoke (id `019f0dff-b3d3-776b-bc68-7f5f007c378c`) — harmless, deletable if you want it cleaned.
