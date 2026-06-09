---
phase: 2
title: "Reconcile Service"
status: completed
priority: P1
effort: "4h"
dependencies: [1]
---

# Phase 2: Reconcile Service

## Overview

Add `StrategyReconcileService` in `execution`: a poll loop that diffs `desired_state` (Mongo) vs actual (RAM `StrategyAppService`), calls `start_strategy`/`stop_strategy` to converge, then writes `actual_state` back to Mongo. Idempotent, cancel-safe, never crashes the app. Mirrors the proven `WsSubscriptionManager` shape.

## Requirements

- Functional:
  - `run()` loop: every `interval_s`, call `_reconcile()`, sleep. Runs until cancelled.
  - `_reconcile()`:
    - Load all subs (`sub_repo.list_all()`).
    - For each sub: compute actual from RAM (`strategy_service.get_strategy(sub.id)` → `.is_running`).
    - `desired=running` & actual=stopped → `start_strategy(sub.id)`.
    - `desired=stopped` & actual=running → `stop_strategy(sub.id)`.
    - After convergence, if persisted `actual_state` != observed actual → `update_actual_state(sub.id, observed)`.
  - Missing RAM instance (`get_strategy` → None) while `desired=running`: log warning, treat actual=stopped, attempt no start (instance is loaded by rehydrate/add_symbol, not by reconcile). Reconcile only flips running, never loads.
- Non-functional:
  - `asyncio.CancelledError` propagates (lifespan teardown).
  - Any other exception → log + retry next tick, never crash.
  - Idempotent: stable desired+actual → zero writes, zero start/stop calls.
  - Shares `StrategyAppService._lock` implicitly via `start_strategy`/`stop_strategy` (both already lock) — no new lock, no lock-split.

## Architecture

- Location: `packages/pocketquant-execution/src/pocketquant/execution/app_services/strategy_reconcile_service.py`. Execution layer is shared engine, imported by trading/backtest/api; placing here keeps import-linter happy (no upward import).
- Deps injected: `SubscriptionRepository` (infra — execution already imports infra repos? VERIFY: execution imports order/position repos via constructor in DI, not direct module import — pass repo instance, do not import api). Constructor takes `sub_repo`, `strategy_service`, `interval_s: float = 5.0`.
- Reconcile decision table:

  | desired | actual (RAM) | action | actual_state write |
  |---------|--------------|--------|--------------------|
  | running | stopped | `start_strategy` | → running (after start) |
  | running | running | none | none (if already running in DB) |
  | stopped | running | `stop_strategy` | → stopped (after stop) |
  | stopped | stopped | none | none |
  | running | (no instance) | warn, no-op | → stopped |

- `actual_state` write: only when DB value drifts from observed, to keep idempotent (no churn writes every tick).

## Related Code Files

- Create: `packages/pocketquant-execution/src/pocketquant/execution/app_services/strategy_reconcile_service.py`
- Create: `tests/execution_test/test_strategy_reconcile_service.py`

## Implementation Steps

1. **Verify import boundary**: confirm `execution` may reference `SubscriptionRepository` type. It lives in `infrastructure`; execution→infrastructure is allowed by layer contract. Constructor-inject the instance (DI wires it Phase 4). Import for type hint is fine (`from pocketquant.infrastructure...import SubscriptionRepository`).
2. **TEST FIRST** — `tests/execution_test/test_strategy_reconcile_service.py` (unit, fakes — no DB/containers, mirror char-test style with AsyncMock + a fake repo holding an in-memory dict):
   - desired=running, actual=stopped → `start_strategy(sub.id)` called once; `update_actual_state(sub.id,"running")` called.
   - desired=stopped, actual=running → `stop_strategy(sub.id)` called; `update_actual_state(...,"stopped")`.
   - desired=running, actual=running, db actual already running → no start, no actual write (idempotent).
   - desired=running, no RAM instance → warn path, no start, actual persisted stopped.
   - `_reconcile` raising inside one sub does not abort the whole tick (wrap per-sub or per-tick try/except — choose per-tick like WsSubscriptionManager; a single bad sub fails the tick, logged, retried — document this choice).
   - `run()` cancellation: schedule `_reconcile` to set an event, cancel task, assert CancelledError propagates (use `asyncio.wait_for`).
3. Write `StrategyReconcileService`:
   - `__init__(self, sub_repo, strategy_service, interval_s=5.0)`.
   - `async def run(self)`: `while True:` try `_reconcile()` except `CancelledError: raise` except `Exception: log`. `await asyncio.sleep(interval_s)`.
   - `async def _reconcile(self)`: list subs; per sub compute observed actual; converge; persist actual on drift.
   - Structured logs: `reconcile.started`, `reconcile.converged` (counts started/stopped), `reconcile.missing_instance`, `reconcile.failed`.
4. Run `just test-pkg execution` (targeted) → green.
5. `just lint` + `just types`.

## Success Criteria

- [ ] `_reconcile` converges all four state combos correctly (table above).
- [ ] Idempotent: stable state → 0 start/stop calls, 0 actual writes.
- [ ] `run()` cancel-safe (CancelledError propagates) and crash-proof (other exc logged, loop continues).
- [ ] No import-linter violation from execution layer.
- [ ] Unit tests green (pure fakes, no containers needed).

## Risk Assessment

- **Reconcile ↔ manual start race**: both go through `StrategyAppService.start_strategy` which is `_lock`-guarded and early-returns if `strategy.is_running`. Idempotent by construction. Locked by the "already running → no-op" test.
- **Per-tick vs per-sub error isolation**: per-tick (WsSubscriptionManager style) means one bad sub skips the rest until next tick. Acceptable for 5s cadence; document. If sub count grows large, revisit per-sub isolation (note, not now — YAGNI).
- **actual_state write churn**: writing every tick would hammer Mongo. Mitigation: write only on drift (DB actual != observed). Locked by idempotent test.
- **Reconcile loads strategies?**: NO. Loading (registry lookup + `load_strategy`) stays in rehydrate/add_symbol. Reconcile only start/stop existing instances. Keeps responsibility narrow; missing instance is a warn, not a load.
- **Backtest injected strategies must not be touched** (load-bearing): `StrategyAppService` is shared — backtest injects strategies under *synthetic ids* via `inject_prepared_strategy` (no subscription row). Reconcile is **subscription-driven**: it iterates `sub_repo.list_all()` and only ever calls `get_strategy(sub.id)` / `start_strategy(sub.id)` / `stop_strategy(sub.id)`. It NEVER enumerates RAM instances, so synthetic-id backtests are invisible to it. Lock this with a test: inject a synthetic-id strategy + a running backtest-style instance, run `_reconcile` over an empty/unrelated subscription set, assert the injected strategy is neither stopped nor written.
