---
phase: 5
title: "Unit tests"
status: completed
priority: P2
effort: "2-3h"
dependencies: [1, 2, 3]
---

# Phase 5: Unit tests

## Overview

Cover the new logic in phases 1-3 with focused unit tests. No integration tests against real APScheduler — too brittle. Pure function tests for catch-up decision, mocked repo tests for orphan reconcile, parametrized tests for `_on_error` exception formatting.

## Requirements

- Functional:
  - 100% coverage of new branches in `_on_error`, `reconcile_orphan_running`, `get_last_successful_started_at`, `enqueue_missed_catchups`.
- Non-functional:
  - Follow existing test pattern (`testcontainers` Mongo for repo tests, see `packages/pocketquant-core/tests/conftest.py`).
  - Fast (< 5s per file).

## Architecture

```
packages/pocketquant-core/tests/unit/
  └── test_scheduler_on_error_logging.py  ← _on_error formatting (parametrized)

packages/pocketquant-core/tests/integration/
  └── test_job_history_repository_orphan_reconcile.py  ← live Mongo, 2 cases
  └── test_job_history_repository_last_successful.py   ← live Mongo, 2 cases

packages/pocketquant-api/tests/unit/
  └── test_sync_jobs_catchup.py  ← pure logic, mocked deps
```

## Related Code Files

- Create: `packages/pocketquant-core/tests/unit/test_scheduler_on_error_logging.py`
- Modify: `packages/pocketquant-core/tests/integration/test_job_history_repository.py` (if exists) OR create dedicated files above
- Create: `packages/pocketquant-api/tests/unit/test_sync_jobs_catchup.py`

## Implementation Steps

1. **`test_scheduler_on_error_logging.py`** — parametrized test, 4 cases:
   ```python
   import pytest
   from unittest.mock import MagicMock
   from pocketquant.core.infrastructure.scheduling.scheduler import JobScheduler

   @pytest.mark.parametrize("exc, expected_prefix", [
       (None, "unknown_error_no_exception"),
       (Exception("real msg"), "Exception: real msg"),
       (Exception(""), "Exception(no message)"),
       (ValueError(""), "ValueError(no message)"),
   ])
   def test_on_error_formats_exception(exc, expected_prefix):
       scheduler = JobScheduler()
       captured: dict = {}
       scheduler._dispatch_skip = lambda jid, t, s, err: captured.update(err=err)

       event = MagicMock(job_id="x", scheduled_run_time=None, exception=exc)
       scheduler._on_error(event)

       assert captured["err"] == expected_prefix
   ```

   Add a fifth case for `asyncio.CancelledError()` once you confirm Python version pickling:
   ```python
   import asyncio
   (asyncio.CancelledError(), "CancelledError(no message)"),
   ```

2. **Orphan reconcile + last_successful repo tests** — use existing `testcontainers` Mongo fixture:
   ```python
   async def test_reconcile_orphan_running(history_repo):
       # Insert 3 docs
       now = datetime.now(UTC)
       await history_repo._col.insert_many([
           {"_id": "a", "job_id": "x", "status": "running", "started_at": now - timedelta(seconds=30)},
           {"_id": "b", "job_id": "x", "status": "running", "started_at": now - timedelta(minutes=15)},
           {"_id": "c", "job_id": "x", "status": "completed", "started_at": now - timedelta(hours=1)},
       ])
       n = await history_repo.reconcile_orphan_running(max_age_seconds=600)
       assert n == 1
       doc_b = await history_repo._col.find_one({"_id": "b"})
       assert doc_b["status"] == "failed"
       assert doc_b["error"] == "orphan_running_recovered"

   async def test_get_last_successful_started_at_returns_latest(history_repo):
       now = datetime.now(UTC)
       await history_repo._col.insert_many([
           {"_id": "a", "job_id": "j1", "status": "completed", "started_at": now - timedelta(days=2)},
           {"_id": "b", "job_id": "j1", "status": "completed", "started_at": now - timedelta(hours=1)},
           {"_id": "c", "job_id": "j1", "status": "failed",    "started_at": now - timedelta(minutes=5)},
       ])
       result = await history_repo.get_last_successful_started_at("j1")
       # Compare with tolerance — Mongo stores ms precision
       assert abs((result - (now - timedelta(hours=1))).total_seconds()) < 1

   async def test_get_last_successful_returns_none_for_no_history(history_repo):
       assert await history_repo.get_last_successful_started_at("nonexistent") is None
   ```

3. **`test_sync_jobs_catchup.py`** — pure logic with mocked deps:
   ```python
   from datetime import datetime, timedelta, UTC
   from unittest.mock import AsyncMock, MagicMock
   from pocketquant.api.market_data.app_services.sync_jobs import enqueue_missed_catchups

   async def test_catchup_skips_when_no_history():
       repo = AsyncMock()
       repo.get_last_successful_started_at = AsyncMock(return_value=None)
       scheduler = MagicMock()
       await enqueue_missed_catchups(repo, scheduler)
       scheduler.add_one_off_job.assert_not_called()

   async def test_catchup_skips_when_recent():
       repo = AsyncMock()
       repo.get_last_successful_started_at = AsyncMock(return_value=datetime.now(UTC) - timedelta(hours=1))
       scheduler = MagicMock()
       await enqueue_missed_catchups(repo, scheduler)
       scheduler.add_one_off_job.assert_not_called()

   async def test_catchup_enqueues_when_stale():
       repo = AsyncMock()
       # 26h since last sync_backfill > 25h threshold
       repo.get_last_successful_started_at = AsyncMock(return_value=datetime.now(UTC) - timedelta(hours=26))
       scheduler = MagicMock()
       await enqueue_missed_catchups(repo, scheduler)
       assert scheduler.add_one_off_job.call_count >= 1
       # First call should be sync_backfill_catchup
       calls = scheduler.add_one_off_job.call_args_list
       assert any("sync_backfill_catchup" in str(c.kwargs.get("job_id", "")) for c in calls)
   ```

4. Run full test suite locally:
   ```bash
   cd D:/w/_me/algo-bot/pocketquant && uv run pytest packages/ -k "scheduler or job_history or catchup" -v
   ```

5. Verify all green before marking phase complete.

## Success Criteria

- [x] All test files created
- [x] `pytest` exits 0 for new test files
- [x] No flaky tests (run twice locally to confirm)
- [x] Coverage of new branches >= 90% per file (visual confirmation via inspection)

## Risk Assessment

- **Risk:** `testcontainers` Mongo slow on Windows CI. **Mitigation:** Existing tests already use it; no new infra.
- **Risk:** Mocked test of `_on_error` doesn't catch real APScheduler integration. **Mitigation:** Accepted trade-off — integration test would require running APScheduler, which is heavy. Manual VPS verification post-deploy covers it.

## Next Steps

After tests pass: `/ck:cook` ships the plan, then deploy + monitor on VPS.
