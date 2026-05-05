# Bar Sync Job System Scout Report
**Date**: 2026-05-05 | **CWD**: D:\w\_me\pocketquant

---

## 1. SYNC JOB CODE & SCHEDULER SETUP

### Scheduler Core
**File**: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py`

- **Class**: `JobScheduler` (lines 36-225)
- **Jobstore**: `MongoDBJobStore` (line 50) — collection: `"apscheduler_jobs"`
- **Executor**: `AsyncIOExecutor` (line 56)
- **Triggers**: `IntervalTrigger`, `CronTrigger` (via APScheduler 4.x)
- **Key methods**:
  - `add_interval_job()` (line 83) — register repeating jobs
  - `add_cron_job()` (line 128) — register scheduled jobs
  - `get_jobs()` (line 188) — returns enriched job list with history via `JobHistoryRepository.get_latest_by_job_ids()`
  - `run_job_now()` (line 214) — force immediate execution

### Job Definitions
**File**: `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py`

**Registered Jobs** (lines 267–329):
1. `sync_5m()` — 5-minute bars (30 bars per sync)
2. `sync_15m()` — 15-minute bars (30 bars)
3. `sync_hourly()` — 1-hour bars (10 bars)
4. `sync_swing()` — 4-hour bars (6 bars)
5. `sync_daily()` — Daily bars (7 bars) — runs at 00:30 UTC
6. `sync_backfill()` — **Backfill all intervals** (5000 bars) — runs daily at 03:00 UTC
7. `sync_integrity()` — Gap/alignment check (runs daily at 04:00 UTC)
8. `sync_repair()` — Delete misaligned + resync gaps (every 12 hours)

**Backfill Logic**:
- `sync_backfill()` (line 287) → `_run_sync("sync_backfill", SYNC_INTERVALS, 5000)` (line 288)
- Requests 5000 bars per symbol/interval (vs. 10–30 for regular syncs)
- Scheduled daily at 03:00 UTC (line 322)

**History Recording** (lines 131–163):
- Wrapper `_run_sync()` calls `history_repo.record_start()` at start (line 140)
- Records completion status + duration_ms + error (if any) at line 147–158
- Pattern repeated for `_run_integrity()` (lines 166–209) and `_run_repair()` (lines 212–258)

---

## 2. JOB PERSISTENCE & STATE

### Job History Collection
**File**: `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/job_history_repository.py`

- **Constant**: `COLLECTION_JOB_HISTORY = "job_history"` (constants.py:19)
- **Repository Class**: `JobHistoryRepository` (lines 17–95)
- **Schema** (from `record_start()` lines 22–36):
  ```
  {
    "_id": string (uuid),
    "job_id": string (e.g. "sync_5m"),
    "started_at": datetime,
    "finished_at": datetime | null,
    "duration_ms": int | null,
    "status": "running" | "completed" | "failed",
    "error": string | null
  }
  ```
- **Methods**:
  - `record_start(job_id)` → returns doc_id (line 22)
  - `record_finish(doc_id, status, duration_ms, error)` → updates doc (line 38)
  - `get_latest_by_job_ids(job_ids)` → aggregation pipeline returns {job_id: last_run_doc} (line 60)
  - `ensure_indexes()` → creates compound idx `(job_id, started_at)` + TTL idx (7 days) (lines 82–94)

### APScheduler Job Storage
- **Collection**: `apscheduler_jobs` (scheduler.py:52)
- **Persistence**: MongoDBJobStore manages job state, next_run_time
- **Race condition**: Multiple processes (local dev + VPS) coordinate via Mongo; first to update `next_run_time` wins each tick (lines 46–48)

---

## 3. BAR REPOSITORY & DEDUP/GAP DETECTION

**File**: `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py`

**Collection**: `"bars"` (constants.py:12)

**Insert Logic** (lines 21–56):
- `insert_many(records)` — bulk insert with `ordered=False`
- Handles `BulkWriteError` gracefully; skips duplicates, inserts rest
- Returns count of newly inserted (not skipped)
- **Dedup via MongoDB unique index** on `(symbol, exchange, interval, datetime)`

**Upsert Single Bar** (lines 58–85):
- Upsert match key: `{symbol, exchange, interval, datetime}`
- Ensures created_at is set on insert only (line 70)
- Updates updated_at on every upsert (line 65)

**Gap Detection** (lines 170–191):
- `find_datetimes()` — returns lightweight `[{_id, datetime}]` docs sorted asc
- Used by integrity check to find missing timestamps in range

**Example Usage in Integrity**:
```python
# integrity_jobs.py:50
docs = await bar_repo.find_datetimes(symbol, exchange, interval, start, end)
# Extract aligned timestamps, compute expected grid, find gaps
```

---

## 4. UI PAGE FOR JOBS

### Monitor Page Route
**File**: `packages/pocketquant-web/src/routes/monitor.tsx` (lines 1–58)

- **Route**: `/monitor`
- **Components**:
  - `<BackgroundJobsList />` — displays all jobs with status (line 55)
  - `<DataHealthTable />` — per-symbol/interval health (lines 50–54)
  - `<HealthBanner />` — high-level status (lines 45–49)

### Background Jobs Table Component
**File**: `packages/pocketquant-web/src/components/monitor/background-jobs-list.tsx` (lines 1–61)

- Fetches jobs via `useBackgroundJobs()` hook
- Columns: Job ID, Trigger, Last Run (started_at), Duration, Next Run, Status
- Status logic (lines 6–13):
  - `last_run?.status === 'failed'` → error (red)
  - Overdue (>60s past next_run) → warn (yellow)
  - Never run → neutral (grey)
  - Otherwise → ok (green)

### Health/Data Health Components
**Files**: 
- `components/monitor/data-health-detail.tsx`
- `components/monitor/data-health-row.tsx`
- `components/monitor/data-health-table.tsx`

---

## 5. APSCHEDULER LIBRARY & HOOKS

**Version**: APScheduler 4.x

**Imports** (scheduler.py):
```python
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
```

**Event Hooks Available** (APScheduler standard):
- `scheduler_started` / `scheduler_shutdown`
- `job_added` / `job_removed` / `job_modified`
- `job_submitted` / `job_executed` / `job_error` / `job_missed`

**Current Implementation**: 
- No explicit event listeners registered in JobScheduler
- History recording happens **inside job functions** (not via scheduler events) — see `_run_sync()` wrapper

---

## 6. RECENT COMMITS

### Commit 89241ea: MongoDBJobStore Rollout
**Date**: 2026-05-04 23:08:26 UTC
**Files Changed**: 11
**Lines Changed**: +471 / −132

**Key Changes**:
- MemoryJobStore → MongoDBJobStore (distributed coordination)
- `sync_jobs.py`: Refactored into picklable module-level coroutines
  - Old: Instance methods with closures (not serializable)
  - New: Text references like `"pocketquant.api.market_data.app_services.sync_jobs:sync_5m"`
  - Dependencies resolved at exec time via module-level `_container` ref
- History recording moved **into job functions** (not scheduler middleware)
- Tests: testcontainers (ephemeral mongo + redis) replace `.env.test`
- Cleanup: removed JOB_WORKER_COUNT env var, mongo-express service

---

## 7. CURRENT ARCHITECTURE SUMMARY

### Job Execution Flow
1. **APScheduler** ticks in background (AsyncIOScheduler with MongoDBJobStore)
2. **Next scheduled job** → mediator pattern sends `SyncSymbolCommand` to market data handler
3. **SyncSymbolCommand** (sync_one/handler.py):
   - Filters already-fetched bars (unless `skip_filter=True`)
   - Filters misaligned bars (via BarBuilder alignment check)
   - Upserts into MongoDB bars collection (dedup on composite key)
4. **History recording** → Wrapper (`_run_sync`) catches start/finish, records to `job_history` collection
5. **Integrity job** (`sync_integrity`):
   - Queries bar_repo for last 7 days (default)
   - Detects missing timestamps (gaps) + misaligned bars
   - Logs findings (does NOT repair by default)
6. **Repair job** (`sync_repair`):
   - Calls `check_integrity()` then deletes misaligned bars
   - Re-syncs gaps via `SyncSymbolCommand(..., skip_filter=True)`
   - Verifies repair success

### Missing-Bar Handling (Current)
- **Detection**: `sync_integrity()` finds gaps via `find_datetimes()` + grid calculation (integrity_jobs.py:34-74)
- **Repair**: `sync_repair()` deletes misaligned docs + resyncs gaps (lines 77–128)
- **Gap Ranges Tracked**: Grouped consecutive missing timestamps (lines 16–31)
- **Limitation**: Only checks last 7 days; equity markets produce false positives on weekends

### Bar Dedup Logic
- **Key**: `(symbol, exchange, interval, datetime)` — implicit unique index
- `insert_many()` with `ordered=False` + catches `BulkWriteError`
- Counts successfully inserted vs. skipped duplicates

---

## 8. WHERE JOB-RUN-HISTORY FITS

**Already Exists**: `job_history` collection with full execution records.

**Natural Fit for Extension**:
- Add per-job **bar statistics** (bars_synced, bars_skipped, gaps_detected) to history doc
  - Store alongside `duration_ms` and `error`
  - Enable UI to show "sync_5m: 150 bars synced, 2 gaps" in history
- Add **repair results** to `sync_repair()` job history
  - Track `{deleted_count, resynced_count, still_missing_after}`
  - Detect repair failures (still_missing > 0)
- Add **collection** for audit trail (append-only):
  - `job_execution_events`: `{timestamp, job_id, event_type, details}`
  - Enables drill-down UI: "see all runs of sync_5m in last 7 days"

**Existing Schema Handles Basic Needs**:
- Status (running/completed/failed)
- Duration
- Error message
- TTL auto-cleanup (7 days)

---

## 9. KEY FILE PATHS

| Component | Path | Lines |
|-----------|------|-------|
| Scheduler | `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py` | 36-225 |
| Sync Jobs | `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/sync_jobs.py` | 1-332 |
| Integrity Jobs | `packages/pocketquant-api/src/pocketquant/api/market_data/app_services/integrity_jobs.py` | 1-129 |
| Job History Repo | `packages/pocketquant-core/src/pocketquant/core/infrastructure/scheduling/job_history_repository.py` | 1-95 |
| Bar Repository | `packages/pocketquant-core/src/pocketquant/core/persistence/repositories/bar_repository.py` | 1-210+ |
| BarBuilder | `packages/pocketquant-core/src/pocketquant/core/domain/bar/services/bar_builder.py` | 1-121 |
| Monitor Page | `packages/pocketquant-web/src/routes/monitor.tsx` | 1-58 |
| Background Jobs UI | `packages/pocketquant-web/src/components/monitor/background-jobs-list.tsx` | 1-61 |
| API Endpoint | `packages/pocketquant-api/src/pocketquant/api/main_extensions.py` | 145-147 |
| Constants | `packages/pocketquant-core/src/pocketquant/core/common/constants.py` | 1-62 |

---

## UNRESOLVED QUESTIONS

1. **Gap Root Cause**: Why are gaps appearing? Is it exchange downtime, fetch failures, filter dropping bars, or data provider lag?

2. **Repair Verification**: If gaps reappear within 7 days after repair, is there follow-up sync?

3. **Backfill vs. Gap Fill**: Do `sync_backfill` (5000 bars) + `sync_repair` (skip_filter=True) fully cover missing bars?

4. **Multi-Instance Race Conditions**: Do concurrent repairs on same symbol/interval cause race conditions in `delete_many_by_ids()`?

5. **Equity Market False Positives**: Integrity check assumes 24/7 markets. How to handle weekend gaps in equity data?
