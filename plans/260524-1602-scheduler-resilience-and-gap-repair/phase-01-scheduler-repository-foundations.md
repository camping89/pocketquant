---
phase: 1
title: "Scheduler & repository foundations"
status: completed
priority: P2
effort: "2-3h"
dependencies: []
---

# Phase 1: Scheduler & repository foundations

## Overview

Foundation changes that unblock phases 2-3. Pure additions / minimal behavior changes — no side effects to running jobs.

## Requirements

- Functional:
  - `_on_error` emits exception type + message (or `<Type>(no message)`) instead of bare `""`.
  - `add_cron_job` accepts optional `misfire_grace_time` kwarg that overrides global default.
  - New `JobHistoryRepository.reconcile_orphan_running(max_age_seconds)` returns count of docs flipped.
  - New `JobHistoryRepository.get_last_successful_started_at(job_id)` returns `datetime | None`.
- Non-functional:
  - No behavior change for callers that don't pass `misfire_grace_time` (backwards compat).
  - Repository methods follow existing repo patterns (async, motor, no logger noise on empty result).

## Architecture

```
JobScheduler
  ├── _on_error          ← richer error string
  └── add_cron_job       ← misfire_grace_time kwarg (forward to APScheduler.add_job)

JobHistoryRepository
  ├── reconcile_orphan_running(max_age_seconds=600)  → int
  └── get_last_successful_started_at(job_id)         → datetime | None
```

## Related Code Files

- Modify: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py`
- Modify: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/job_history_repository.py`

## Implementation Steps

1. **`scheduler.py` — `_on_error`:**
   ```python
   def _on_error(self, event):
       exc = event.exception
       if exc is None:
           err = "unknown_error_no_exception"
       else:
           msg = str(exc)
           err = f"{type(exc).__name__}: {msg}" if msg else f"{type(exc).__name__}(no message)"
       self._dispatch_skip(event.job_id, event.scheduled_run_time, "failed", err)
   ```

2. **`scheduler.py` — `add_cron_job`:** add `misfire_grace_time: int | None = None` kwarg. Build `job_kwargs` dict; only inject `misfire_grace_time` when non-None.
   ```python
   def add_cron_job(self, func, *, job_id, cron_expression=None,
                    hour=None, minute=None, second=None, day_of_week=None,
                    misfire_grace_time: int | None = None, **kwargs) -> str:
       ...
       job_kwargs = {"id": job_id, "replace_existing": True, "kwargs": kwargs}
       if misfire_grace_time is not None:
           job_kwargs["misfire_grace_time"] = misfire_grace_time
       self._scheduler.add_job(func, trigger=trigger, **job_kwargs)
       logger.info("scheduler.registered_cron_job", job_id=job_id, ...,
                   misfire_grace_time=misfire_grace_time)
   ```

3. **`job_history_repository.py` — `reconcile_orphan_running`:**
   ```python
   async def reconcile_orphan_running(self, max_age_seconds: int = 600) -> int:
       cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
       result = await self._col.update_many(
           {"status": "running", "started_at": {"$lt": cutoff}},
           {"$set": {
               "status": "failed",
               "finished_at": datetime.now(UTC),
               "error": "orphan_running_recovered",
           }},
       )
       return result.modified_count
   ```

4. **`job_history_repository.py` — `get_last_successful_started_at`:**
   ```python
   async def get_last_successful_started_at(self, job_id: str) -> datetime | None:
       doc = await self._col.find_one(
           {"job_id": job_id, "status": "completed"},
           sort=[("started_at", -1)],
           projection={"started_at": 1},
       )
       return doc["started_at"] if doc else None
   ```

5. Compile-check both files: `python -m py_compile <path>`.

## Success Criteria

- [x] `_on_error` no longer emits `error=""` for any exception type
- [x] `add_cron_job(misfire_grace_time=N)` passes through to APScheduler
- [x] Callers without `misfire_grace_time` unchanged (regression-safe)
- [x] Both new repo methods present, async-compatible with motor
- [x] `py_compile` passes both files
- [x] No new imports beyond stdlib + already-imported

## Risk Assessment

- **Risk:** `add_cron_job` signature change breaks call sites. **Mitigation:** kwarg with default `None` — fully backwards compatible.
- **Risk:** `_on_error` format change breaks log alert regexes. **Mitigation:** additive prefix — keyword greps still match.
- **Risk:** `update_many` race with wrapper writing `record_finish('completed', ...)` mid-reconcile. **Mitigation:** wrapper's update is `_id`-targeted; reconcile filters by `status="running"` + `started_at < cutoff` — wrapper's completed doc no longer matches the filter.

## Next Steps

Unblocks phase 2 (orphan reconcile lifespan) and phase 3 (per-job grace + catch-up).
