---
name: d16-prewindow-vendor-drift-and-log-loss-on-deploy
description: 2026-11-07 open-questions review after the 1d cascade fold release — Exness 1d volume for BTCUSD 2026-10-24 moved between reads (113120/113100/113120) on a pre-window day; prod container logs vanish on every redeploy so integrity warnings must be reproduced via check_integrity; owner keeps journals local and tracks agent memory
metadata:
  type: project
---

Findings from the 2026-11-07 read-only review (report `plans/reports/kongming-261107-1227-open-questions-and-prod-state.md`).

- D16 (1d vs vendor) pre-window row: stored BTCUSD:EXNESS 1d 2026-10-24 has volume 113120 (written from Exness REST on 11-01), stored 1m sum is 113130, Exness returned 113100 on 11-04 and 113120 again on 11-07. OHLC matched exactly every time. Advice given: for days older than the 7-day fold window the D16 pass rule should be self-consistency (stored 1d == dry-run 1m aggregate), vendor equality only inside the window; re-run D16 once on/after 2026-11-11 then retire it. Owner decision pending. 2026-11-08: the D14 window is the latest 14 days, so the 10-24 row leaves the comparison by 11-11 on its own; the amendment only guards future revisions on days 8-14 days old. `fc173b5f` (develop, unreleased) stores integrity issues on the run doc with detail status `issues_found`; `job-runs-table.tsx` counts every non-`completed` detail as "failed" (pre-existing, also hits `skipped`). Counsel: record F1/F2 follow-ups in plan 261103-1741, not the closed MTF plan.
- Prod log loss: the log driver is json-file (10m x 3) and `deploy/vps/10-deploy.sh` recreates api/worker/trader, so every log line before the newest container start is gone after a redeploy. `sync_integrity` writes no `job_history.details` (it only logs `integrity.issues_found`), so R4-style evidence must be reproduced by calling `check_integrity` read-only through PRODPY. Four redeploys happened 11-06 14:52Z to 11-07 05:16Z (containers -14 to -18).
- Owner decision 2026-11-07 (`e49c0565`): `plans/journals/` is gitignored, `**/.claude/agent-memory/` is no longer ignored and the root agent memory is tracked. Reports under `plans/reports/` are conventionally committed (59 tracked); governance has no commit rule for `plans/`.
- The 11-04 manual job runs (06:04:53Z, 06:07:56Z, 06:12:13Z) are visible in `job_history` as off-schedule rows; `job_history` records no actor, so "who asked" is never decidable from prod.

**Why:** These are prod and vendor facts that code cannot show, and they decide how to read future D16 or R4 evidence.

**How to apply:** When asked for log-based evidence older than the newest container, say it is gone and reproduce via the job's read-only function instead. When a D16 diff is on a day older than 7 days with exact OHLC and a volume delta under about 1e-3, treat it as vendor drift unless the stored 1d also differs from its 1m aggregate. See also [[exness-1d-rest-equals-1m-aggregate]] and [[phase17-d14-window-source-rule-contradiction]].
