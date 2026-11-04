# Phase 02 report: Symbol lookup race, cascade read limit, unused positions route

Date: 2026-11-04 (Asia/Bangkok). Run in Git Bash on the owner's Windows 11 host, branch `develop`.

## Outcome

All three fixes are committed, pushed to `develop`, and green in CI.

| Task | Commit |
|---|---|
| 02.1 Symbol lookup reads the cache once | `9c5f0cae fix(market-data): read the symbol lookup cache once` |
| 02.2 Cascade reads the whole bucket | `bb84c2a3 fix(market-data): read every 1m bar of a cascaded bucket` |
| 02.3 Delete the positions route | `4933e028 refactor(api): remove the unused subscription positions route` |

CI: run `41765510772`, `status=completed`, `conclusion=success`, `headSha=4933e028595c49d66b4c8d0764d49903462072bf`, which equals `git rev-parse HEAD`.

## Task 02.1

- `SymbolLookupHelper.get` now reads once with `_CACHE.get(key, _MISS)`. I checked the installed cachetools 7.1.4 source: `_TimedCache.get` wraps `Cache.get` (a membership test then a read) in `with self.__timer:`, so both reads see one frozen time and cannot disagree. A plain `in` then `[]` calls the timer twice.
- `binance_ws.error` in `run_forever` now logs with `exc_info=True`. The re-raise in `_invoke_callback` is kept (E4).
- New test `tests/core_test/infra/persistence/test_symbol_lookup_helper.py::test_an_entry_expiring_between_reads_never_raises`, parametrized for a found symbol and a cached miss (`None`). The fake timer returns 0, then 59, then 60.
- Red before the fix: `2 failed`, `KeyError: 'ETHUSDT:BINANCE'`.
- Verify: after the fix `2 passed`. With only the source file reverted to `HEAD` (copy and restore, not `git stash`, because other files were dirty): `2 failed`, `KeyError: 'ETHUSDT:BINANCE'`. After restore: `2 passed`.

## Task 02.2

- `cascade_for_symbol` no longer computes `expected_count` and passes no `limit`, so `BarRepository.find` uses its default of 5000. A 1d bucket holds at most 1440 1m bars.
- New test `test_a_day_with_more_minutes_than_the_calendar_keeps_its_first_bar` stores 1440 minutes of Monday 2026-06-08 for `XAUUSD:EXNESS` in `mock_bar_repo` and checks the 1d open and volume. Red before the fix: `assert 157.0 == 100.0` (the 57 earliest minutes were dropped).
- Deleted `test_a_halted_hour_bounds_the_query_by_the_calendar`, `test_the_same_hour_on_a_24x7_calendar_fetches_sixty`, `test_a_short_session_day_bounds_the_daily_read`, and the `limit` assert in `test_a_session_calendar_cascades_its_daily_bar_at_utc_midnight`. The `HALT_START` constant and its comment lost their only users, so they were deleted too.
- Verify: `uv run python -m pytest tests/app_test/market_data/ -q` printed `84 passed`. `git grep -n "expected_count" -- .../cascade_aggregator.py | wc -l` printed `0`.

## Task 02.3

- Deleted the `/{sub_id}/positions` route and `StrategyQueryService.get_positions`, the guarded-route entry in `test_admin_token_guard.py`, and the two `get_positions` tests. The section comment now names only `get_trades`. `_open_position` stays because `test_edit_refuses_an_open_position` and the snapshot test still use it.
- `PositionRepository.find_open_by_subscription` stays (used by `strategy_command_service.py`). No doc in `docs/`, `README.md` or `CLAUDE.md` named the route.
- Verify: the `src tests` grep printed `0`; the `web/src` grep printed `0`. The first pytest run printed `28 passed, 7 errors` because Docker Desktop was not running. After starting Docker Desktop (plan FULLSUITE convention) it printed `35 passed`.

## Close

- GATES: `Contracts: 6 kept, 0 broken.`; `code_metrics.py --ratchet` exit 0; `ruff check src tests scripts` printed `All checks passed!`.
- FULLSUITE: `4 failed, 1345 passed, 1 skipped, 63 warnings, 4 errors in 104.59s`; the count of other failures printed `0`.
- Line endings: my first edit script wrote CRLF into two LF files. I converted them back to LF before the commit and checked them with `git ls-files --eol`.

## Notes

- `ruff format --check src tests scripts` reports 16 files on both the tree before this phase and after it. `cascade_aggregator.py` is one of them because of a missing blank line that was there before this phase. Formatting is not a plan gate, so I left it alone.
- The `cascade_for_symbol` header comment still says "A partial bucket is logged". That was already stale before this phase and is outside this phase's scope.
- The Phase 01 journal asked for one FULLSUITE run before any code change, because the repo now has a `.env`. I did not run it before the change. The FULLSUITE run after the change met its pass condition, so the `.env` did not break the suite.
- The Phase 01 plan-file edits are committed together with this phase's plan files, as the Phase 01 journal asked.

## Advisory review (`--advice`)

kongming returned GO for Phase 03 and found no defect in the three commits. It reproduced the race against cachetools 7.1.4. It also confirmed that `aggregate_ohlcv` sorts ascending before it takes open and close, so the newest-first read without a limit cannot flip them.

- Nit, left as is on its advice: the comment at the top of the new test names the prod incident, which is history rather than a WHY.
- Top risk for Phase 03 (kongming's inference, not measured): the 7-day re-cascade lengthens `sync_repair`. Memory records that this job already blocks the event loop for 25-49 min at 00:00 and 12:00 UTC. If the stall goes past `sync_1m`'s 100-minute lookback, the minutes it missed are never folded, and Phase 04's check would warn on them. In Task 03.3, time `_cascade_all(10080)` across all tracked symbols, not just one. In Phase 05, read the `sync_1m` misfire logs around the first repair after deploy.

Result: PASS
