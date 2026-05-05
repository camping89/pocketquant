# Brainstorm — Job History + Bar Sync Observability

**Date:** 2026-05-05 08:42 ICT (01:53 UTC) | **Branch:** develop | **Symbol scope:** BTCUSDT/BINANCE (only tracked symbol)

---

## 1. Problem Statement (revised after diagnosis)

**Original framing:** "We always have missing bars even though jobs over-fetch."
**Verified reality:** Active intervals have **zero gaps**. The "missing bars" perception comes from:

1. Two **orphan rows** in `sync_status` (`30m`, `2h`) last touched **2026-04-28**, **not in `SYNC_INTERVALS`** → no job covers them → `data-health` UI renders them → integrity check shows ~7-day gap → user reads it as "missing bars".
2. **Zero observability** for APScheduler-level skips (`EVENT_JOB_MISSED`, `EVENT_JOB_MAX_INSTANCES`, `EVENT_JOB_ERROR` before wrapper) — currently no listener registered → silent skips.
3. **Per-job aggregate only** in `job_history` — no per-(symbol, interval) breakdown → cannot localize a future failure to one combo.
4. **Empty-fetch returns `status=completed`** (`handler.py:55-70`) → silent zero-bar runs are indistinguishable from healthy runs.

**Real goal:** Glance-level health of the scheduler + ability to drill into any (job, symbol, interval) run. Plus cleanup orphans.

### Diagnostic data (VPS Mongo, 2026-05-05 01:53 UTC)

| Interval | Bars | Span | Expected | Missing |
|---|---|---|---|---|
| 5m | 15364 | 53.3d | 15364 | **0** |
| 15m | 8481 | 88.1d | 8454 | -27 (slight overcount, fine) |
| 1h | 5864 | 244.3d | 5863 | -1 |
| 4h | 5216 | 869.2d | 5216 | **0** |
| 1d | 3184 | 8.7y | 3184 | **0** |
| **30m** | **5687** | **stale @ 2026-04-28** | — | orphan |
| **2h** | **5171** | **stale @ 2026-04-28** | — | orphan |

Job density last 24h (post-restart 10h ago):

| Job | Runs | Expected |
|---|---|---|
| sync_5m | 287 | 288 |
| sync_15m | 95 | 96 |
| sync_hourly | 23 | 24 |
| sync_swing | 5 | 6 |
| sync_daily | 1 | 1 |
| sync_backfill | 1 | 1 |
| sync_integrity | 1 | 1 |
| sync_repair | 1 | 2 (every 12h) |

99.7% on-schedule. **Zero `failed` rows.** Skips correlate with the deploy.

---

## 2. Approaches Evaluated

### A. Minimal (cleanup only)
- Delete orphan sync_status rows + add a UI filter
- Pros: 5 lines of work
- Cons: leaves observability blind spots — next outage looks identical to today's "missing bars" panic

### B. Targeted (cleanup + scheduler listeners) ★
- A + register `EVENT_JOB_MISSED|MAX_INSTANCES|ERROR` listeners → write synthetic `job_history` rows with status `missed`/`skipped`/`failed`
- Pros: closes the silent-skip blind spot. Small surface.
- Cons: still no per-(symbol,interval) drilldown — future "BTC 4h sync silently failing while 5m works" still invisible

### C. Comprehensive (B + sub-records + UI + robustness) — **Recommended**
- B + extend `job_history.details[]` with per-(symbol,interval) entry → `{symbol, interval, fetched, inserted, filtered_existing, filtered_misaligned, status, error}`
- Empty-fetch alarm: track `consecutive_empty_fetches` per (symbol, interval) on `sync_status`; status `stuck` after threshold
- UI: expand-row in existing `<BackgroundJobsList />` showing last 20 runs as a strip; new `/monitor/jobs/$jobId` route with timeline + filter + per-symbol breakdown + error search
- Robustness: `misfire_grace_time=300s`, `sync_5m n_bars=60` (5h coverage), `sync_swing n_bars=12` (48h coverage)
- Pros: complete picture; future failures are localized in seconds
- Cons: ~3-day implementation, +1 mongo collection-equivalent (history docs grow)

### D. Maximalist (C + separate event log collection + Grafana)
- Cons: YAGNI. 1 symbol, 1 user. Skip.

---

## 3. Recommended Solution (C)

### 3.1 Backend changes

**File: `pocketquant-core/src/pocketquant/core/infrastructure/scheduling/scheduler.py`**

