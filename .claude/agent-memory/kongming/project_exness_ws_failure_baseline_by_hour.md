---
name: exness-ws-failure-baseline-by-hour
description: Prod exness_ws failure lines run ~120/day clustered 00-04Z and 12Z; the 13-19Z band sees ~2/day. Read before judging R1, the Phase 01 spike, or handover timing.
metadata:
  type: project
---

Prod `pocketquant-app` logged 121 `exness_ws.(connection_failed|reconnecting|circuit_breaker_open)` lines in the 24 h before the Phase 01 spike (2026-10-27T13:00Z to 2026-10-28T13:01Z): 60 connection_failed, 57 reconnecting, 4 circuit_breaker_open. By hour UTC: 00h 22, 02h 53, 03h 26, 04h 2, 12h 16, 17h 2. No `stale_detected`.

**Why:** the Phase 01 two-sessions spike (13:01-13:36Z, PASS) saw 0 prod WS failure lines, but the 13-19Z band has ~2/day at baseline, so that condition carried little power; the real PASS evidence was the p99 quote-age delta (B-A within +0.04 s) and the own-session gaps. Verified separately: 0 WS failure lines from 13:36Z to ~14:40Z after the spike. The clusters coincide with the plan's deploy blackouts (23:50-00:50, 02:50-04:50, 11:50-12:50) and the known sync_repair stalls at 00:00/12:00.

**How to apply:** when a handover (Phase 07-10) or a probe shows WS reconnects near 00-04Z or 12Z, compare against this baseline before blaming the second session (R1). Rolls scheduled inside the Conventions window avoid the clusters. Also confirmed 2026-10-28: 80 "Error notifying listener" lines/day, all `AttributeError: 'JobSubmissionEvent' object has no attribute 'scheduled_run_time'` (the Phase 02 Task 2.3 fix); see [[sync-repair-stall-and-skip-listener-bug]].
