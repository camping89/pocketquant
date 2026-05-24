---
phase: 3
title: "Per-job grace + startup catch-up"
status: completed
priority: P1
effort: "2-3h"
dependencies: [1]
---

# Phase 3: Per-job grace + startup catch-up

## Overview

Tune `misfire_grace_time` per job (high cadence: tight, daily: 1h) and add a startup catch-up that enqueues a one-off run when last successful execution exceeded the expected interval. This is the highest-impact item — addresses 3 missed daily jobs/month observed in prod.

## Requirements

- Functional:
  - Each cron registered in `register_sync_jobs` passes `misfire_grace_time` matching its cadence.
  - After cron registration, `enqueue_missed_catchups` scans `job_history` for the three heavy daily/12h jobs and enqueues a one-off run if last success exceeds the per-job `max_gap`.
  - Multi-instance safe (VPS app + local dev pointing at same Mongo).
- Non-functional:
  - Catch-up does NOT fire for `sync_1m` (self-heals via 100-min cascade lookback) or `sync_verify_cascade` (cheap to wait for next tick).
  - Logs `scheduler.catchup_enqueued` with `job_id` + `gap_seconds`.

## Architecture

### Per-job grace table

| Job | Cadence | Grace | Rationale |
|-----|---------|-------|-----------|
| `sync_1m` | every 1m | 120s | Tight — stale tick storms prevention. Cascade lookback handles missed minutes. |
| `sync_verify_cascade` | hourly | 600s | 10-min slip OK for read-only check. |
| `sync_backfill` | daily 03:00 | 3600s | 1h recovery for heavy daily run. |
| `sync_integrity` | daily 04:00 | 3600s | Same. |
| `sync_repair` | every 12h | 1800s | 30-min slip on bi-daily. |

### Catch-up logic

```python
CATCHUP_TARGETS = [
    ("sync_backfill",  f"{_MODULE}:sync_backfill",  86400 + 3600),   # 24h + 1h
    ("sync_integrity", f"{_MODULE}:sync_integrity", 86400 + 3600),
    ("sync_repair",    f"{_MODULE}:sync_repair",    43200 + 1800),   # 12h + 30min
]

async def enqueue_missed_catchups(history_repo, job_scheduler):
    now = datetime.now(UTC)
    for job_id, func_ref, max_gap in CATCHUP_TARGETS:
        last = await history_repo.get_last_successful_started_at(job_id)
        if last is None:
            continue                          # fresh DB — let cron tick handle first
        gap = (now - last).total_seconds()
        if gap > max_gap:
            job_scheduler.add_one_off_job(
                func_ref, job_id=f"{job_id}_catchup",
            )
            logger.info(
                "scheduler.catchup_enqueued",
                job_id=job_id, gap_seconds=int(gap),
            )
```

**Multi-instance safety:** `add_one_off_job` uses `replace_existing=True` + stable `_catchup` suffix → if both VPS and local dev resolve simultaneously, second call overwrites first; only one execution.

## Related Code Files

- Modify: `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py`

## Implementation Steps

1. Add `CATCHUP_TARGETS` constant near top of `sync_jobs.py` (after `SYNC_INTERVALS`).

2. Update each `job_scheduler.add_cron_job(...)` call in `register_sync_jobs` to pass `misfire_grace_time` per table above. Example:
   ```python
   job_scheduler.add_cron_job(
       f"{_MODULE}:sync_1m", job_id="sync_1m",
       cron_expression="*/1 * * * *", second=2,
       misfire_grace_time=120,
   )
   job_scheduler.add_cron_job(
       f"{_MODULE}:sync_backfill", job_id="sync_backfill",
       hour=3, minute=0,
       misfire_grace_time=3600,
   )
   # ...etc for verify_cascade (600), integrity (3600), repair (1800)
   ```

3. Add `enqueue_missed_catchups` function (signature in Architecture above).

4. Refactor `register_sync_jobs` to be `async` and call `enqueue_missed_catchups` AFTER cron registration. Update caller in `main_extensions.py` to `await`:
   ```python
   await register_sync_jobs(
       container=container,
       job_scheduler=await container.get(JobScheduler),
   )
   ```

5. Inside `register_sync_jobs`, resolve `history_repo` from container and pass to `enqueue_missed_catchups`:
   ```python
   async def register_sync_jobs(container, job_scheduler):
       set_container(container)
       # ... add_cron_job calls ...
       history_repo = await container.get(JobHistoryRepository)
       await enqueue_missed_catchups(history_repo, job_scheduler)
       logger.info("market_data.registered_sync_jobs", job_count=5)
   ```

6. Compile-check `sync_jobs.py` + `main_extensions.py`.

## Success Criteria

- [x] All 5 cron jobs registered with per-job `misfire_grace_time`
- [x] `enqueue_missed_catchups` runs after cron registration
- [x] Catch-up enqueues `<job_id>_catchup` one-off when gap exceeds threshold
- [x] `sync_1m` and `sync_verify_cascade` NOT in `CATCHUP_TARGETS`
- [x] `register_sync_jobs` now `async`, caller in `main_extensions.py` updated to `await`
- [x] `py_compile` passes
- [x] Log line `scheduler.catchup_enqueued` includes `job_id` + `gap_seconds`

## Risk Assessment

- **Risk:** Fresh DB → catch-up storm. **Mitigation:** `if last is None: continue`.
- **Risk:** Catch-up + normal cron double-fire. **Mitigation:** `coalesce=True` global default + `max_instances=1` prevents overlap.
- **Risk:** `sync_1m` 120s grace drops ticks on host pause. **Mitigation:** `cascade_for_symbol(lookback_minutes=100)` repairs within 2h.
- **Risk:** Catch-up triggers immediately for sync_backfill at boot when system was just down 25h. Heavy job fires while other startup work still in flight. **Mitigation:** `register_sync_jobs` is called at the end of lifespan startup sequence — backfill running alongside is acceptable (it ran daily without issue when the cron fired normally).

## Next Steps

Phase 4 (audit script + runbook) verifies whether prior missed-daily-runs actually left data gaps.
