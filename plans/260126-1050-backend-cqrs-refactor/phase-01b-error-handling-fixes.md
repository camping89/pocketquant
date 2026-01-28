# Phase 1B: Error Handling Fixes

## Context
- Brainstorm identified bare `except Exception:` without logging
- Lines: `scheduler.py:163`, `tradingview_ws.py:204`

## Overview
- **Priority:** P2
- **Status:** Pending
- **Effort:** 20 min
- **Parallelizable:** Yes (no file overlap with 1A, 1C)

## Key Insights
- Bare `except` swallows errors silently
- At minimum: log the error
- Better: catch specific exceptions where possible

## Requirements

### Functional
- Replace bare `except Exception:` with specific exception or logged catch
- Maintain existing return behavior

### Non-functional
- All errors logged for debugging
- No behavior change for callers

## Files

### Modify
- `src/common/jobs/scheduler.py` (line 163)
- `src/features/market_data/providers/tradingview_ws.py` (line 204)

## Implementation Steps

### Step 1: Fix scheduler.py (line 163)
**Current:**
```python
except Exception:
    logger.warning("scheduler.job_not_found", job_id=job_id)
    return False
```

**Analysis:** Already has logging! The warning is logged. However, could be more specific.

**Fix (optional improvement):**
```python
from apscheduler.jobstores.base import JobLookupError

try:
    cls._scheduler.remove_job(job_id)
    logger.info("scheduler.removed_job", job_id=job_id)
    return True
except JobLookupError:
    logger.warning("scheduler.job_not_found", job_id=job_id)
    return False
```

### Step 2: Fix tradingview_ws.py (line 204)
**Current:**
```python
async def _send_heartbeat(self) -> None:
    if self._ws is not None:
        try:
            await self._ws.send("~h~1")
        except Exception:
            pass
```

**Fix:**
```python
async def _send_heartbeat(self) -> None:
    if self._ws is not None:
        try:
            await self._ws.send("~h~1")
        except Exception as e:
            logger.debug("tradingview_ws.heartbeat_failed", error=str(e))
```

Note: Using `debug` level since heartbeat failures are expected during disconnect.

## Todo

- [ ] Update scheduler.py with `JobLookupError` specific catch
- [ ] Update tradingview_ws.py to log heartbeat failures
- [ ] Run linting
- [ ] Run tests

## Success Criteria
- [ ] No bare `except:` without logging
- [ ] Specific exception types where available
- [ ] All tests pass

## Risks
- None - additive logging only, no behavior change
