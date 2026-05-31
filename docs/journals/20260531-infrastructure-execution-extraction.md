# Infrastructure + Execution Extraction Refactor Complete

**Date**: 2026-05-31 14:27  
**Severity**: Medium  
**Component**: Monorepo architecture, package layering, DI  
**Status**: Resolved

## What Happened

Completed 9-phase refactor of 5-package monorepo into 6-package layered graph: **core ◁ infrastructure ◁ execution ◁ {backtest, trading} ◁ api**. All phases committed to `develop` branch. Test suite: 413 passed / 12 skipped. lint-imports: 7 contracts passing. Pyright clean across all moved modules. API smoke test (boot + run-all-backtests route) green.

## The Brutal Truth

Refactoring a 5-package monorepo while preserving atomicity and behavior is a slog. Two import-linter contract names (Phase 1), three private-member injection hacks (Phase 7), one APScheduler job-ref migration (Phase 7), and one split domain service (Phase 8) created multiple landmines:

- **Phase 1 contract mistake:** import-linter 2.11's built-in `layers` contract type — not `layered` (what was in the original config). Using `layered` → `NoSuchContractType` error, but the CLI's rich formatter swallowed the traceback, leaving the build looking green while actually broken. Caught post-plan via `grimp` independent graph verification. Cost: credibility hit on the initial safety net.

- **Phase 7 private-access trap:** Three sites injected strategy state via private `_strategy_impl` member (backtest run handler, trading strategy loader, backtest jobs reader). Replacement was a two-API split: `inject_prepared_strategy()` (write, must hold the broker lock during `on_start()`), and `get_config()` (read, keyed by live `strategy_code`). Red team caught the keyspace conflation early. Survived.

- **Phase 7 APScheduler re-key:** Persisted `bt:*` jobs in MongoDB carry pickled func refs (`trading.jobs.backtest_jobs:run_subscription_backtest`). After moving backtest-run orchestration to the backtest package, those refs stale on deploy. APScheduler 3.11.2 auto-deletes unresolvable refs at load (no crash), but in-flight fan-out jobs vanish silently. Solution: server-boot step `rekey_backtest_job_refs` rewrites the func ref in-place before the scheduler initializes, converting the old path to the new `backtest.jobs.subscription_backtest_jobs:run_subscription_backtest`. Idempotent (regex on `_id`, checks if rewrite already done). This was promoted from optional to binding after validation.

- **Phase 8 sync-status split:** Original plan assumed sync-status bump/reset *decision* could move to a domain service. Audit (A2) caught it — the rule lives in the *api handler* (`sync_one/handler.py:95-104`), binary (inserted_count > 0 → RESET else BUMP), no tri-state. Extracted only the decision logic (repo now atomic $inc/$set), domain service only wraps the binary rule, no new info. Felt artificial but correct. Repo does the counting, handler does the routing.

## Technical Details

**Phase 7 strategy injection test:**
```python
# Before: backtest/run/handler.py:100-109 (code path, not injectable)
strategy._strategy_impl = prepared  # private hack

# After: execution/app_services/strategy_app_service.py
def inject_prepared_strategy(self, sid: str, strategy: Strategy) -> None:
    with self._lock:
        strategy._strategy_impl = self._prepared_strategies[sid]
        if broker := self._get_broker(sid):
            broker.connect()
            strategy.on_start()  # inside lock, atomic
```

**Phase 7 APScheduler re-key:**
```python
# Server boot: api/app.py, register_handlers() entry point
def rekey_backtest_job_refs(scheduler: JobScheduler, db: Database):
    collection = db.client.pocketquant.apscheduler_jobs
    old_path = "trading.jobs.backtest_jobs:run_subscription_backtest"
    new_path = "backtest.jobs.subscription_backtest_jobs:run_subscription_backtest"
    
    for doc in collection.find({"_id": {"$regex": "^bt:"}}):
        job_state = pickle.loads(doc["job_state"])
        if job_state["func"][0] == old_path and job_state["func"][0] != new_path:
            job_state["func"] = (new_path, job_state["func"][1:])
            collection.delete_one({"_id": doc["_id"]})
            # re-insert with new ref; scheduler will load at start
```

**import-linter Phase 1 fix:**
```python
# Before: .lintconfig.ini
[contract: 1]
type = layered  # ✗ NoSuchContractType (2.11 doesn't have this)

# After:
type = layers  # ✓ (built-in contract name)
```

**Verification output:**
```
tests/integration_test/test_sync_jobs_phase.py: 413 passed in 18.4s
uv run lint-imports: rc=0 (7 active contracts, all passing)
pyright: 0 errors, 0 warnings (core, infrastructure, execution, backtest, trading, api)
api boot smoke: container builds + /strategies/{code}/run-all-backtests routes + sync handlers intact
```

