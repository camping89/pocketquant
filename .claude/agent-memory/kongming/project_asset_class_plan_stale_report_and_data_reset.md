---
name: asset-class-plan-stale-report-and-data-reset
description: Asset-class futures plan (260921-1436): completion-report.md is stale vs plan.md Session 11; partial_aggregate removed a9233245; prod futures data wiped 2026-10-12 and re-seeded as :TRADINGVIEW 2026-10-13
metadata:
  type: project
---

The asset-class index-futures plan's `completion-report.md` (dated 2026-09-24) predates
`plan.md` Session 11 of the same day. Session 11 records a user decision that
`cascade.partial_aggregate` was removed outright (`a9233245`), so metric 4's
partial_aggregate clause is retired. Prod data for `ES1!/NQ1!:CME_MINI`, `YM1!:CBOT_MINI`
was fully deleted on 2026-10-12 and the symbols re-seeded as `*:TRADINGVIEW` on
2026-10-13, after the `session_date` stamping fix (`f101f4ee`), so the "4999 unstamped
1d bars" of metric 5 no longer exist. Counsel on 2026-10-22 (report
`plans/reports/archive/kongming-261022-1145-asset-class-open-items.md`): measure #10 from
`job_history` (30-day TTL, survives deploys) and #11 from the app log (cleared on every
deploy; 24 hourly runs need 24 h without a deploy), drop the 2026-11-30 week-long watch,
defer G2 (#13), then archive the plan.

**Why:** callers keep quoting the stale report's "Fail" rows; the real state is in
plan.md's later sessions and in the Exness lean-sync reports.
**How to apply:** for any question about this plan, read `plan.md` Sessions 11+ and
`plans/261009-0858-exness-venue-lean-sync-refactor/reports/symbol-cascade-delete-261012.md`
before trusting `completion-report.md`. Verify the archive location (may have moved to
`plans/archive/`).
