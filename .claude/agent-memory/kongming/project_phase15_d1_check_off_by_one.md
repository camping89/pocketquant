---
name: phase15-d1-check-off-by-one
description: Phase 15 (STF-to-MTF plan) entry gate 4 and Task 15.1 disagree by one day; days=0 on 2026-11-02 was window arithmetic, not a cascade failure; advised ASK with Recommended: no and resume after 2026-11-03T00:45Z
metadata:
  type: project
---

Phase 15 of `plans/261101-0843-stf-to-mtf-foundation` has an off-by-one between entry gate line 4 and Task 15.1: gate 4 passes once `(D1 + 1d)` midnight has passed, but the Task 15.1 script counts 1d bars in `[(D1+1d) midnight, today midnight)`, which is empty until `(D1 + 2d)` midnight. With `d1_deployed_at=2026-11-01T14:50:40Z` the first passing run is after 2026-11-03T00:00Z.

Evidence seen 2026-11-02T06:23Z (read-only prod): the 2026-11-01 1d bars for BTCUSD/EURUSD/XAUUSD:EXNESS are `source=cascade`, finalised 00:00:21-23Z on 11-02, `repair_1d=0`. The 11-01 day is a Sunday: EURUSD/XAUUSD bars cover only ~22:10/23:02-24:00Z, so the first full weekday close (with the 21:00Z rollover) is the 11-02 bar.

**Why:** the plan deliberately splits D-1 and D-2 so the release rests on one closed day of cascade evidence; the planner anticipated `days=0` and prescribed `[ASK] Recommended: no`.

**How to apply:** if Phase 15 resumes and days=0 recurs, do not treat it as a cascade bug; check the window arithmetic first. If the owner said "no" on 11-02, Phase 15 resumes `--from 15 after 2026-11-03T00:45Z` (00:01Z is the minimum; 00:45Z clears the midnight repair window before a deploy restarts the worker, see [[sync-repair-stall-and-skip-listener-bug]]). The gate-4/script mismatch is a plan defect worth fixing by the planner (`timedelta(days=2)` in gate 4), not by the worker.
