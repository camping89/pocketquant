---
phase: 2
title: "Orphan-running reconcile lifespan integration"
status: completed
priority: P2
effort: "30min"
dependencies: [1]
---

# Phase 2: Orphan-running reconcile lifespan integration

## Overview

Wire the new `reconcile_orphan_running` repo method into FastAPI lifespan so every boot clears stale `status="running"` docs left by deploy-cancelled jobs.

## Requirements

- Functional: On every startup, after MongoDB indexes ensured and BEFORE scheduler starts, mark any `job_history` doc with `status="running"` AND `started_at < now - 10min` as `failed` with `error="orphan_running_recovered"`.
- Non-functional: Log the count when > 0 (mirror `recover_stale_backtests` pattern). Silent when 0.

## Architecture

```
main.py lifespan order (current → new):
  ensure_all_indexes
  recover_stale_backtests
  recover_orphan_jobs       ← NEW (between stale_backtests and seed_tracked_symbols)
  seed_tracked_symbols
  register_health_checks
  start_background_jobs     ← scheduler.start() inside; orphan reconcile MUST be done before this
  start_quote_feed
```

## Related Code Files

- Modify: `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` (add helper + export)
- Modify: `packages/pocketquant-api/src/pocketquant/api/main.py` (call helper in lifespan)

## Implementation Steps

1. **`main_extensions.py` — add `recover_orphan_jobs`** (place near `recover_stale_backtests`):
   ```python
   async def recover_orphan_jobs(container: AsyncContainer) -> None:
       """Mark any job_history docs stuck at status='running' as 'failed' on startup.

       Orphan rows arise when a job's wrapper writes record_start() but the
       process is killed before record_finish() runs (e.g. mid-deploy
       CancelledError). Without this sweep, dashboards show forever-running jobs.
       Safe to call repeatedly — idempotent. Logs once if any docs were updated.
       """
       repo = await container.get(JobHistoryRepository)
       n = await repo.reconcile_orphan_running(max_age_seconds=600)
       if n:
           logger.info("orphan_jobs_recovered", marked_failed=n)
   ```

2. **`main.py` — insert call** between `recover_stale_backtests` and `seed_tracked_symbols`:
   ```python
   await recover_stale_backtests(container)
   await recover_orphan_jobs(container)            # ← NEW
   await seed_tracked_symbols(container)
   ```

3. Update the imports in `main.py` to include `recover_orphan_jobs`.

4. Compile-check both files.

## Success Criteria

- [x] `recover_orphan_jobs` defined in `main_extensions.py`, ~6 LOC
- [x] Imported and called in `main.py` lifespan
- [x] Call order: indexes → stale_backtests → orphan_jobs → seed → health → background_jobs
- [x] Log message `orphan_jobs_recovered` fires only when count > 0
- [x] `py_compile` passes both files

## Risk Assessment

- **Risk:** Long-running legitimate job mistakenly flipped. **Mitigation:** 10min threshold; longest observed run (`sync_backfill`) is ~20s. Even if false-flip happens, the wrapper's `record_finish('completed', ...)` will overwrite when the job actually finishes — wrapper writes are `_id`-targeted.
- **Risk:** Reconcile runs before container fully wired. **Mitigation:** Called AFTER `ensure_all_indexes` which already proves DB connectivity.

## Next Steps

Phase 3 (catch-up logic) depends on the same `JobHistoryRepository` methods from phase 1 but doesn't need this lifespan helper.