1. Bump `misfire_grace_time: 60 → 300` (5 min). Allows recovery from short scheduler delays without dropping ticks. No downside for non-realtime data jobs.
2. Register APScheduler listeners after `start()`:
   ```python
   from apscheduler.events import EVENT_JOB_MISSED, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_ERROR
   self._scheduler.add_listener(self._on_missed, EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES)
   self._scheduler.add_listener(self._on_error,  EVENT_JOB_ERROR)
   ```
   `_on_missed` writes a `job_history` row with `status="missed"|"skipped_max_instances"`, `started_at=event.scheduled_run_time`, `finished_at=now`, `duration_ms=0`. `_on_error` writes `status="failed"` (idempotent w/ wrapper — pick the more recent one or use unique key on `{job_id, started_at}`).

**File: `pocketquant-core/.../job_history_repository.py`**

3. Schema additions (backward compat — Mongo flexibility):
   ```
   details: [{symbol, exchange, interval, fetched, inserted,
              filtered_existing, filtered_misaligned, status, error_message}]
   total_inserted, total_fetched   # rollups for fast list rendering
   ```
4. New method `record_detail(doc_id, detail)` — push to `details[]`.
5. TTL 7d → **30d**. Diagnostic horizon needs to span monthly issues.
6. New index: `{started_at: -1}` for timeline scans.

**File: `pocketquant-api/.../sync_jobs.py`**

7. `_sync_by_intervals` enriches per-iteration: capture per-(symbol,interval) `SyncResponse` → `record_detail()`. The `SyncResponse` already exposes `bars_synced`. Add `bars_fetched` and `bars_filtered_*` to `SyncResponse` (small DTO change).
8. `_run_sync` rolls up `total_inserted`, `total_fetched` at finish.

**File: `pocketquant-api/.../sync_one/handler.py`**

9. Track and return `bars_fetched`, `filtered_existing`, `filtered_misaligned`. Already counted internally — just surface them in `SyncResponse`.
10. **Empty-fetch alarm:** when `len(records) == 0` and DB has bars, increment `sync_status.consecutive_empty_fetches`. On any non-empty fetch, reset to 0. Threshold (e.g. 5) → mark `sync_status.status = "stuck"` (new enum value alongside `completed|syncing|error`). UI surfaces this.
11. **Bump n_bars in callers** (sync_jobs.py): `sync_5m: 30→60` (5h coverage), `sync_swing: 6→12` (48h coverage), `sync_15m: 30→48` (12h). Storage cost negligible (1 symbol × dedup index).

**Cleanup migration (one-shot):**

12. Mongo command — run once on VPS:
    ```js
    db.sync_status.deleteMany({interval: {$in: ["30m", "2h"]}})
    ```
13. Add a defensive guard in `sync_status_repo.find_all()` callers (data-health route) to filter by `interval ∈ SYNC_INTERVALS` so a future re-introduction of an orphan doesn't reproduce the panic.

### 3.2 Frontend changes (UXUI promax pass)

Skill `ui-ux-pro-max` activates here.

**Existing:** `routes/monitor.tsx`, `components/monitor/background-jobs-list.tsx`.

**New surface:**

1. **In-place enhancement — `<BackgroundJobsList />` row click:**
   - Click row → expand below with **last 20 runs as colored sparkline strip** (each cell = one run, color = green/yellow/red/grey, hover = tooltip {time, duration, inserted, error}).
   - "View details" link → `/monitor/jobs/$jobId`.
2. **New route — `/monitor/jobs/$jobId`** (TanStack Router file-route):
   - **Header:** job name, trigger ("every 5 min"), next run, last run + status pill, P50/P95 duration over 24h.
   - **Timeline chart** (recharts or visx): X = time, Y = duration_ms, color-coded status; hover = full run detail. Toggle between 24h / 7d / 30d.
   - **Filters bar:** status (multi-select chips), symbol, interval, date range, search error message.
   - **Runs table:** `started_at | duration | status | total_inserted | total_fetched | symbols_failed`. Click row → detail drawer.
   - **Detail drawer:** full doc — `details[]` table per (symbol, interval) with badges for filtered/misaligned/error. JSON view fallback.
   - **Empty state:** illustrated, suggests "Run Now" (already exists in API).
3. **`/monitor` page tweaks:**
   - Banner condenses from 3 cards into a status strip with 3 dots: Scheduler / Bars / Symbols. Click → relevant section.
   - Data Health table: hide rows where `interval ∉ SYNC_INTERVALS` by default; toggle "Show inactive intervals".
   - "Stuck" status badge (new) when `consecutive_empty_fetches >= 5`.

**API additions:**
- `GET /api/system/jobs/{job_id}/runs?since=&limit=&status=` → paginated history rows with `details`.
- `GET /api/system/jobs/{job_id}/stats?window=24h|7d|30d` → aggregate { p50, p95, success_rate, missed_count, last_run }.

### 3.3 Style decisions (UXUI promax)

