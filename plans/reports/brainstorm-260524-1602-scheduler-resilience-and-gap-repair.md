# Brainstorm — Scheduler Resilience + Sync Gap Repair

**Date:** 2026-05-24 16:02 UTC+7
**Context:** Carry-forward items from `brainstorm-260524-1504-sync-jobs-container-race-fix.md`
**Predecessor PR (already shipped):** sync_jobs container race fix (`9a8dcf9` → rebased `45e2d7f`)
**Scope:** Single PR bundling: improved scheduler error logging + orphan reconcile, per-job misfire grace + startup catch-up, gap audit script, ops runbook update.

---

## Problem Statement

Three carry-forward items from prior brainstorm:

1. **`sync_1m` 2026-05-23 06:25 failure** with empty `error=""` — root cause unknown until now.
2. **`misfire_grace_time=300s` too tight for daily cron** — `sync_backfill` (03:00 UTC) drops entire day's run if container restart spans the window.
3. **May 21 + May 23 gaps** in bar data possibly left by race-induced sync_1m failures.

## Diagnostic Evidence (queried 2026-05-24 from VPS)

**Item 1 — empty-error root cause:**
- 06:25:02 has TWO `job_history` docs: wrapper-path stuck at `status=running` (never finished) + listener-path with `status=failed, error=""`.
- `error=""` from `scheduler._on_error` calling `str(event.exception)` — `str(asyncio.CancelledError())` is empty.
- 06:26+ logs show a NEW error (`"Invalid composite symbol 'BTCUSDT'"`) → code deploy happened in that minute.
- Verdict: not a sync_1m bug. Deploy-time job cancellation. Logging deficiency masked the real cause.

**Item 2 — missed daily jobs:**
| job_id | completed | missed | failed (30d) |
|--------|-----------|--------|--------------|
| sync_1m | 12,717 | 0 | 16 |
| sync_verify_cascade | 213 | 3 | 2 |
| sync_backfill | 17 | **3** | 0 |
| sync_integrity | 17 | 2 | 1 |
| sync_repair | 33 | 3 | 0 |

Daily jobs missed on 2026-05-08, 05-11, 05-21 — all restart days. 300s grace ≠ enough.

**Item 3 — actual gap risk:**
- `sync_1m` self-heals via `cascade_for_symbol(lookback_minutes=100)` → cascade outputs (5m/15m/1h/4h/1d) repaired within ~2h of any failed minute.
- 1m bars themselves: each `sync_1m` REST-fetches 100 bars per run → 100-minute self-heal window.
- Only **deep gaps beyond ~2h around a missed `sync_backfill`** would persist. Likely none, but worth verifying.

---

## Final Recommended Design (Approved)

### Item 1 — Logging fidelity + orphan reconcile

#### 1a. `JobScheduler._on_error` better exception capture
File: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py`

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

Result: `CancelledError(no message)` instead of `""`. Greppers still match existing prefixes.

#### 1b. Orphan-running reconciliation on startup
File: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/job_history_repository.py`

New method:
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

File: `packages/pocketquant-api/src/pocketquant/api/main_extensions.py`

New helper `recover_orphan_jobs(container)` mirroring `recover_stale_backtests()`.

File: `packages/pocketquant-api/src/pocketquant/api/main.py`

Lifespan order:
```
ensure_all_indexes
recover_stale_backtests
recover_orphan_jobs       # ← NEW (after stale_backtests, before background_jobs)
seed_tracked_symbols
register_health_checks
start_background_jobs
start_quote_feed
```

Threshold: 10 min. Longest observed sync_backfill run ~20s → safe margin.

---

### Item 2 — Per-job misfire grace + startup catch-up

#### 2a. `add_cron_job` accepts `misfire_grace_time`
File: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py`

```python
def add_cron_job(self, func, *, job_id, ..., misfire_grace_time: int | None = None, **kwargs):
    job_kwargs = {"id": job_id, "replace_existing": True, "kwargs": kwargs}
    if misfire_grace_time is not None:
        job_kwargs["misfire_grace_time"] = misfire_grace_time
    self._scheduler.add_job(func, trigger=trigger, **job_kwargs)
