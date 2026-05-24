# Scheduler-Resilience Changes — Test Verification Report

**Date:** 2026-05-24  
**Test Run:** 16:39 UTC  
**Total Time:** ~6.2 seconds  
**Status:** DONE_WITH_CONCERNS

---

## Test Execution Summary

| Test Target | Tests Run | Passed | Failed | Time |
|---|---|---|---|---|
| Unit: `test_scheduler_on_error_logging.py` | 5 | 5 | 0 | ~0.08s |
| Unit: `test_sync_jobs_catchup.py` | 4 | 4 | 0 | ~0.21s |
| Integration: `test_job_history_repository.py` | 6 | 5 | 1 | ~5.85s |
| **TOTAL** | **15** | **14** | **1** | **~6.14s** |

---

## Test Results Detail

### 1. Unit Test: `packages/pocketquant-core/tests/unit/infrastructure/scheduling/test_scheduler_on_error_logging.py`

**Status:** ✓ ALL PASSED (5/5)

Tests cover exception formatting in scheduler error logging:
- `test_on_error_formats_exception[None-unknown_error_no_exception]` — PASSED
- `test_on_error_formats_exception[exc1-Exception: real msg]` — PASSED
- `test_on_error_formats_exception[exc2-Exception(no message)]` — PASSED
- `test_on_error_formats_exception[exc3-ValueError(no message)]` — PASSED
- `test_on_error_formats_exception[exc4-CancelledError(no message)]` — PASSED

No warnings or failures.

---

### 2. Unit Test: `packages/pocketquant-api/tests/unit/market_data/test_sync_jobs_catchup.py`

**Status:** ✓ ALL PASSED (4/4)

Tests cover startup catch-up logic for sync jobs:
- `test_catchup_skips_when_no_history` — PASSED
- `test_catchup_skips_when_recent` — PASSED
- `test_catchup_enqueues_when_stale` — PASSED
- `test_catchup_partial_stale_only_enqueues_stale_ones` — PASSED

No warnings or failures.

---

### 3. Integration Test: `packages/pocketquant-core/tests/integration/test_job_history_repository.py`

**Status:** ⚠ 1 FAILURE OUT OF 6

Docker/testcontainers MongoDB started successfully. 5/6 tests passed including all new reconciliation tests.

#### Passing Tests (5/5):
- `test_idempotency_index_tolerates_legacy_null_rows` — PASSED (guards sparse index bug with legacy null rows)
- `test_get_latest_by_job_ids_awaits_aggregate` — PASSED (regression guard for pymongo 4.16 coroutine awaiting)
- `test_record_detail_appends_to_run` — PASSED (per-symbol detail records flow correctly)
- `test_reconcile_orphan_running_flips_only_stale_running` — PASSED (**NEW — guards false positives in orphan recovery**)
- `test_get_last_successful_started_at_returns_none_for_no_history` — PASSED (**NEW — fresh DB case**)

#### Failing Test (1/1):
- `test_get_last_successful_started_at_returns_latest_completed` — **FAILED** (**NEW**)

**Failure Traceback:**

```
TypeError: can't subtract offset-naive and offset-aware datetimes

File packages/pocketquant-core/tests/integration/test_job_history_repository.py:190, in test_get_last_successful_started_at_returns_latest_completed
    result = await repo.get_last_successful_started_at("sync_backfill")
    assert result is not None
    # Mongo stores ms-precision; compare with 1s tolerance.
    assert abs((result - recent_success).total_seconds()) < 1
                    ^^^^^^^^^^^^^^^^^^^^^^^
```

**Root Cause:** The repository method `get_last_successful_started_at()` (line 183–188 in `job_history_repository.py`) returns a raw datetime fetched from MongoDB. When MongoDB's PyMongo driver retrieves a stored datetime, it may return it as naive (no timezone info), but the test inserts timezone-aware UTC datetimes. The subtraction on line 190 fails because one operand is naive and the other is UTC-aware.

**Expected vs Actual:**
- Test inserts: `recent_success = now - timedelta(hours=1)` where `now = datetime.now(UTC)` — UTC-aware
- Returned: naive datetime (no tzinfo)
- Assertion: `(result - recent_success).total_seconds()` → TypeError

**Impact:** Startup catch-up logic relies on this method to compare timestamps; a timezone mismatch could cause caught exceptions in production or incorrect catch-up decisions.

---

## Coverage Assessment

**Critical Code Paths Verified:**

1. ✓ Scheduler error logging — all exception types handled
2. ✓ Sync job catch-up logic — stale detection, selective enqueueing
3. ✓ Job history persistence — index constraints, aggregate queries
4. ✓ Orphan running recovery — only stale "running" docs flipped to "failed"
5. ✗ Last-successful timestamp retrieval — timezone handling bug

**Unmapped/Untested:**
- No test gaps identified in unit or integration suites — all three target files have comprehensive coverage.

---

## Performance Notes

- Unit tests: negligible execution time (~0.08s, ~0.21s)
- Integration tests: ~5.85s (MongoDB container startup + 6 test cases)
- No slow tests identified; Docker container lifecycle normal

---

## Critical Issues

**ISSUE #1: Timezone Mismatch in `get_last_successful_started_at()`**

**Severity:** Medium (affects correctness of catch-up logic)  
**File:** `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/job_history_repository.py:183–188`  
**Fix Required:** Ensure returned datetime is UTC-aware using `coerce_utc()` helper from `pocketquant.core.common.time`

Suggested fix (pseudocode):
```python
from pocketquant.core.common.time import coerce_utc

async def get_last_successful_started_at(self, job_id: str) -> datetime | None:
    doc = await self._collection().find_one(...)
    return coerce_utc(doc["started_at"]) if doc else None
```

---

## Recommendations

1. **High Priority:** Fix timezone handling in `get_last_successful_started_at()` — the method must return UTC-aware datetimes to prevent comparison errors in startup catch-up logic.

2. **Verification:** After fix, re-run integration test suite to confirm `test_get_last_successful_started_at_returns_latest_completed` passes.

3. **Code Pattern:** This pattern (fetch from Mongo → ensure UTC-aware) appears safe elsewhere (e.g., `get_latest_by_job_ids` converts to ISO string before returning), but audit other datetime-returning methods for consistency.

---

## Unresolved Questions

- Does MongoDB's PyMongo codec configuration strip timezone info by default, or is this a driver behavior on Windows? (affects reproducibility on other platforms)
- Should all repository methods return UTC-aware datetimes by contract, or is string/ISO format acceptable? (consistency + API design)
