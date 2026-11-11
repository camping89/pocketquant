---
name: ak-plan-reindex-dry-run-default
description: ak 2.19 `ak plan reindex` is a dry run without --apply; `ak plan list` is files-first so an unindexed plan still shows (bare folder id), and `ak plan update` then fails "planstore: plan not found"
metadata:
  type: project
---

`ak plan reindex` (ak 2.19.0) only reports "recognized" folders unless `--apply` is passed. `ak plan list --json` reads plan files first, so a plan missing from the SQLite store still appears, with id = folder basename (e.g. `261109-1349-1m-strategy-evidence`) instead of the indexed `pocketquant/<yymmdd-hhmm>` form. `ak plan update` reads the store only, so it fails with `planstore: plan not found`.

**Why:** 2026-11-10, plan 261109-1349 Phase 07 Task 07.2 hit this; the phase steps said `ak plan reindex` without `--apply` (Task 07.3 has the same gap).

**How to apply:** when reviewing or advising on plan phases that change status or archive through `ak`, require `ak plan reindex --apply`, and treat a bare-basename id in `ak plan list` as "not indexed".
