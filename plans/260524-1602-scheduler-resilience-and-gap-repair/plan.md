---
title: "Scheduler resilience + sync gap repair"
description: "Bundle scheduler error-logging fidelity, orphan-running reconciliation, per-job misfire grace, startup catch-up for missed daily/12h crons, bar-gap audit script, ops runbook update. Single PR."
status: completed
priority: P2
effort: "1d"
branch: "develop"
tags: [scheduling, observability, market-data, ops]
blockedBy: []
blocks: []
created: "2026-05-24T09:17:22.730Z"
createdBy: "ck:plan"
source: skill
brainstorm: plans/reports/brainstorm-260524-1602-scheduler-resilience-and-gap-repair.md
predecessor: "plans/reports/brainstorm-260524-1504-sync-jobs-container-race-fix.md (race fix already shipped: 9a8dcf9 → 45e2d7f)"
---

# Scheduler resilience + sync gap repair

## Overview

Carry-forward work from the sync_jobs container-race fix. Three related concerns bundled into one PR:

1. **Logging fidelity** — `_on_error` currently writes empty `error=""` when APScheduler dispatches `CancelledError` during deploy. Cosmetic but masks deploy-cancellation as "unknown failure".
2. **Orphan-running reconcile** — wrapper-path docs stuck at `status="running"` when the job is cancelled mid-flight. Pollutes `/runs` dashboard.
3. **Per-job misfire grace + startup catch-up** — global 300s grace silently drops 3 daily jobs/month (`sync_backfill`, `sync_integrity`, `sync_repair`) when restart spans the window. Daily jobs need 3600s + a startup catch-up enqueue for any gap > expected interval.
4. **Bar-gap audit script + ops runbook** — verify whether any 1m/cascade gaps persist around historical missed-backfill days (likely none due to 100-min cascade lookback, but worth confirming).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Scheduler & repository foundations](./phase-01-scheduler-repository-foundations.md) | Complete |
| 2 | [Orphan-running reconcile lifespan integration](./phase-02-orphan-running-reconcile-lifespan-integration.md) | Complete |
| 3 | [Per-job grace + startup catch-up](./phase-03-per-job-grace-startup-catch-up.md) | Complete |
| 4 | [Audit script + ops runbook](./phase-04-audit-script-ops-runbook.md) | Complete |
| 5 | [Unit tests](./phase-05-unit-tests.md) | Complete |

## Phase Dependencies

- P1 = foundation. P2, P3, P5 depend on P1.
- P2 depends on P1's `reconcile_orphan_running` repo method.
- P3 depends on P1's `add_cron_job` grace kwarg + `get_last_successful_started_at` repo method.
- P4 stands alone (script + docs).
- P5 covers all of P1-P3 logic.

## Dependencies

<!-- No cross-plan dependencies. Scheduler/sync_jobs surface is not currently being modified by any other open plan. -->

## Validation Plan (post-merge)

1. Deploy.
2. Force restart at `02:58 UTC` to skip the 03:00 `sync_backfill`.
3. Wait 10 min after boot.
4. Query `job_history`:
   - APScheduler-side: `apscheduler_jobs` shows a `sync_backfill_catchup` job (briefly, until it runs).
   - History-side: a `sync_backfill` doc with `started_at` near boot time and `status=completed` (catchup writes under the ORIGINAL job_id; see `enqueue_missed_catchups` docstring).
5. Run `audit_bar_gaps.py --dates today` → expect parity.

## Success Metrics (30-day window post-deploy)

- Zero `job_history` docs with `error=""`.
- Zero `job_history` docs stuck at `status="running"` >11 min.
- Each restart day: each daily job has completed-OR-catchup-completed record (NOT a bare `missed` event).

## Completion Notes

Plan completed 2026-05-24. All 5 phases implemented, tested, reviewed. 15/15 unit tests passing. Post-review changes: `math.ceil` in audit script for sub-daily bar expectations. Ready for deploy.
