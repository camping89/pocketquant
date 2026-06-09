---
phase: 4
title: "Boot Wiring and Migration"
status: completed
priority: P1
effort: "4h"
dependencies: [2, 3]
---

# Phase 4: Boot Wiring and Migration

## Overview

Wire the reconcile loop into the app lifespan (DI provider + background task with cancel-safe teardown), and add an idempotent boot migration that backfills `desired_state`/`actual_state` on pre-existing subscription docs. Migration default for old docs = **`running`** (auto-resume), per user decision — with the mass-live-start risk mitigated below.

## Requirements

- Functional:
  - DI provider for `StrategyReconcileService` (APP scope), wired with `SubscriptionRepository` + `StrategyAppService` + `reconcile_interval_seconds` from Settings.
  - Lifespan starts reconcile as a background `asyncio.Task` AFTER `rehydrate_strategies_from_subscriptions` (instances must exist first) and AFTER `start_quote_feed` ordering is fine either way (reconcile only needs instances loaded). Store handle on `app.state.reconcile_task`.
  - Cancel-safe teardown mirroring `stop_quote_feed`: cancel task, `wait_for(shield, 5s)`, swallow Timeout/Cancelled.
  - `Settings.reconcile_interval_seconds: float = 5.0`.
  - Boot migration `migrate_subscription_desired_state(container)`: for docs missing `desired_state`, `$set desired_state="running"` (auto-resume) and `actual_state="stopped"` (reconcile will converge to running on first tick). Idempotent (only touches docs where `desired_state` absent).
- Non-functional:
  - Migration runs once at boot, before `rehydrate` (so rehydrate/reconcile read final field shape), after `migrate_strategy_id_fields` (field-rename must precede).
  - `enable_jobs=False` (test mode) must NOT start reconcile task (gate like background jobs) — OR keep reconcile independent of jobs flag? **Decision below.**

## Architecture

### Lifespan ordering (insert points)