```

#### 2b. Per-job grace values
File: `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py`

| Job | Cadence | Grace | Why |
|-----|---------|-------|-----|
| `sync_1m` | every 1m | **120s** | Prevent stale tick storms; cascade lookback self-heals |
| `sync_verify_cascade` | hourly | **600s** | 10-min slip acceptable on read-only check |
| `sync_backfill` | daily 03:00 | **3600s** | Full hour to recover heavy daily run |
| `sync_integrity` | daily 04:00 | **3600s** | Same |
| `sync_repair` | every 12h | **1800s** | 30-min slip on bi-daily |

#### 2c. Startup catch-up (inside `register_sync_jobs`)

```python
CATCHUP_TARGETS = [
    # (job_id, func_ref, expected_max_gap_seconds)
    ("sync_backfill",  f"{_MODULE}:sync_backfill",  86400 + 3600),
    ("sync_integrity", f"{_MODULE}:sync_integrity", 86400 + 3600),
    ("sync_repair",    f"{_MODULE}:sync_repair",    43200 + 1800),
]
# sync_1m + sync_verify_cascade EXCLUDED — self-heal or cheap to wait

async def enqueue_missed_catchups(history_repo, job_scheduler):
    now = datetime.now(UTC)
    for job_id, func_ref, max_gap in CATCHUP_TARGETS:
        last = await history_repo.get_last_successful_started_at(job_id)
        if last is None:
            continue  # fresh DB / never run — let cron tick handle first
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

Called from `register_sync_jobs` AFTER all cron jobs registered. Multi-instance safe via `replace_existing=True` + stable `_catchup` suffix.

New repo method `get_last_successful_started_at(job_id)`:
```python
async def get_last_successful_started_at(self, job_id: str) -> datetime | None:
    doc = await self._col.find_one(
        {"job_id": job_id, "status": "completed"},
        sort=[("started_at", -1)],
    )
    return doc["started_at"] if doc else None
```

---

### Item 3 — Audit + targeted backfill

#### 3a. Audit script `scripts/audit_bar_gaps.py`

CLI tool. For each tracked symbol × `SYNC_INTERVALS`, queries `bars` collection for actual count in given window, compares against expected (1440 bars/day for 1m, 288 for 5m, etc).

```
usage: audit_bar_gaps.py --dates 2026-05-08,2026-05-11,2026-05-21 [--window-hours 6]
Output:
  symbol      | interval | window                              | expected | actual | gap
  BTCUSDT:... | 1m       | 2026-05-21T00:00..2026-05-21T06:00 | 360      | 360    | 0
  BTCUSDT:... | 1m       | 2026-05-08T00:00..2026-05-08T06:00 | 360      | 358    | -2 ⚠
```

Reads `MONGODB_URL` from env (same pattern as other scripts).

#### 3b. Ops runbook
Append to `docs/deployment-guide.md` as new section **"Sync Gap Repair"** (does NOT create new doc file — respects project rule).

Steps:
1. Run `python scripts/audit_bar_gaps.py --dates 2026-05-08,2026-05-11,2026-05-21`
2. If gaps found for `(symbol, interval)`:
   ```
   curl -X POST http://localhost:$APP_PORT/api/v1/market-data/sync \
     -H 'Content-Type: application/json' \
     -d '{"symbol":"BTCUSDT:BINANCE","interval":"1m","n_bars":5000}'
   ```
3. Re-run audit script to verify.

---

## Tests (approved)

1. **`tests/unit/test_scheduler_on_error_logging.py`** — mocks `event.exception` with: None, `Exception("real msg")`, `Exception("")`, `CancelledError()`. Asserts emitted error strings.
2. **`tests/unit/test_job_history_repository.py`** — adds two new test cases:
   - `reconcile_orphan_running`: insert 3 docs (1 running fresh, 1 running stale, 1 completed) → call → assert 1 modified.
   - `get_last_successful_started_at`: returns latest completed; returns None when no completions.
3. **`tests/unit/test_sync_jobs_catchup.py`** — pure logic test of `enqueue_missed_catchups` with mocked repo + scheduler. Cases: no history → no enqueue, fresh history → no enqueue, stale history → enqueue.

No integration tests for orphan reconcile on real Mongo — covered by unit test against `testcontainers` Mongo per existing repo test pattern.

---

## File Touch List (Single PR)

