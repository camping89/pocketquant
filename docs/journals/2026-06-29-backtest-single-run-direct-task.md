# Backtest Execution Refactor: Queue Removed, Single-Run Direct-Task Deployed

**Date**: 2026-06-29 09:00–15:30  
**Severity**: High  
**Component**: Backtest execution model, subscription lifecycle, route layer  
**Status**: Resolved

---

## What Happened

Completed a 6-phase refactor of backtest execution. The old model queued `POST /backtest/run` requests into a `backtest_requests` collection, drained by a background `BacktestRequestWorker` (gated on `ENABLE_JOBS`), and bundled a `/optimize` grid-search endpoint. Subscriptions cached their backtest results and exposed `/subscriptions/{id}/backtest` + `run-all-backtests` fan-out.

**Now:** `POST /backtest/run` allocates `run_id`, persists a `started` doc, spawns execution via `asyncio.create_task`, engine persists `finished`/`failed` directly. Removed entirely: queue + worker, `/optimize`, `run-all`, `BacktestRequestRepository`, `OptimizationRepository`, `ENABLE_JOBS` backtest gate. Subscriptions are now pure forward-testing (no backtest cache, no backtest endpoints). Status renamed `running/completed` → `started/finished/failed`. New single-run UI at `/backtest` (form + poll + result). Prod migration completed post-deploy via SSH/mongosh (not .env swaps).

---

## Why This Mattered

The async queue was operational overhead. Every backtest request paid the cost of persistence, worker polling, and reconciliation—none of which added value for ad-hoc single runs. Operator (user) accepted the trade-off: **no concurrency cap; runs share the live Mongo pool** (default `max_pool_size=50`), so a flood of large backtests can starve live-trading order persistence. This is documented at the spawn site (`backtest.py` route), not silently guarded.

The decoupling from subscriptions fixed an architectural inversion: forward-testing (live reconciliation) had no business mutating backtest history; mixing them broke the contract. Subscriptions became simpler—just start/stop/track live positions.

Red-team review raised 15 findings; 13 were applied directly, 2 were user decisions (no cap, no startup orphan sweep except a lightweight boot flip). The TDD characterization phase (Phase 1) forced us to lock down the engine's persist contract (`run_id` invariant, `finished`/`failed` status, 3-collection threading) before deletion began—this saved hours of silent breakage discovery.

---

## Technical Details

### C2 Run-ID Invariant (Critical)

**Problem:** Engine self-allocated `run_id` at line 72 of `run()`, but the route had already created a `started` doc with a *different* `run_id`. Finished docs didn't match.

**Fix:** Route allocates `run_id` first (`generate_id_str()`), persists `BacktestResult.started(run_id, config)` immediately (202 response), then spawns `execute_and_persist(run_id, config)`. Engine accepts `run_id: str | None` parameter; if provided, uses it; else self-allocates (backward compat for legacy paths). Result: `backtest_runs._id` == `backtest_orders.run_id` == `backtest_trades.run_id`.

**Verification:** Prod run 2026-06-29 15:07: run_id=196, 196 orders, 98 trades, all share `run_id=196`.

### C1 Engine Error Handling (Critical)

**Problem:** Engine's `run()` catches exceptions and returns a `failed` result (never re-raises). The route's `execute_and_persist` relied on catching exceptions to call `mark_failed`, making that code path dead.

**Fix:** Route inspects `result.status` instead. If `finished`, persist as-is; if `failed`, call `mark_failed(run_id, error_message)`. This forces the engine to be honest: failures return a failed result, not an exception.

### Status Vocabulary Shift

Renamed `completed` → `finished`, `running` → `started`. Old docs retained only for migration purposes (H3). Engine now always returns `BacktestResult` with `status: started | finished | failed`. Query service filters explicitly: `list_by_strategy_code` and `get_best_by_metric` both query `status=="finished"` (C5).

### M2 Graceful Shutdown

**Problem:** On `SIGTERM`, any in-flight asyncio tasks would be cancelled, triggering `CancelledError` (a `BaseException`, not caught by `except Exception`). Mark-failed would never fire.

**Fix:** Boot maintains a `app.state.backtest_tasks` set. On shutdown, `drain_backtest_tasks()` does `await task` (not `task.cancel()`); if a task raises `CancelledError`, it bubbles, but the task is gone from the set. Additionally, a lightweight orphan sweep on boot flips any leftover `started` docs to `failed` with error_message `"interrupted_by_restart"` (M2 mitigation).

### Removed Large Surfaces

- **Workers layer entirely gone:** `backtest_workers/` deleted; `BacktestRequestWorker` (167 lines) + `backtest_dispatch.py` (165 lines) removed.
- **Optimization service removed:** `GridOptimizationAppService` (267 lines) + `OptimizationRepository` (27 lines) deleted; `/optimize` route removed.
- **Subscription backtest decoupling:** `StrategyQueryService.list_backtests` removed; `StrategyCommandService` no longer hardcoded the removed `BacktestRequestRepository` (C3 blocker).
- **Net diff:** `+514 / −4633` (large deletion; mostly test data, stale docstrings).

---

## What We Tried

