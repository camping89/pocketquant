---
name: exness-c3-races-sync-1m
description: E2 paper-check C3 run within ~15 s after a minute boundary reports the just-closed 1m bar missing because check_integrity expects it while sync_1m (cron second=2, p95 ~12.5 s) is still writing; row 1 (2026-10-20) was ruled PASS-with-note on a read-only re-run
metadata:
  type: project
---

C3 (phase-08 T8.7 of plan 261009-0858) races `sync_1m` by construction: `check_integrity` expects every bar with start `< bar_start(now)` and `sync_1m` is the sole 1m writer, firing at second 2 of each minute. Row 1 at 22:34:02Z showed XAUUSD 1m `VENUE_HAS 22:33:00`; a read-only re-run 42 s later passed. Kongming ruled it PASS with a note (2026-10-21), with no repair run.

**Why:** The pass rule's repair-then-recheck step exists to give a venue-fillable gap one chance to fill; `sync_1m` filled this one by itself. A read-only re-run substitutes for repair only for gaps ending within ~2 min of the check; older fillable gaps still need the repair step.

**How to apply:** For rows 2-4 advise starting C3 at UTC second >= 20 and, on a `VENUE_HAS` range ending within 2 min of the check, one 60 s re-check before repair. This is a timing note, not a pass-rule change, so no user [ASK]. Replacing the repair step would be a pass-rule change and needs an [ASK]. Phase 12's `unexpected_count` call has the same exposure but is record-only.
