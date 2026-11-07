---
name: phase04-daily-check-go-and-transient-rule
description: 2026-11-04 GO for the hourly 1d self-consistency check; Phase 05 must read cascade.daily_divergence as failure only when the same (symbol, day) repeats on consecutive hourly runs; exact-equality variant deferred
metadata:
  type: project
---

Phase 04 (plan 261103-1741) GO on 2026-11-04: `cascade.daily_divergence` compares stored 1d to `aggregate_bucket` over stored 1m with the 5m REST thresholds (0.01% price, 5% volume), relative to the aggregate.

**Why:** the hourly verify fires at :00:00 and overlaps sync_1m (:00:12), sync_repair (00/12Z) and sync_backfill (03Z, which writes REST 1d then folds), so a single-run warning can be a read between a 1m/REST write and its fold. Thresholds also hide a never-folded mid-day minute unless it moved the close.

**How to apply:** in Phase 05, count a warning only when the same (symbol, datetime) shows on two consecutive hourly runs. If integrity shows 1m repairs with no daily warning, propose switching the check to exact tuple equality (what upsert_bar uses) as a follow-up, not a Phase 04 change.
