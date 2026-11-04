---
phase: 3
title: "Repair and backfill fold late 1m bars"
status: pending
priority: P1
effort: 4h
dependencies: [2]
---

# Phase 03: Repair and backfill fold late 1m bars

## Goal

Every 1m bar that `sync_repair` or `sync_backfill` writes is folded into 5m-1d in the same job run, and the REST repair stops rewriting cascaded intervals.

## Context

- Design and line references: `plans/reports/kongming-261103-1741-1d-cascade-and-small-fixes.md` item 1.
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py`: `sync_1m` cascades every tracked symbol with `lookback_minutes=100` inside its body; `sync_repair` runs `repair_integrity` for every interval in `SYNC_INTERVALS` (7 days back, `skip_filter=True`) and never cascades; `sync_backfill` is a lambda over `_rest_sync` and never cascades.
- `cascade_for_symbol` (`cascade_aggregator.py`) is idempotent: `upsert_bar` returns early when OHLCV is unchanged (`bar_repository.py:81-82`).
- `CASCADE_TFS` (`cascade_aggregator.py`) lists 5m, 15m, 1h, 4h, 1d.

## Task 03.1: E3 (decided)

E3 is decided in plan.md Owner decisions: the repair fetches only 1m and 1w, and the cascade rebuilds 5m-1d. Reason: prod rewrites 5000 REST 5m bars on gaps it then cannot fill, and Phase 17 measured REST 1d equal to cascaded 1d. Record `E3=yes` in the report. Do not ask again.

## Task 03.2: One cascade helper, three callers

**Target files:** `src/pocketquant/engine/market_data/app_services/sync_jobs.py`, tests next to `tests/app_test/unit/market_data/test_sync_jobs_tracked.py` (new file `tests/app_test/unit/market_data/test_sync_jobs_fold.py`).

**Steps:**
1. Write the tests first, patching `cascade_for_symbol` and `repair_integrity` / `_rest_sync` the way the existing `test_sync_jobs_*` files patch the container:
   - (a) `test_repair_folds_seven_days_for_every_symbol_even_after_one_fails`: two tracked symbols, `repair_integrity` raises for the first; `cascade_for_symbol` is awaited once per symbol with `lookback_minutes=10080`, and the job still raises its `1 of 2 symbols failed` error.
   - (b) `test_repair_fetches_only_the_intervals_the_cascade_cannot_build`: `repair_integrity` is awaited only with `Interval.MINUTE_1` and `Interval.WEEK_1`.
   - (c) `test_backfill_folds_after_the_rest_sync`: `cascade_for_symbol` is awaited after `_rest_sync`, once per symbol with `lookback_minutes=10080`.
   Confirm they fail.
2. Extract the per-symbol cascade loop of `sync_1m` into `async def _cascade_all(lookback_minutes: int) -> dict[Interval, int]` (gets `TrackedSymbolRepository`, `BarRepository`, `TradingCalendarFactory` from the container, keeps the per-symbol `try` and `sync_1m.cascade_failed` ERROR log, renamed to `cascade.symbol_failed` with a `lookback_minutes` field). `sync_1m` calls `_cascade_all(100)` and keeps its DEBUG summary.
3. Add `_REPAIR_DAYS = 7`. In `sync_repair`, loop over `[i for i in SYNC_INTERVALS if i not in CASCADE_TFS]`, pass `days_back=_REPAIR_DAYS` to `repair_integrity`, and call `await _cascade_all(_REPAIR_DAYS * 1440)` after the symbol loop and before `if failed: raise`.
4. Turn `sync_backfill`'s lambda into a body: `totals = await _rest_sync(...)`, then `await _cascade_all(_REPAIR_DAYS * 1440)`, then return `totals`. A REST failure still cascades (same rule and comment style as `sync_1m`).
5. Update the comment above `SYNC_INTERVALS`: REST backfill still fills 5m-1d history older than the stored 1m bars; repair fetches only 1m and 1w; the cascade rebuilds 5m-1d from 1m in `sync_1m`, `sync_repair` and `sync_backfill`.
6. Add one `#` line above `_cascade_all`'s 7-day call sites only if the reason is not obvious from the constant name: repair and backfill can write a 1m bar days back, and only a re-cascade folds it into the buckets above.

**Verify:** `uv run python -m pytest tests/app_test/unit/market_data/ tests/app_test/market_data/ tests/app_test/test_sync_jobs_phase.py tests/app_test/integration/test_sync_backfill_gap_fill.py -q` passes.

## Task 03.3: Measure the cost locally

**Steps:** with Docker up and a local Mongo that holds at least 7 days of 1m bars for one symbol (seed with `scripts/backfill/provider_bars.py` if needed, see `docs/deployment.md`), time one `_cascade_all(10080)` call for that symbol with a short script and record `cascade_7d_s=<seconds> symbols=<n>` in the report.

**Verify:** the report has one `cascade_7d_s=` line. Above 60 s for one symbol, STOP and ask the owner before shipping (R1).

## Close

CLOSE (plan.md Conventions). Commit `fix(market-data): fold late 1m bars into cascaded bars after repair and backfill`. Report `reports/phase-03-fold-late-1m-bars.md` with the Verify outputs, `E3=yes`, `cascade_7d_s=`, the commit id and the CI run id. Record R2 (partial oldest bucket for a symbol tracked under 7 days) as accepted.

## Risk and rollback

- R1 cost, R2 partial edge bucket, R4 a 5m-1d gap with no 1m behind it (plan.md Risks).
- Rollback: `git revert` the commit; the next `sync_repair` returns to the old behaviour. No data migration.

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