Current order (`api/main.py` lifespan):
```
migrate_strategy_id_fields
rekey_backtest_job_refs
register_handlers
ensure_all_indexes
recover_stale_backtests
recover_orphan_jobs
seed_tracked_symbols
rehydrate_strategies_from_subscriptions   ← instances loaded here
register_health_checks
start_background_jobs
start_quote_feed
```
New steps:
- Insert `migrate_subscription_desired_state(container)` immediately AFTER `migrate_strategy_id_fields` (both are subscription-collection migrations; field-rename first, then state backfill).
- Insert `start_reconcile_loop(container, app)` AFTER `start_quote_feed` (last; instances already rehydrated). Add `stop_reconcile_loop` in the `finally` block BEFORE `stop_quote_feed` (reverse order: stop reconcile first so it doesn't issue start/stop during teardown).

### enable_jobs gate decision

Reconcile is core runtime control-plane, not a "background sync job". But in tests (`enable_jobs=False`) we don't want a live loop. **Plan: gate reconcile start on `enable_jobs`** (same flag), since both represent "is this a real running app vs a test/CLI". Document: if SP3 later runs `app` always-on, `enable_jobs` stays True there; `bff` never starts reconcile. Reconcile lives only in `app` process.

### DI provider placement

Add to `ExecutionProvider` (execution-layer service, like StrategyAppService): a plain `@provide(scope=Scope.APP)` returning `StrategyReconcileService(sub_repo, strategy_service, interval_s=settings.reconcile_interval_seconds)`. `SubscriptionRepository` comes from PersistenceProvider; resolves across providers automatically.

### Migration default = running (user-confirmed) — risk + mitigation

Old subs lost RAM state; setting `desired_state="running"` means reconcile auto-starts EVERY pre-existing sub on first deploy. This is what the user wants (auto-resume). Mitigations baked into the plan:
- `actual_state` seeded `stopped` so the transition is observable in logs/FE (`converging`).
- Migration is idempotent and only touches docs lacking `desired_state` → re-deploys never re-flip a human's later `stop`.
- **Pre-deploy verification gate** (Phase 5): dry-run count of how many subs would flip to running on a DB copy before prod deploy. Operator eyeballs the number.
- Rollback note documented (set all `desired_state` back to `stopped` via one `updateMany`).

## Related Code Files

- Modify: `packages/pocketquant-core/src/pocketquant/core/config.py` (add `reconcile_interval_seconds`)
- Modify: `packages/pocketquant-api/src/pocketquant/api/di/execution.py` (provider) — file is 68 LOC, adding one provider keeps it well under 200; no split needed.
- Modify: `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` (add `migrate_subscription_desired_state`, `start_reconcile_loop`, `stop_reconcile_loop`)
- Modify: `packages/pocketquant-api/src/pocketquant/api/main.py` (lifespan: import + call new steps in order)
- Create: `tests/api_test/test_subscription_desired_state_migration.py`
- Create/extend: `tests/api_test/` reconcile-task lifespan test (optional integration)

## Implementation Steps

1. **TEST FIRST** — `tests/api_test/test_subscription_desired_state_migration.py` (container `settings` + real Database):
   - Seed 2 legacy docs (no `desired_state`) + 1 modern doc (`desired_state="stopped"`). Run migration.
   - Legacy docs → `desired_state="running"`, `actual_state="stopped"`.
   - Modern doc untouched (`desired_state` stays `"stopped"`).
   - Idempotent: second run → 0 modified.
2. Add `reconcile_interval_seconds: float = 5.0` to `Settings` (under "Strategy Engine").
3. Write `migrate_subscription_desired_state(container)` in `main_extensions.py`:
   - Get `Database`; `coll = db.database["subscriptions"]`.
   - `update_many({"desired_state": {"$exists": False}}, {"$set": {"desired_state": "running", "actual_state": "stopped"}})`.
   - Log `subscription_state_migration.completed` with modified_count. Idempotent by the `$exists:false` filter.
4. Write `start_reconcile_loop(container, app)` + `stop_reconcile_loop(container, app)` in `main_extensions.py`, mirroring `start_quote_feed`/`stop_quote_feed`:
   - `start`: gate on `settings.enable_jobs`; get `StrategyReconcileService`; `app.state.reconcile_task = asyncio.create_task(svc.run())`.
   - `stop`: cancel `app.state.reconcile_task`, `wait_for(shield, 5s)`, swallow Timeout/Cancelled.
5. Add DI provider in `ExecutionProvider` (execution.py is 68 LOC; stays well under 200). Inject `Settings` for interval.
6. Edit `main.py` lifespan:
   - Import new funcs.
   - Call `await migrate_subscription_desired_state(container)` right after `migrate_strategy_id_fields`.
   - Call `await start_reconcile_loop(container, app)` after `start_quote_feed`.
   - In `finally`, call `await stop_reconcile_loop(container, app)` BEFORE `stop_quote_feed`.
7. **TEST** — lifespan/DI resolution: a test that builds the container and resolves `StrategyReconcileService` + `StartStrategyHandler` (proves Phase 3 dep swap resolves). Reuse api_test container patterns.
8. Run `just test-pkg api` → green. `just lint` + `just types`.

## Success Criteria

- [ ] `reconcile_interval_seconds` in Settings, default 5.0.
- [ ] DI resolves `StrategyReconcileService` and the rewired start/stop/list handlers.
- [ ] Migration backfills legacy docs → `desired_state="running"`, `actual_state="stopped"`; modern docs untouched; idempotent.
- [ ] Lifespan starts reconcile task after rehydrate; teardown cancels it before quote-feed stop; cancel-safe.
- [ ] Reconcile task gated on `enable_jobs` (off in tests).
- [ ] api suite green; lint + types clean.

## Risk Assessment

- **Mass live-start on deploy** (HIGH, user-accepted): migration flips all legacy subs to `running` → reconcile starts them all within one tick. Mitigations: `actual_state` observability, idempotent filter, Phase-5 dry-run count on DB copy, documented one-line rollback. **Surface the flip count to the operator before prod deploy.**
- **Task start ordering**: reconcile must start AFTER rehydrate (instances exist) else first tick logs N "missing_instance" warnings then catches up next tick. Harmless (reconcile retries) but noisy. Mitigation: order per insert-point spec.
- **Teardown ordering**: stop reconcile BEFORE quote feed + before `container.close()` (which stops StrategyAppService). If reconcile ran during `container.close`, it could call `start_strategy` on a stopping engine. Mitigation: `stop_reconcile_loop` first in `finally`.
- **DI cross-provider resolution**: `StrategyReconcileService` needs `SubscriptionRepository` (PersistenceProvider) + `StrategyAppService` (ExecutionProvider) + `Settings` (CoreProvider). Dishka resolves across providers; verified pattern (StrategyAppService already pulls from multiple). Phase 4 step 7 test proves resolution.
- **Settings test construction**: `tests/trading_test/conftest.py` builds `Settings(...)` with explicit kwargs — adding a defaulted field is back-compat (no kwarg needed). Verify no `Settings(...)` call in tests sets `extra="forbid"` paths. Default makes it safe.
