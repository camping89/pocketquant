# Phase 04 report: Hourly 1d self-consistency check

Date: 2026-11-04 (Asia/Bangkok). Run in Git Bash on the owner's Windows 11 host, branch `develop`.

## Outcome

`sync_verify_cascade` now compares each stored 1d bar of the last closed days (up to 4) with the aggregate of its stored 1m bars and logs `cascade.daily_divergence` at WARNING with `symbol`, `datetime` and the list of differing `fields`. The change is committed, pushed to `develop`, and green in CI.

Commit: `c0abc0fb feat(market-data): check stored daily bars against their minutes every hour`

CI: run `41769640680`, `status=completed`, `conclusion=success`, `headSha=c0abc0fb14c96d57768ef8e6edc9305a10c9f90a`, which equals `git rev-parse HEAD`.

## What changed

- `cascade_aggregator.aggregate_bucket(symbol, tf, boundary, bar_repo, calendar)` reads one bucket's 1m bars and returns the aggregated `Bar`, or `None` when the bucket has no 1m bars. `cascade_for_symbol` and the daily check both call it.
- In `sync_verify_cascade`, the 5m result handling became an if/elif chain instead of `continue`, so the 1d check also runs when the 5m check is empty or failed. The 5m events and their levels are unchanged.
- The 1d check skips the day in progress and any day missing its stored 1d or its 1m bars. A failure logs `sync_verify_cascade.symbol_failed` with `check="1d"` and the loop continues. No new job or schedule.

## Verify

- Task 04.1: `uv run python -m pytest tests/app_test/market_data/ -q` printed `84 passed, 1 warning`. The existing cascade tests pass unchanged.
- Task 04.2: the four new tests were written first. Before the implementation, `test_a_stored_day_that_differs_from_its_minutes_warns_with_the_day` failed with `assert 0 == 1`. The three "no warning" tests could not fail before the implementation, because no warning is the starting state. After: `uv run python -m pytest tests/app_test/unit/market_data/test_sync_verify_cascade.py -q` printed `15 passed, 1 warning`.

## Gates

- GATES: `uv run lint-imports` printed `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exited 0; `uv run ruff check src tests scripts` printed `All checks passed!`.
- FULLSUITE: `4 failed, 1352 passed, 1 skipped, 63 warnings, 4 errors in 96.36s`; the count of other failures printed `0`.

## Advisory review (`--advice`)

kongming returned GO with no must-fix item. It verified that the threshold is relative to the 1m aggregate, that Exness daily buckets start at UTC midnight on both sides, that a REST 1d written by `sync_backfill` is overwritten by the fold in the same job, that the 5m events are unchanged, and that the check logs at most 4 warnings per symbol per hour. I left its optional nits: the `if summary is None: pass` style, and no `exc_info` on `symbol_failed`, which matches the existing 5m line.

Limits:

- The shared price threshold (0.01%) and volume threshold (5%) can hide a missed mid-day minute that did not move the close. Exact equality could be considered later.
- The same `aggregate_ohlcv` produces both sides, so a bug inside it is invisible here; the 5m REST check covers it.

Risk for Phase 05 (kongming): the verify runs at :00:00 while `sync_1m`, `sync_repair` (00Z/12Z) and `sync_backfill` (03Z) may be mid-write, so a single warning can be transient. Treat a `(symbol, datetime)` as a failure only when it repeats on two consecutive hourly runs after the first post-deploy repair (R3).

Result: PASS