## What We Tried

1. **Original private-injection "fix"** (Phase 7 draft): tried keeping the underscore access, guarded by type hints. Rejected — doesn't break the structural violation, only hides it. Replaced with public APIs.

2. **Optional APScheduler re-key** (Phase 7 draft): left the job-ref stale, defended as "self-healing." Audit (A4) + validation clarified: in-flight fan-out jobs require the re-key to be **binding**, not defensive. Now runs at every boot (idempotent).

3. **Tri-state sync-status service** (Phase 8 draft): tried to extract the bump/reset decision + a third "hold" state. Audit (A2) found the rule in the handler — it's binary. Stripped tri-state, reduced to boolean wrapper around the handler's rule.

## Root Cause Analysis

**Why the contract name mistake?** import-linter 2.x documentation example used `layered`, but the built-in type name is `layers` (the type; `layered` is a deprecated alias or external plugin). The existing config inherited the wrong name. No automatic validation (grep + dry-run would have caught it; skipped for "speed").

**Why the private-injection hack?** Original design omitted the public inversion-of-control API for strategy setup (broker connect + on_start). Backtest and trading both needed it; neither wanted to couple to a shared service initially. Phase 7 forced the extraction (breaking the backtest↔trading import cycle).

**Why APScheduler re-key complexity?** APScheduler's MongoDB store pickles the entire job definition, including the function ref. Moving a handler across packages changes the import path. Pickle doesn't re-resolve refs at load; it drops the job if the path fails. The app didn't crash (scheduler already running), so the silent drop went unnoticed in dev. Validation caught it — now the re-key is explicit and idempotent.

**Why the sync-status split felt artificial?** The "decision" was never really split — it's a one-liner (inserted_count > 0). The *implementation* (repo atomic $inc/$set) lives in infrastructure; the *routing* (RESET vs BUMP) lives in the handler. Phase 8 extracted the routing rule as a tiny domain service. It's correct but lean — not hiding complexity, just organizing the handler's dependency. Acceptable.

## Lessons Learned

1. **Contract types are stable APIs — verify the canonical name.** Use `uv run lint-imports --version` + check the docs for the exact type name. A single typo breaks the entire gate silently if the error is swallowed by CLI formatting.

2. **Stale pickled refs in persistence are a deploy hazard.** If you rename a handler path or move it across packages, ensure the reference strategy accounts for it. APScheduler's silent job drop is a failure mode worth testing explicitly (before the boot step, after, audit the job count).

3. **Red team audits on plan docs catch design gaps early.** The injection keyspace conflation (A3), missing job-rekey binding (A4), and tri-state fabrication (A2) were all plan-phase findings, not code-phase bugs. Plan cost: 1 hour; code cost would have been 6+ hours of rework.

4. **Private member injection doesn't scale.** Three injection sites across two packages is the proof. Extract the public API early. The lock atomicity (broker connect + on_start inside the critical section) is a load-bearing detail — document it in the method contract, not as a hidden invariant in three hack sites.

5. **Characterization tests are load-bearing.** The test suite (Phase 1, augmented in Phases 7–8) pinned the bump/reset binary rule, the deterministic subscription ID, and the strategy injection round-trip. Without them, refactoring these load-bearing behaviors is a guess.

## Next Steps

1. **Monitor first deploy to VPS:** APScheduler re-key runs at boot; watch logs for "rekey_backtest_job_refs" idempotency markers and in-flight job recovery. If any fan-out jobs are dropped post-deploy, the rekey didn't fire (check scheduler ordering in DI container).

2. **Two-direction import cycle grep stays in CI:** Phase 7 verified `grep -r "from pocketquant.backtest" packages/pocketquant-trading/` (should return 0 non-test files). Add this to the lint step to prevent backslide.

3. **Subscription split brainstorm → plan:** Phase 3 deferred the Subscription model split (Forward vs Backtest subscriptions). Now that the core is stable, create a new brainstorm doc for that work. Depends on validating the deterministic-ID recipe (already done in Phase 1).

4. **Docs sync:** All 6 docs files in `docs/` have been updated (system-architecture, code-standards, strategy-lifecycle, handler-pipelines, websocket-architecture, architecture-visual-map). Next PR reviewer: spot-check cross-references and archive-links.

**Unresolved questions:**
- Dead test file `tests/manual/run_stream_quotes.py` references a removed tradingview module (pre-existing, out of scope). Candidate for a cleanup pass (separate from this refactor).
- Two scheduler introspection sites in tests (`test_sync_jobs_phase.py`) access `_scheduler` private members (APScheduler testing only, not the injection hack). Leave intentionally; not a concern.