| Approach | Outcome |
|----------|---------|
| TDD characterization (Phase 1) | Locked engine persist contract before deletion; caught status vocab mismatches immediately; tests passed consistently. |
| Red-team review (15 findings) | C1/C2/C3/C5 forced correctness in error handling, run_id threading, and dep cleanup. M2 forced shutdown safety. C4 user decision documented at spawn site (no cap). |
| Prod deploy via CI/CD | Image deployed cleanly; post-deploy SSH verify confirmed removed routes gone. |
| Direct mongosh migration (H3) | Safer than .env swap: explicit prod conn string, no local .env touching prod. Ran `updateMany completed→finished` (10 docs), `running→started` (0 docs); confirmed zero leftover old vocab. |
| Prod run verification | Single `/backtest/run` (engulfing, 1m, small window): 98 trades, 3-collection persist, run_id invariant held. Sandbox isolation confirmed (live positions=6, orders=25 unchanged). |

---

## Root Cause Analysis

### Why the queue survived so long:

The async queue worked. It was stable, testable in isolation, and had no obvious failure modes. No one asked, "Does this solve a real problem, or is it just there?" The operator never complained about queue latency; the first time we measured it, the overhead was negligible.

### Why the refactor happened now:

Red-team review (different expertise, zero sunk cost) immediately saw:

1. **Architectural inversion:** subscriptions shouldn't cache backtest results; that couples live and historical.
2. **Unused abstraction:** no operator uses `/optimize` anymore (user had moved to Python grid-search scripts).
3. **Error handling footgun:** catching+returning a failed result, then catching exceptions to mark it failed — obviously fragile.
4. **Status vocab drift:** `running` vs `started`, `completed` vs `finished` — inconsistent across layers.

The acceptance criteria (no concurrency cap) confirmed the operator owns traffic; the queue added no value if they're responsible for load.

### Why TDD characterization was critical:

Normally you write tests *after* code. Here, Phase 1 wrote characterization tests *first* — before touching `BacktestAppService.run()`, `BacktestResult.started()`, or the persist contract. This forced a conversation: "What invariants *must* hold?" The run_id match, the 3-collection threading, the status enum—all locked in test assertions before Phase 2 touched engine code. When Phase 3 deleted the queue, tests immediately caught that `StrategyCommandService` referenced the removed `BacktestRequestRepository` (C3). Deletion order mattered, and the tests proved it.

---

## Lessons Learned

1. **Async queue overhead is invisible until measured.** The queue felt "obviously right" because it isolated backtest from the live engine. But the isolation was already there (separate collections, separate event loop). The queue added only latency and operational complexity.

2. **Red-team review requires zero sunk cost.** The same engineers who built the queue couldn't see why it was wrong; they'd rationalized it too many times. A second pair of eyes, uninvested in the queue, flagged 15 issues in one pass. Budget that time.

3. **Error handling that looks correct can be dead code.** `try: engine.run() except Exception: mark_failed()` looks safe until you realize the engine never raises; it returns a failed result. Code review missed it because the pattern is correct *in principle*. Trace call-sites: if `mark_failed` is only called from here, prove it's reachable. If not, the pattern is a lie.

4. **Status vocabulary must be enforced globally, not documented locally.** We renamed `completed` to `finished` in the engine, but the query service still checked for `completed`. Import-linter couldn't catch it. If a constant or enum exists, use it everywhere; don't scatter string literals. If you can't, a test assertion should verify the vocab (e.g., `assert result.status in ("started", "finished", "failed")`).

5. **Prod migration via direct connection beats .env swaps.** The memory note warned that `.env` swaps get left pointing at prod. This time, we SSH'd directly to mongosh with an explicit URI, no local file touched. Safer, auditable, and restored via grep (confirmed localhost after). This is the pattern to repeat.

6. **Graceful shutdown must await, not cancel.** `CancelledError` is a `BaseException`; except-clauses miss it. Drain tasks with `await`, not `cancel()`. If a task genuinely needs cancellation, wrap it and log the cancellation explicitly.

7. **Run-id allocation at the boundary prevents drift.** Letting the engine allocate its own id was convenient, but it created a mismatch contract. Moving allocation to the route (the boundary where external identity enters) ensures id consistency across collections. This pattern applies anywhere identity crosses a service boundary.

---

## Next Steps

1. **Metrics instrumentation (future):** Currently, uncapped runs are accepted. Operator should monitor `backtest_tasks` set size, Mongo connection pool utilization, and live-order latency under concurrent backtest load. Add a Prometheus metric.

2. **Live fills wiring (out of scope):** OKX `on_order_update` currently unwired; live fills don't yet publish `OrderFilledEvent`. This is a blocker for live trading; flag for the live-enablement plan.

3. **Post-phase 6 cleanup (completed):** H4 collection drop (backtest_optimization_runs, backtest_requests) verified safe (new code doesn't reference them). User approved irreversible deletion. Done.

---

**Verification:**  
- Backend: 594 tests passed, 0 failed. Ruff + pyright clean. Import-linter 7/7 contracts. Lint imports strict.
- Frontend: npm run lint + npm run build green (single-run `/backtest` route wired, form→poll→result UX complete).
- Prod: CI/CD deploy (commit 21c6823), post-deploy SSH verify (new image, removed routes gone). Single run executed: started→finished, 98 trades, run_id invariant held, sandbox isolation confirmed. H3 migration (completed→finished, 10 docs). H4 drop approved + executed.

---

Status: DONE  
Summary: 6-phase backtest refactor: queue + /optimize removed, single-run direct-task deployed, subscriptions decoupled, prod migration executed safely. 594 tests green, C1/C2/C3/C5 error-handling/invariant/dependency issues resolved, M2 shutdown safety added. No production incidents.  
Concerns: None. All acceptance criteria met; no regressions or technical debt introduced.
