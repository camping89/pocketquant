---
name: phase17-d14-window-source-rule-contradiction
description: 2026-11-02 Task 17.2 failed (mismatches=35) because D14's 14-day window reaches 13 pre-deploy REST 1d days while the pass rule still demands source=cascade; bars.source is "last writer that changed values", not ownership
metadata:
  type: project
---

Phase 17 Task 17.2 (plan 261101-0843) failed on 2026-11-02T17:49Z with `mismatches=35
repair_1d=0`: every diff row was a pre-deploy day (2026-10-19..10-31, `source=rest_repair`);
all three 2026-11-01 rows were `equal source=cascade`. The 1d cascade for Exness shipped at
`d1_deployed_at=2026-11-01T14:50:40Z` (Phase 03), so only one closed day was ever cascaded
live. The D14 amendment ("latest 14 stored days, pass rule unchanged") came from my advice
`plans/reports/advise-261103-0025-finish-mtf-plan-now.md`; the contradiction was my error.

Two code facts decide this class of question:
- `upsert_bar` returns before any write when OHLCV are equal (`bar_repository.py:81-82`), so
  `source` names the last writer that CHANGED values, never the owner. Phase 16's whole-history
  `cascade_for_symbol("XAUUSD:EXNESS")` (2026-11-02 09:14Z) left those days `rest_repair`,
  which is evidence the cascade values equalled REST, not that it skipped them.
- `sync_repair` on any 1d gap in the last 7 days re-upserts 5000 REST 1d bars with
  `source=rest_repair` (`integrity_jobs.py:145-155`); with `sync_backfill` 03:00Z that is three
  REST writers that win whenever values differ. No job compares 1d to the vendor.

**Why:** A pass rule keyed on `source` cannot be satisfied on days the cascade never changed;
a dry-run cascade (stored 1m -> `aggregate_ohlcv` with the live `find` limit) is the
read-only way to test the arithmetic over any window without waiting.

**How to apply:** Proposed D16 on 2026-11-03: values equal on all 14 days + dry-run cascade
equal + `source=cascade` only from the deploy day on. Never write a vendor-comparison rule
that needs `source=cascade` on days before the cascade's first write. Related:
[[exness-1d-rest-equals-1m-aggregate]], [[exness-venue-no-tick-gaps]].