| File | Change | Net LOC |
|------|--------|---------|
| `packages/pocketquant-core/src/.../scheduling/scheduler.py` | `_on_error` + `add_cron_job` grace kwarg | ~15 |
| `packages/pocketquant-core/src/.../scheduling/job_history_repository.py` | 2 new methods | ~25 |
| `packages/pocketquant-api/src/.../main_extensions.py` | `recover_orphan_jobs` helper | ~12 |
| `packages/pocketquant-api/src/.../main.py` | 1-line call insertion | ~1 |
| `packages/pocketquant-api/src/.../market_data/app_services/sync_jobs.py` | Per-job grace + `enqueue_missed_catchups` | ~40 |
| `scripts/audit_bar_gaps.py` | New CLI audit script | ~80 |
| `docs/deployment-guide.md` | New "Sync Gap Repair" section | ~40 |
| `tests/unit/test_scheduler_on_error_logging.py` | 4 cases | ~50 |
| `tests/unit/test_job_history_repository.py` | 2 new cases | ~40 |
| `tests/unit/test_sync_jobs_catchup.py` | 3 cases | ~60 |
| **Total** | | **~363** |

---

## Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Orphan threshold kills in-flight job | Job marked failed wrongly | Very low | 10 min default; longest observed run ~20s |
| Fresh-DB catch-up storm | Multiple heavy jobs at boot | Low | `if last is None: skip` |
| `sync_1m` 120s grace drops ticks on host pause | Missing 1-2 min of cascade | Low | 100-min cascade lookback self-heals |
| Two processes both enqueue catchup | Duplicate run | Low | `replace_existing=True` + stable `_catchup` job_id |
| Catch-up + normal cron double-fire | Heavy job runs twice | Very low | `coalesce=True` global; `max_instances=1` |
| New `_on_error` format breaks log alerts | Alert misses | Low | Additive prefix; existing keyword greps still match |
| `reconcile_orphan_running` collides with restart-killed job that legitimately resumes | Doc says failed but job actually completes later | Very low | Wrapper writes `record_finish('completed', ...)` overwrites status field |

---

## Implementation Considerations

- **Boot ordering matters:** `recover_orphan_jobs` MUST run BEFORE `start_background_jobs` so a fresh scheduler doesn't see lingering "running" status from the previous incarnation. Current order in `main.py` already supports this insertion point.
- **`_catchup` suffix vs original `job_id`:** Distinct job_id prevents collision with cron registration. Use `f"{job_id}_catchup"`.
- **Cron tick + catchup ordering:** If catchup fires first and main cron is due within `max_instances=1` window, cron's run will block. Acceptable — they do the same work.
- **MongoDBJobStore distributed:** Both VPS app + local dev can be running. Catchup decision is racy; `replace_existing=True` makes the resulting state deterministic.
- **Catch-up not in scope for `sync_1m`:** explicit choice. Lookback in `cascade_for_symbol` already handles it.

---

## Success Metrics

After deploy, within 30 days:
- Zero `job_history` docs with `error=""`.
- Zero `job_history` docs stuck in `status="running"` longer than 11 min.
- For each restart day: each daily job (`sync_backfill`, `sync_integrity`) has either a completed scheduled run OR a completed catchup run (NOT a `missed` event).
- Audit script verifies bar count parity ±0.1% per (symbol, interval, day).

Validation procedure post-deploy:
1. Apply fix, deploy.
2. Force a restart at `02:58 UTC` (skipping `sync_backfill` at 03:00).
3. Wait 10 min after boot.
4. Query `job_history`: expect a `sync_backfill_catchup` completed doc.
5. Query `bars`: expect parity with prior day.

---

## Out of Scope

- WS layer reconnection patterns (`WsSubscriptionManager` / `quote_app_service`) — separate concern; already has its own reconnect logic verified working in deploy logs.
- Migration of legacy `error=""` docs to backfilled exception type — historical data left as-is.
- Distributed coordination beyond `replace_existing=True` (e.g. leader election) — overkill for 2-process setup.

---

## Next Step

If user approves: invoke `/ck:plan` with this brainstorm as context to break into implementation phases.

Suggested phase layout (preview):
- **Phase 1:** Scheduler logging + JobHistoryRepository methods (foundations, no behavior change to running jobs)
- **Phase 2:** Orphan reconcile lifespan integration
- **Phase 3:** Per-job grace + catch-up logic in sync_jobs
- **Phase 4:** Audit script + ops runbook
- **Phase 5:** Unit tests (per phase or end)

---

## Unresolved Questions

None — design fully spec'd. Implementation can proceed.
