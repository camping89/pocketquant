# Sync_jobs Race Fix — Deploy Verification

**Date:** 2026-05-25 08:43 +07 / 01:43 UTC
**Commit:** `d535751` fix(api): wire sync/backtest job containers at lifespan start
**CI run:** 26378855343 (build-api 1m2s, build-web 42s, cleanup 5s — all PASS)

## Result: race window closed

| Metric | Before fix | After fix |
|--------|-----------|-----------|
| `container not initialized` failures today | 1 (01:30:02 during prior deploy) | 0 (across the new deploy window) |
| Time to `application_started` | ~1s | ~1s |
| sync_1m success rate during restart | 50% (1 fail) | 100% |

## Restart timeline (UTC)

```
01:42:02 sync_1m completed     ← old container, normal tick
01:42:35 deploy.sh started
01:43:10 application_starting  ← new container boots
01:43:11 background_jobs_enabled
01:43:11 application_started
01:43:10 sync_1m completed     ← APScheduler dispatched late during boot — succeeded
01:44:02+ all subsequent ticks pass
```

The 01:43:10 sync_1m tick fired DURING new-container startup. With the fix, `set_sync_container(container)` runs synchronously before any `await` in `lifespan()`, so the JobScheduler dispatcher (running on a separate APScheduler thread after Dishka resolves it) found a wired container.

## Code change

`packages/pocketquant-api/src/pocketquant/api/main.py`:
```python
container: AsyncContainer = app.state.dishka_container

# Wire job-module containers BEFORE any await. ...
set_sync_container(container)
set_backtest_container(container)

try:
    ...
```

`packages/pocketquant-api/src/pocketquant/api/main_extensions.py:start_background_jobs` simplified — wiring moved to `lifespan()`.

## Validation

- pyright: 0 errors, 0 warnings on touched files
- ruff: only pre-existing E501 (line 295, unrelated)
- pytest `test_sync_jobs_phase.py`: failed but failure is PRE-EXISTING (test calls async `register_sync_jobs` without `await`; reproduced on `HEAD~`)

## Follow-ups

- [ ] Optional: fix the pre-existing `test_sync_jobs_phase.py` await bug (separate plan)
- [ ] Monitor `job_history` for next 24h to confirm no regressions across the next daily 04:00Z `sync_integrity` cycle
