# SP1 Shipped — Declarative Control Plane

**Date**: 2026-06-09 14:46  
**Severity**: Feature  
**Component**: Strategy lifecycle, reconcile loop, boot migration  
**Status**: Completed  

## What Shipped

Strategy run-state moved from RAM (`StrategyAppService` memory) into MongoDB (`Subscription.desired_state` + `actual_state`). New reconcile poll loop (5s) diffs desired (DB) vs actual (engine), calls start/stop to converge, writes actual back only on drift. Boot migration idempotently backfills legacy docs: `desired_state` default `running` (auto-resume all pre-existing), `actual_state` default `stopped`. Handlers rewritten declarative: start/stop/list_symbols write or read from DB only, zero RAM coupling. add_symbol pins new adds to `desired_state="stopped"` (user-confirmed — new subscriptions don't auto-run). This gates SP3 (split app/bff) because the handler↔runtime boundary is now 100% Mongo.

Commit: 2b818ab (38 files, 2379 +/-).

## Key Decisions Locked

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Reconcile mech | Poll every N sec | Mirrors existing WsSubscriptionManager pattern |
| State enum | 2 states (`running`/`stopped`) | YAGNI; extensible later |
| Persist actual? | Yes | List reads DB; reconcile writes idempotently; SP3-ready |
| Migration default | `desired_state=running` | Auto-resume all pre-existing (mass-start risk accepted + documented) |
| add_symbol default | `desired_state=stopped` | New adds don't auto-run (intentional asymmetry with migration) |

## TDD Note

Each phase had characterization test before code — froze behavior of frozen dataclass + lifecycle (rehydrate, reconcile) before refactoring. Pattern: `tests/execution_test/strategy_injection_roundtrip_characterization_test.py`.

## Verification

- Suite: **444 passed / 12 skipped / 0 failed**
- import-linter: 7/7 contracts held
- pyright: 0 errors on changed files
- ruff: changed files clean (141 pre-existing repo errors not from this)
- Code review: PASS-WITH-CONCERNS (no Critical/High, one Low: per-tick log-spam on missing instances — **fixed**: warn now fires once on drift, not every tick)
- Integration test: `test_reconcile_restart_resume_integration.py` — running sub auto-resumes across simulated restart, zero manual starts

## The Hard Part — Race Safety

Looked scary on paper: remove_symbol can delete a strategy instance between reconcile's snapshot of `get_strategy()` (line 100, no lock) and the `start_strategy()` call (line 112). If strategy vanishes mid-window, `start_strategy()` re-checks under its own `_lock` (strategy_app_service.py:120-121) and bails with ValueError. Per-sub error isolation catches it, sub row deletes next tick, loop continues. No crash, no orphan. **The lock-recheck in start_strategy is the guard.** Easy to miss because the snapshot looks like the guard — it's not. The lock is.

Lesson: when a snapshot looks like a race guard, trace what actually stops the bad outcome. Often the real guard sits one level deeper. Document the WHY if it's non-obvious (we did: strategy_app_service.py:168-170 + reconcile service comments on lock reliance).

## Actual Impact

Run-state persistence + reconcile loop unlocks:
- **Auto-resume on restart** (no manual FE clicks)
- **Observable desired vs actual** (Mongo source of truth, not RAM ephemeral)
- **SP3 prerequisite met** (no more command-channel-to-RAM)

Mass-start risk (migration default `running`) **user-accepted**, documented in code with rollback one-liners (main_extensions.py:259-263) + pre-deploy count command. Observability + idempotency make it safe to run in prod — worst case, redeploy with `$exists:false` filter rolls back unseen.

## Why This Matters

Kubernetes-style declarative state is alien to a RAM app. The shift forces a boundary: handlers write intent (Mongo), engine reads intent + reports reality (actual_state). That boundary is what lets SP3 split the monolith — with this in place, the RPC boundary is pure data, no hidden channel coupling. Without it, every refactor of StrategyAppService or DI blows up the split. This ship unblocks the whole plan.

## Next

SP2 (rename the composition-root package to `pocketquant.app`) is mechanically independent — can run before or after, just path-swap in all plan files. SP3 (split app/bff) goes next: now that the boundary is Mongo, the split is a wiring problem, not an architecture problem.
