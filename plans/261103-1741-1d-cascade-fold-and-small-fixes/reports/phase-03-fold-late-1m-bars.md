# Phase 03 report: Repair and backfill fold late 1m bars

Date: 2026-11-04 (Asia/Bangkok). Run in Git Bash on the owner's Windows 11 host, branch `develop`.

## Outcome

`sync_repair` and `sync_backfill` now re-cascade 7 days of 1m bars for every tracked symbol, and the REST repair touches only 1m and 1w. The change is committed, pushed to `develop`, and green in CI.

Commit: `0b5a0608 fix(market-data): fold late 1m bars into cascaded bars after repair and backfill`

CI: run `41768197210`, `status=completed`, `conclusion=success`, `headSha=0b5a060894778d90b8fa3a84ed138f35d3d7512e`, which equals `git rev-parse HEAD`.

## Task 03.1

E3=yes

## Task 03.2

- New `_cascade_all(lookback_minutes)` in `sync_jobs.py` holds the per-symbol cascade loop. It has three callers: `sync_1m` (100 minutes), `sync_repair` and `sync_backfill` (both `_REPAIR_DAYS * 1440`). The per-symbol ERROR is now `cascade.symbol_failed` with a `lookback_minutes` field.
- `sync_repair` loops over `SYNC_INTERVALS` minus `CASCADE_TFS` (1m and 1w), passes `days_back=_REPAIR_DAYS`, and cascades after the symbol loop and before `if failed: raise`.
- `sync_backfill` has a body like `sync_1m`'s: the REST sync, then the cascade even when the REST sync failed, then the re-raise.
- The comment above `SYNC_INTERVALS` now says that repair fetches only 1m and 1w and that the cascade rebuilds 5m-1d in all three jobs. The WHY for the 7-day window sits on `_REPAIR_DAYS`.
- New tests in `tests/app_test/unit/market_data/test_sync_jobs_fold.py`: (a) `test_repair_folds_seven_days_for_every_symbol_even_after_one_fails`, (b) `test_repair_fetches_only_the_intervals_the_cascade_cannot_build`, (c) `test_backfill_folds_after_the_rest_sync`. Red before the change: `3 failed`.
- Existing tests: the repair fakes in `test_sync_jobs_tracked.py` take the new `days_back` keyword, and `_wire` patches `cascade_for_symbol` with an `AsyncMock` by default so repair and backfill tests do not run the real cascade against a `MagicMock` repository. `test_sync_source_labels.py::test_sync_backfill_dispatches_with_rest_backfill_source` patches the cascade the same way.
- Verify: `uv run python -m pytest tests/app_test/unit/market_data/ tests/app_test/market_data/ tests/app_test/test_sync_jobs_phase.py tests/app_test/integration/test_sync_backfill_gap_fill.py -q` printed `129 passed, 1 skipped, 2 warnings in 9.76s`. The first run printed 4 errors because Docker Desktop was not running; after starting it, the same command passed.

## Task 03.3

Local Mongo (all-local profile) was empty, so I seeded it with `scripts/backfill/provider_bars.py --interval 1m --days 8` for `BTCUSDT:BINANCE` and then `ETHUSDT:BINANCE` (11520 bars each). A script in `.cache/` timed `_cascade_all(10080)` with a stub tracked-symbol list.

cascade_7d_s=12.70 symbols=1

- One symbol, cold (every bucket written): 12.70 s. Same symbol, unchanged bars: 8.28 s. Buckets per run: 5m 2017, 15m 673, 1h 169, 4h 43, 1d 8.
- Two symbols, with ETHUSDT cold: 21.84 s. Two symbols, unchanged bars: 17.06 s. The cost grows linearly at about 8.5 s per symbol.
- An event-loop probe (a 100 ms sleep loop run beside the cascade) measured a maximum lag of 0.020 s. The cascade does not block the loop, so it cannot by itself push `sync_1m` past its lookback.
- Projection (inference, unmeasured): about 50-80 s per run for six symbols on prod. Phase 05 records the real `sync_repair` and `sync_backfill` durations (R1).

## Gates

- GATES: `uv run lint-imports` printed `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exited 0; `uv run ruff check src tests scripts` printed `All checks passed!`.
- FULLSUITE: `4 failed, 1348 passed, 1 skipped, 63 warnings, 4 errors in 151.42s`; the count of other failures printed `0`.

## Accepted risks

- R2 is accepted: for a symbol tracked under 7 days, the oldest 4h/1d bucket that 1m only partly covers is rebuilt from partial 1m and replaces the REST backfill bar. It is one bucket per interval per symbol and leaves the window after 7 days.
- Window edge (from kongming, accepted): each symbol's repair window starts at its own `now - 7d`, while the cascade window starts at `now - 7d` taken after the whole symbol loop. A 1m bar repaired in the first minute or two of the 7-day edge can fall before the cascade's first 5m or 15m boundary and miss its fold. 1h-1d buckets still include it because `compute_boundaries` floors the start to the bucket. If the Phase 05 dry-run comparison shows a 5m or 15m mismatch exactly at the window edge, this is the known cause.

## Advisory review (`--advice`)

kongming returned GO and found no correctness bug or rule violation. It confirmed that a resumed run with every symbol done still cascades, that `_cascade_all` catches only `Exception` so a cancellation ends the run as interrupted, and that the duplicated try/cascade/raise shape in `sync_backfill` is what the phase step asked for. I applied its wording nit on the `_REPAIR_DAYS` comment and left its optional move of the "cascade runs even when a REST fetch failed" comment.

Risks it named for later phases:

- Phase 04: keep the empty-bucket and `None` skips inside the extracted `aggregate_bucket` so `cascade_for_symbol` behaviour stays the same.
- Phase 05: `sync_backfill` now carries a 7-day cascade after its REST fetch and was never timed on prod; read its duration as well as `sync_repair`'s. Record the release time and the first repair's finish time in UTC with seconds, so the R3 split of 1d warnings is unambiguous. Strip ANSI colours before grepping `interval=5m` in repair logs.

Result: PASS
