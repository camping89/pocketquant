---
title: Hourly daily bar self-consistency check
date: 2026-11-04
summary: "sync_verify_cascade now warns cascade.daily_divergence when a stored 1d differs from the aggregate of its stored 1m; one commit green in CI"
---

# Hourly daily bar self-consistency check

## What happened
This is Phase 04 of `plans/261103-1741-1d-cascade-fold-and-small-fixes`. Commit `c0abc0fb` is on `develop`, and CI run 41769640680 passed on it.

- `aggregate_bucket` was extracted from `cascade_for_symbol`, so the cascade and the new check aggregate a bucket the same way.
- The hourly `sync_verify_cascade` compares up to 4 closed days per symbol and logs `cascade.daily_divergence` with the day and the differing fields. It makes no provider call.
- The 5m branch used `continue` on an empty or failed check; it became an if/elif chain so the 1d check still runs for that symbol.

## Lessons
- A test that asserts "no warning" cannot be red before the feature exists. Only the positive test proves the check fires; the negative tests guard against false alarms.
- The module logger must be replaced with a fresh `structlog.get_logger` in tests, or `capture_logs` sees nothing once the cached logger has emitted.

## Next steps
Phase 05 deploys Phases 02-04. Warnings before the first post-deploy repair are old drift (R3). A `(symbol, datetime)` counts as a failure only when it repeats on two consecutive hourly runs after a repair, because the verify can run while `sync_1m` or a repair is writing.

> Historical work record — not durable authority. Prefer docs/specs/ADRs for current decisions.