- **Status palette:** completed=`emerald-500`, running=`sky-400`, missed=`amber-400`, skipped=`amber-500`, failed=`rose-500`, stuck=`fuchsia-500`. Consistent across strip/timeline/table/badges.
- **Timeline chart:** thin bars, 2px gap, hover lifts to 1.05x with shadow. Use the project's existing chart lib (verify which during planning).
- **Drawer not modal** — preserves table context (URL-sync via `?run=$id`).
- **Sparkline strip:** tactile, cells exactly 12×24px, rounded-sm, gap-1, last cell pulses if `running`.
- **Density:** monospace font for timestamps + IDs, sans for labels. Two-column compact layout on desktop, single-column stacked on mobile.

---

## 4. Implementation Considerations & Risks

| Risk | Mitigation |
|---|---|
| Listener writes duplicate row when wrapper also writes | Idempotency key `(job_id, scheduled_run_time)` — listener uses `replace_one(upsert=True)` on this key |
| `details[]` array unbounded if symbols grow | YAGNI now (1 symbol). When >50 symbols, switch to child collection `job_run_details`. Document the threshold. |
| `misfire_grace_time=300` masks real lag | Add log warn when grace_time consumed >50% — separate signal |
| TTL=30d retroactively deletes existing 7d data | Existing `created_at` of 7-day docs stays; TTL extension only affects new docs going forward (Mongo TTL semantics) |
| Stuck status sticky across deploys | Reset `consecutive_empty_fetches` on `sync_status` upsert when `bars_synced > 0` (already implied; just verify in handler) |
| Frontend chart library choice | Inspect existing imports in `pocketquant-web` before picking. If none, prefer `recharts` (smaller) over `visx` |
| Orphan deletion irreversible | Take Mongo dump before running `deleteMany` |

---

## 5. Success Metrics & Validation

1. **Cleanup verified:** `db.sync_status.distinct("interval") == ["1d","1h","15m","4h","5m"]`. UI no longer renders 30m/2h rows.
2. **Listener verified:** kill app mid-run → `job_history` shows row with `status=missed`. Verifiable on staging.
3. **Per-(symbol,interval) verified:** `job_history.details[].symbol == "BTCUSDT"` populated for last sync_5m run.
4. **Empty-fetch alarm:** simulate provider returning `[]` → after 5 ticks, `sync_status.status == "stuck"` and UI badge visible.
5. **UI:** `/monitor/jobs/sync_5m` renders timeline + table + drawer. Lighthouse a11y >90.
6. **Robustness:** `misfire_grace_time=300` deployed; 7-day post-deploy missed-run count ≤ pre-deploy / 2.

---

## 6. Phasing (suggested for `/ck:plan`)

- **Phase 1 — Cleanup + observability primitives** (½ day)
  - Mongo `deleteMany` for orphan sync_status
  - `misfire_grace_time` bump
  - APScheduler listeners + idempotent record
  - TTL bump 30d, new index
- **Phase 2 — Per-detail records + empty-fetch alarm** (1 day)
  - `SyncResponse` enrichment, handler counters
  - `JobHistoryRepository.record_detail`
  - `sync_status.consecutive_empty_fetches`, `status="stuck"`
  - n_bars bumps
  - Backend API endpoints (`/runs`, `/stats`)
- **Phase 3 — UI** (1.5 days, UXUI promax)
  - Sparkline strip on row expand
  - `/monitor/jobs/$jobId` route + timeline + table + drawer
  - Data-health filter inactive + Stuck badge
  - A11y + dark mode review

---

## 7. Next Steps & Dependencies

- Confirm chart lib: read `pocketquant-web/package.json` for existing recharts/visx/echarts before planning Phase 3.
- Confirm `Status` enum extension is OK (add `missed`, `skipped`, `stuck`).
- Mongo dump script before Phase 1 deletion.
- Then `/ck:plan` to break Phase 1–3 into phase files under `plans/260505-0842-job-history-and-bar-sync-observability/`.

---

## 8. Unresolved Questions

1. **Chart library** in pocketquant-web — recharts? visx? echarts? Need to inspect package.json before designing timeline.
2. **Multi-instance race for listener writes** — if local-dev BE is also pointed at VPS Mongo, both will write missed events. Idempotency key handles dedup, but worth confirming policy.
3. **`stuck` threshold** — 5 consecutive empty fetches reasonable for 5m (=25 min), but for 4h that's 20h before alarm. Per-interval threshold? Or time-based ("no successful fetch in 2× cadence")?
4. **Retention for `details[]`** — if a single sync_5m row has many details and we keep 30d × 288/day = 8640 docs, with details bloating, is the doc still <16MB? For 1 symbol × 1 interval, fine. Add the >50-symbols threshold note as a doc.
5. **Should sync_repair be more aggressive** post-cleanup? With days_back=7 it cannot heal anything older. Out-of-scope for this brainstorm but flag for follow-up.
