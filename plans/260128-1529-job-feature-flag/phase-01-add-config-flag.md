# Phase 01: Add Config Flag

## Context
- Parent: [plan.md](plan.md)
- Docs: [src/config.py](../../src/config.py), [src/main.py](../../src/main.py)

## Overview
- **Priority:** P3
- **Status:** Pending
- **Effort:** 15m

## Related Code Files

**Modify:**
- `src/config.py` - Add `enable_jobs` setting
- `src/main.py` - Conditional job registration
- `.env.example` - Document new config

## Implementation Steps

### Step 1: Add config to Settings class
```python
# src/config.py line 41, after job_worker_count
enable_jobs: bool = True
```

### Step 2: Update .env.example
```bash
# Background Jobs
JOB_WORKER_COUNT=4
ENABLE_JOBS=true
```

### Step 3: Conditional job registration in main.py
```python
# src/main.py line 69-71, replace:
JobScheduler.initialize(settings)
JobScheduler.start()
register_sync_jobs()

# With:
if settings.enable_jobs:
    JobScheduler.initialize(settings)
    JobScheduler.start()
    register_sync_jobs()
    set_mediator(mediator)  # Move inside condition
    logger.info("background_jobs_enabled")
else:
    logger.info("background_jobs_disabled")
```

### Step 4: Conditional shutdown
```python
# src/main.py line 119, replace:
JobScheduler.shutdown(wait=True)

# With:
if settings.enable_jobs:
    JobScheduler.shutdown(wait=True)
```

## Todo List
- [ ] Add `enable_jobs: bool = True` to Settings
- [ ] Update `.env.example`
- [ ] Wrap job init/register with condition
- [ ] Wrap job shutdown with condition
- [ ] Test with ENABLE_JOBS=true
- [ ] Test with ENABLE_JOBS=false

## Success Criteria
- App starts without error when `ENABLE_JOBS=false`
- Jobs run normally when `ENABLE_JOBS=true` (default)
- Log message indicates jobs enabled/disabled

## Risk Assessment
- **Low risk:** Simple boolean flag, default true = backward compatible
- No breaking changes
