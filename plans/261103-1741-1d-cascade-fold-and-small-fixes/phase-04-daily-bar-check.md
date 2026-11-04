---
phase: 4
title: "Hourly 1d self-consistency check"
status: pending
priority: P2
effort: 3h
dependencies: [2, 3]
---

# Phase 04: Hourly 1d self-consistency check

## Goal

Prod notices a stored 1d bar that no longer equals the aggregate of its stored 1m bars, and the log names the day.

## Context

- Design: `plans/reports/kongming-261103-1741-1d-cascade-and-small-fixes.md` item 2. Self-consistency (stored 1d vs aggregate of stored 1m), not REST-vs-stored: it catches a missed fold, a REST overwrite and a truncated read, makes no provider call, and has no newest-bucket race. The hourly 5m REST check already ties stored 1m to the venue.
- `sync_verify_cascade` and `_verify_one_symbol` in `src/pocketquant/engine/market_data/app_services/sync_jobs.py`; `compare_bar_fields`, `DIVERGENCE_ALERT_FRACTION`, `PRICE_THRESHOLD_PCT`, `VOLUME_THRESHOLD_PCT` are already imported there.
- `cascade_for_symbol` builds each bucket inline (read 1m, `aggregate_ohlcv`, build `Bar`); after Phase 02 the read has no limit.
- Existing tests: `tests/app_test/unit/market_data/test_sync_verify_cascade.py`.

## Task 04.1: One bucket builder, two callers

**Target files:** `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`, `tests/app_test/market_data/test_cascade_aggregator.py`.

**Steps:**
1. Extract the per-bucket read and aggregate from `cascade_for_symbol` into `async def aggregate_bucket(symbol, tf, boundary, bar_repo, calendar) -> Bar | None` (returns `None` when the bucket has no 1m bars). `cascade_for_symbol` calls it and keeps its upsert and logging.
2. No behaviour change: the existing cascade tests pass unchanged.

**Verify:** `uv run python -m pytest tests/app_test/market_data/ -q` passes.

## Task 04.2: The daily check

**Target files:** `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, `tests/app_test/unit/market_data/test_sync_verify_cascade.py`.

**Steps:**
1. Write the tests first with a fake bar repo and a 24/7 calendar:
   - `test_a_stored_day_that_differs_from_its_minutes_warns_with_the_day`: three closed days, the middle stored 1d has a different close; exactly one `cascade.daily_divergence` WARNING naming that day's `datetime`.
   - `test_equal_days_log_no_warning`.
   - `test_the_day_in_progress_is_never_compared`: today's stored 1d differs; no warning.
   - `test_a_day_missing_on_either_side_is_skipped`.
   Confirm they fail.
2. In `sync_verify_cascade`'s per-symbol loop, after the 5m check, add the 1d check: get the symbol's calendar from `TradingCalendarFactory`; for each `boundary` in `compute_boundaries(Interval.DAY_1, now - 4 days, now, calendar)` with `boundary + 1 day <= now`, read the stored 1d at `boundary`, call `aggregate_bucket`, skip when either is `None`, and when `compare_bar_fields` reports any field, log `cascade.daily_divergence` at WARNING with `symbol`, `datetime` and the fields. A failure of this check for one symbol logs `sync_verify_cascade.symbol_failed` like the 5m check and continues.
3. Keep it inside `sync_verify_cascade` (no new job, no new schedule). Bounded log: at most 4 lines per symbol per hour, only when values differ.

**Verify:** `uv run python -m pytest tests/app_test/unit/market_data/test_sync_verify_cascade.py -q` passes.

## Close

CLOSE (plan.md Conventions). Commit `feat(market-data): check stored daily bars against their minutes every hour`. Report `reports/phase-04-daily-bar-check.md` with the Verify outputs, the commit id and the CI run id.

## Risk and rollback

- R3 (plan.md): warnings before the first post-deploy repair are real drift the old code left; Phase 05 reads them.
- The same `aggregate_ohlcv` builds both sides, so a bug inside it is invisible to this check; the 5m REST check covers that.
- Rollback: `git revert` the commit.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same failure evidence to the user. Never continue by self-reasoning.
