# Scheduler Resilience and Sync Gap Repair: APScheduler + Missing Job Recovery

**Date:** 2026-05-24 16:30
**Severity:** High (deployed resilience + data-integrity safety net)
**Component:** APScheduler orchestration, sync_jobs recovery, job history, bar gap auditing
**Status:** Shipped to develop (commit 38f04eb)

## What Happened

Shipped 5-phase scheduler hardening and sync-gap repair on top of the predecessor sync_jobs race fix (9a8dcf9 → 45e2d7f). Three specific brittle behaviors converted to resilience patterns: `_on_error` now logs exception types properly (was masking CancelledError as "unknown failure" during deploy restarts), wrapper-path status stops getting stuck at `running` when a job is killed before `record_finish`, and the global 300s `misfire_grace_time` no longer silently drops ~3 daily jobs/month during restarts that span the maintenance window. Added `JobHistoryRepository.reconcile_orphan_running()` to detect and clear stale orphaned states, per-job grace windows (sync_1m=120s, verify=600s, daily=3600s, repair=1800s), and `enqueue_missed_catchups` to queue one-off catchup jobs for daily/12h jobs that drifted stale during downtime. New audit CLI `scripts/audit_bar_gaps.py` introspects bar history across date ranges and intervals. All 15 tests pass; zero critical/high code-review findings.

## The Brutal Truth

