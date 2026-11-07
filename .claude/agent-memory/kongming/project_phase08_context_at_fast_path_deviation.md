---
name: phase08-context-at-fast-path-deviation
description: Plan 261101-0843 Phase 08 Task 08.3 - advised a fast path in StrategyAppService._context_at (same output) despite the plan sentence "stay unchanged"; D10 bound wins; closed_before text untouched
metadata:
  type: project
---

2026-11-02: Task 08.3 preload alone left `t_mtf_s=5.30` vs `t_stf_s=1.25` (bound 2x). The cost was `_context_at` re-filtering up to 500 cached higher bars on every one of 43,200 entry bars, not Mongo. Advised: in `_context_at`, when `closed_before(cached[-1:], step, instant)` is non-empty return `list(cached)`, else the full `closed_before` (warm-up replays earlier instants, so the filter must stay). `closed_before` body untouched.

**Why:** owner decision D10 (keep the 2x bound) outranks the plan step sentence "`_context_at` and `closed_before` stay unchanged"; the fast path has identical output because cached lists are ascending `closed_before` output (invariant already used by the completeness check in `_refresh_context`). Recorded as a deviation in the phase report, not an escalation.

**How to apply:** if a later audit flags `_context_at` as a look-ahead change, point to the equality tests in `tests/backtest_test/test_higher_timeframe_context.py` and this reasoning. Timing test order was advised STF-first to keep cold-cache cost out of the MTF leg; if CI flakes, re-measure once rather than loosen the bound.
