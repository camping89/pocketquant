---
phase: 5
title: "Verify"
status: completed
priority: P1
effort: "2h"
dependencies: [1, 2, 3, 4]
---

# Phase 5: Verify

## Overview

End-to-end verification of the declarative control plane: full test suite, import-linter, lint+types, and a restart-resume integration test proving the success metric. Plus a pre-prod migration dry-run gate for the mass-auto-start risk.

## Requirements

- Functional:
  - Restart-resume proven by test: sub with `desired_state="running"`, actual=stopped → reconcile starts it; restart (new engine, rehydrate + reconcile) → strategy running again with zero manual calls.
  - Stop convergence: `desired="stopped"` + actual=running → reconcile stops.
  - `import-linter` passes (reconcile service in correct layer).
  - Full `just test`, `just lint`, `just types` green.
- Non-functional:
  - Pre-prod: dry-run count of subs that migration would flip to `running`.

## Architecture

- Integration test composes the real pieces with container fixtures: `SubscriptionRepository`, `StrategyAppService` (real, paper broker), `StrategyReconcileService`. Drive `_reconcile()` directly (no live loop/sleep) for determinism — call it, assert state, simulate restart by building a fresh `StrategyAppService` + rehydrate path, call `_reconcile()` again.
- Restart simulation: don't actually restart the process; reconstruct the engine + re-run the rehydrate logic (load_strategy per sub) then reconcile, asserting `actual_state` returns to running.

## Related Code Files

- Create: `tests/api_test/test_reconcile_restart_resume_integration.py` (or `execution_test/` if no api deps needed — prefer execution_test with real PaperBroker + real repo via container)
- Verify only: all Phase 1–4 files.

## Implementation Steps

1. **Integration test** `test_reconcile_restart_resume_integration.py`:
   - Setup: persist a sub `desired_state="running"`, load its strategy instance into engine A (stopped).
   - `await reconcile_A._reconcile()` → strategy running; DB `actual_state="running"`.
   - Simulate restart: build engine B (fresh), run rehydrate (load_strategy per sub — instances stopped), build reconcile_B.
   - `await reconcile_B._reconcile()` → strategy running again; DB `actual_state="running"`. Zero manual `start_strategy` calls in test body.
   - Stop path: `update_desired_state(sub, "stopped")`; `_reconcile()` → strategy stopped; `actual_state="stopped"`.
2. Run full suite: `just test`. Fix any regressions (esp. existing strategy/subscription tests touching the changed handlers/entity).
3. `just lint` — ruff clean.
4. `just types` — pyright clean.
5. **import-linter**: run `.venv/bin/lint-imports` (binary present; no `just` recipe — invoke directly from workspace root). Confirm `StrategyReconcileService` in execution does not import api/trading/backtest; the 6 contracts still pass.
6. **Migration dry-run gate** (pre-prod, documented, not automated in CI): on a copy of the production DB, run `db.subscriptions.countDocuments({desired_state: {$exists: false}})` to see how many subs will flip to `running`. Operator confirms the number is expected before deploy. Document the command + the rollback (`updateMany({}, {$set:{desired_state:"stopped"}})`).
7. Update `docs/system-architecture.md` if it describes strategy lifecycle/rehydrate (delegate to docs-manager or note as follow-up) — add reconcile loop + desired/actual state to the AS-IS description. Keep AS-IS only (no changelog).

## Success Criteria

- [ ] Restart-resume integration test green: running sub auto-resumes across simulated restart, 0 manual starts.
- [ ] Stop convergence test green.
- [ ] `just test` full suite green (no regressions).
- [ ] `just lint` + `just types` clean.
- [ ] import-linter: all 6 contracts pass.
- [ ] Migration dry-run command + rollback documented; operator gate noted.
- [ ] docs/system-architecture.md reflects reconcile + desired/actual state (or follow-up task filed).

## Risk Assessment

- **Existing tests touching changed surfaces**: entity field add, handler dep swap, list_symbols shape change may break existing assertions (`test_subscription_repository.py`, `test_add_symbol_handler_autoload.py`, `test_strategy_position_and_trade_handlers.py`). Mitigation: run full suite; fix assertions to match new (intended) behavior — do not weaken tests to pass.
- **Flaky live-loop test**: never assert on the live `run()` loop with sleeps — drive `_reconcile()` directly. Locked by test design (step 1).
- **import-linter false pass**: if reconcile accidentally imports something upward, contract catches it. If linter not in CI, add to verify checklist (manual run step 5).

## Unresolved questions

1. **add_symbol auto-run**: plan sets new adds `desired_state="stopped"` (two-step UX preserved). User confirmed migration default running, but did NOT explicitly confirm new-add default. If they want add = auto-run, change Phase 3 step 5 to `"running"`.
2. **`list_symbols` `is_running` semantics for FE**: plan keeps `is_running` key = `actual_state=="running"`. If FE distinguishes desired vs actual (transitional UI), FE work is a separate (out-of-scope) task.
3. ~~import-linter invocation~~ — RESOLVED: `.venv/bin/lint-imports` from workspace root (no `just` recipe).