This was the cleanest phase of the entire sync-jobs repair arc. Plan executed as written; code review had teeth but no blockers; testing caught one subtle bug (datetime coercion) that would have haunted monitoring. The hardest part was architectural: justifying per-job grace windows and catchup logic WITHOUT making the scheduler opaque. Three decisions nearly failed: (1) whether catchup jobs should reference the original `job_id` or use a `_catchup` suffix (chose suffix to isolate namespaces, let original job_id anchor history lookups); (2) whether multi-instance boot races on `enqueue_missed_catchups` would silently duplicate catchups (safe because `replace_existing=True` + APScheduler's distributed race pattern on `next_run_time`; documented); (3) whether we'd ever actually validate the post-deploy fix (deferred — requires a 02:58 UTC restart to skip the 03:00 daily cron, impractical to schedule, trusting tests + organic monitoring).

## Technical Details

**Six concrete changes:**

1. **_on_error logging:** `task.exception` now emits `{exc.__class__.__name__}: {str(exc)}` or `{exc.__class__.__name__}(no message)` or `unknown_error_no_exception` if exception is None. Reveals deploy-cancellations (CancelledError), not just noise.

2. **Wrapper-path recovery:** `JobHistoryRepository.reconcile_orphan_running(max_age_seconds=600)` finds any history doc with `status="running"` and `started_at < now - 600s` (stale), sets status to `"error"`, records `exit_code=None` (killed mid-job). Runs at lifespan startup between `recover_stale_backtests` and `seed_tracked_symbols`.

3. **Per-job misfire grace:** `add_cron_job(job_id, cron, misfire_grace_time: int | None = None, ...)`. Defaults to None (use scheduler's global 300s). Sync jobs override per use-case: sync_1m=120s (tight, retries daily), verify=600s (loose, once-daily), daily={sync_backfill,sync_integrity,sync_repair}=3600s (1h grace for multi-minute deploys), daily catch-routes=1800s. Per-job grace beats global grace; misfire windows are now explicit and auditable.

4. **Catchup mechanism:** `register_sync_jobs` is now async. Post-register, `enqueue_missed_catchups` iterates daily/12h jobs, calls `get_last_successful_started_at(job_id)`, and if `started_at < now - job_catchup_window`, queues `add_one_off_job(f"{job_id}_catchup", ...)` with `replace_existing=True`. Namespace isolation: original job_id anchors `JobHistoryRepository` queries; `_catchup` suffix isolates APScheduler jobs. Next boot's `get_last_successful_started_at("sync_backfill")` then sees the recent success and skips.

5. **New repo method:** `JobHistoryRepository.get_last_successful_started_at(job_id: str) -> datetime | None`. Returns the most recent `started_at` from a history doc with `status="success"`. Returns raw Mongo value; motor strips tzinfo on read. Caller MUST coerce via `coerce_utc(...)` before subtracting from `datetime.now(UTC)` — this is a code contract. Caught by integration test when we forgot; TypeError: can't subtract offset-naive and offset-aware.

6. **Audit CLI:** `scripts/audit_bar_gaps.py --dates 2026-05-20,2026-05-24 --intervals 1m,5m,1h`. Iterates tracked symbols, computes expected bars per interval (ceiling of window hours / interval hours), queries actual count from BarRepository, outputs `symbol,interval,window_start,window_end,expected,actual,gap` as CSV. Exit 0 (no gaps) or 1 (gaps found). Early version had off-by-one in expected_bars (floor division → undercount); code review flagged it; fix was `math.ceil(window_hours / interval_hours)`.

**Architectural note:** Catchup job_id uses stable `_catchup` suffix, but the history doc written by the wrapper uses the ORIGINAL job_id. Two distinct namespaces intentionally — the next boot's `get_last_successful_started_at("sync_backfill")` sees the success and skips. Easy to confuse when reading `/runs` dashboard.

## What We Tried

1. **Orphaned state detection:** First iteration queried APScheduler jobs table for missing entries and marked them as "missing" in history. Too fragile (APScheduler truncates on upgrade). Switched to time-based heuristic: any history doc with `status="running"` and `started_at > 600s` ago is stale. Pragmatic, survives schema changes.

2. **Coerce-UTC fix:** `get_last_successful_started_at` initially returned raw Mongo datetime. Integration test hit `TypeError: can't subtract offset-naive and offset-aware` when comparing to `datetime.now(UTC)`. Fix: wrap all returns in `coerce_utc(...)` and document the contract. Lesson: any caller subtracting repo datetimes from `datetime.now(UTC)` must round-trip through `coerce_utc`.

3. **Audit script off-by-one:** Initial floor division (`window_hours // interval_hours`) under-counted for sub-daily intervals where window > interval (e.g. 6h window, 4h bars → expected=1 but actual=2). Code review M4 flagged it. Fix: `math.ceil`. Bug was cosmetic (gap == max(0, expected-actual) always clamped), but produced confusing rows. Fundamental rule: every bar whose open timestamp falls in [start, start+window) is a ceiling operation.

4. **Multi-instance safety:** VPS + local-dev both run `enqueue_missed_catchups` at boot. Safe because `add_one_off_job` uses `replace_existing=True` with stable `_catchup` suffix; second write overwrites first. APScheduler's distributed-coord pattern (race on `next_run_time`) ensures single execution. Documented in docstring.

## Root Cause Analysis

**_on_error logging:** CancelledError is a normal deploy signal, not a failure. Empty `error=""` masked it as "unknown." Root: exception object was lost in the original error handler before we could format the type name.

**Wrapper-path orphans:** Process killed mid-job leaves history doc stuck at `status="running"`. No cleanup hook runs; next restart doesn't see it as stale. Root: no TTL on orphaned docs, no explicit orphan detection on boot.

**Global grace window too loose:** 300s grace catches 99.9% of normal restarts. But sync_backfill (cron 03:00 UTC) with a deploy window 02:55–03:05 UTC drifts into the grace window 2 times/month on average. Root: single global lever for heterogeneous job types; some need tight grace (1m intrabar), others need loose (daily backfill).

**No catchup after deploy-induced miss:** Daily jobs that skip a cron because the scheduler was down don't enqueue retroactively. Root: APScheduler's misfire detection assumes the job will reschedule at next cron; we never manually enqueue missed windows.

## Lessons Learned

1. **Exception type matters for deploy signals.** CancelledError, asyncio.TimeoutError, etc. are normal during orchestrated restarts. Losing the exception type in the error handler obscures what's happening. Always format and log the exception type, not just the message.

2. **Distributed systems need explicit cleanup.** Orphaned running states don't self-correct. Add a boot-time "reconcile" sweep for any stale/orphaned resources. 600s staleness threshold is reasonable for a 300s global grace window.

3. **One global lever is too coarse.** Different job types have different fault-tolerance profiles. sync_1m retries hourly (tight grace OK). sync_backfill waits 24h for next cron (loose grace needed). Per-job grace is explicit and auditable; makes scheduler resilience policy visible.

4. **Audit tooling is not optional.** Without `audit_bar_gaps.py`, silent skips go undetected until traders notice missing data. CLI that answers "did we miss a bar window?" is table stakes for any sync orchestrator.

5. **Catchup jobs need namespace isolation.** Don't overload the original job_id for recovery. Use a suffix (`_catchup`) so original job_id stays the anchor for history queries. Two distinct namespaces, one logical story.

6. **DateTime coercion is a code contract.** Any caller that subtracts repo-returned datetimes from `datetime.now(UTC)` must coerce. Document it, make it a pattern, enforce via type hints if possible.

## Next Steps

1. **Monitor job_history post-deploy:** Watch for reconcile_orphan_running finds any orphans (should be 0 post-deploy). Check APScheduler job counts match expected (no ghost jobs). 48h observation window.

2. **Validate post-deploy on 03:00 UTC restart:** Requires a scheduled restart 02:58–02:59 UTC to skip the sync_backfill cron and confirm enqueue_missed_catchups fires. Impractical to schedule synthetically; trust tests + organic observation. Flag in runbook: "first daily schedule after this deploy will confirm catchup logic."

3. **Add orphan reconciliation to runbook:** If `/runs` shows stale "running" jobs, run `JobHistoryRepository.reconcile_orphan_running()` manually or trust next boot to clean them up.

4. **Monitor for silent bar skips:** Daily operator check: `scripts/audit_bar_gaps.py --dates $(date -d "yesterday" +%Y-%m-%d),$(date +%Y-%m-%d) --intervals 1m,5m,1h,4h,1d`. Exit 1 = escalate. Exit 0 = all clear.

---

**Commits:**
- `38f04eb`: Phase 01-05, tests (15/15 pass), docs, all components

**Effort vs plan:** 5h estimated, ~5h actual (single agent, no parallelization needed).

**Key metrics:** 0 critical/high code-review findings; 1 iteration (coerce_utc in integration test); 2 deferred validations (orphan reconciliation observed post-deploy, catchup logic validated on next natural restart).
