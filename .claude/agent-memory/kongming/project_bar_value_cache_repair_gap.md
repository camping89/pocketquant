---
name: bar-value-cache-blocks-repair
description: CLOSED 2026-11-05 — _BAR_VALUE_CACHE no longer exists in src; upsert_bar decides writes by a find_one diff. Do not cite the old "cache blocks repair of deleted bars" finding.
metadata:
  type: project
---

Closed. `git grep _BAR_VALUE_CACHE -- src` returns nothing on origin/develop as of 2026-11-05. `BarRepository.upsert_bar` reads the existing doc with `find_one` and skips the write only when OHLCV is equal, so a bar deleted from Mongo is recreated by the next repair or sync.

**Why:** the 2026-10-11 finding (process-local cache made `sync_repair` skip a deleted bar) was fixed when the cache was removed (plan 261028-0652 Phase 05 Task 5.6).

**How to apply:** nothing to act on; if a new per-process value cache is ever proposed for `upsert_bar`, raise the deleted-bar case again.
