# Phase 08 report: backtest intervals, real sandbox wiring, backtest-path context

A backtest now runs on an ordered `intervals` list that `check_strategy_inputs` validates before the started doc is saved. Its sandbox engine reads the real stored bars through the real calendar and tracks the run's own positions. Each higher interval is read from Mongo once per run. On CI, the timing bound from D10 (`t_mtf_s <= 2 * t_stf_s`) missed on one of three test jobs, so the owner amended D10 (Task 08.3b): CI gates only the read count, and the ratio is recorded locally.

## Entry gate

`0`, `synced`, Phase 07 report ends `Result: PASS`, `check_strategy_inputs` count `1`, `doubles`, `docker-ok`.

## Commits

- `0aba1821` `feat(backtest): run over ordered intervals with stored context and live risk`.
- `8493fd39` `test(backtest): gate the context read count in CI and record the time ratio locally`.

## Test-first red outputs

- 08.1: `8 failed, 3 passed`. The command has no `intervals` field yet.
- 08.2: `2 failed, 9 passed`. The stub repository gives an empty `1h` context, and the SHORT fills and closes the long (`[BUY, SELL]`).
- 08.3: `context_cost find_1h=779 find_4h=419 t_mtf_s=34.74 t_stf_s=1.16`.

## Verify outputs

- 08.1: `84 passed`; the `config.interval` grep prints `0`.
- 08.2: `279 passed` (`tests/backtest_test tests/engine_test`); `11 passed` for the context file. The no-local-strategy grep, the src stub-class grep and the `build_backtest_sandbox()` grep all print `0`.
- 08.3: `12 passed`; the `context_cost find_1h=1 find_4h=1` grep prints `1`.

## Tests

- New in `test_backtest_single_run_direct_task.py`: `test_run_rejects_unsorted_intervals_before_saving`, `test_run_rejects_a_parameter_of_the_wrong_type_before_saving`, `test_a_run_stores_intervals_and_the_entry_interval`.
- Changed: `test_strategy_history_filters_by_composite_symbol` also asserts `row["intervals"] == ["1m"]`.
- Changed: `test_engine_failure_marks_failed_via_inspect_not_exception`. The command now rejects an unknown strategy before saving. The test therefore saves the started doc with a valid code and changes the payload's `strategy_code` before `execute_and_persist`.
- New in `test_higher_timeframe_context.py`: `test_backtest_contexts_equal_live_contexts_at_every_boundary` and `test_backtest_rejects_an_entry_against_its_open_position`. The live helper is shared as `_live_seen`, and the backtest runner as `_backtest`.
- New file `test_backtest_context_cost.py`: `test_a_multi_timeframe_backtest_reads_each_higher_interval_once`.
- `ScriptedStrategy` gained the `SCRIPT` class variable and the `script` instance list.
- 15 importer files now import `NoStoredBars` and `Continuous24x7CalendarFactory` from `tests.strategy_doubles`.
- Five `BacktestConfig(` sites now use `intervals=[...]`: `test_backtest_app_service_persistence.py` (two sites), `test_paper_broker_signal_bar.py`, `test_report_annualization_source.py` and `test_result_collector_mark_to_market.py`.
- Payload sites changed: `test_backtest_dispatch_contract_spec.py`, `test_app_standalone_runtime.py`, and the two payloads in `test_backtest_single_run_direct_task.py`.
- A sixth payload site, `tests/core_test/infra/brokers/test_paper_broker_spread.py`, was outside the plan's grep scope. FULLSUITE found it (`KeyError: 'intervals'`), and it now uses `"intervals": ["1m"]`.

## Deviations, each made on kongming's counsel after a failed Verify

All three were made to meet D10. With only the plan's preload, the result was `context_cost find_1h=1 find_4h=1 t_mtf_s=5.30 t_stf_s=1.25`. cProfile put 3.3 s in `closed_before` called from `_context_at`.

1. `_context_at` has a fast path. When the newest cached bar is closed at the instant, it returns a copy of the cached list; otherwise it applies the full `closed_before` filter. Cached bars are oldest first, so the two give the same output. Live and backtest always take the fast path. Warm-up replays earlier instants and takes the filter. `closed_before` is unchanged.
2. `_refresh_context` returns early when the cached window is complete and `window <= instant < window + step`, and makes no calendar call. Both `bar_start` implementations (`get_bar_start` and `exness_bar_start`) use buckets that are exactly one step long, so this decides the same thing as the old `cached[0] == window` check. The completeness check and the WARNING are unchanged.
3. The cost test times three interleaved pairs (single interval first) and asserts on the fastest run of each leg. It also recreates the bar indexes that the collection drop removes. The plan step timed one pair.

The equality test at every boundary and across the gap passes after each change. The code reviewer also ran a random simulation of the slice and the fast path (400 seeds, 5m to 1d steps, random gaps) and found 0 mismatches.

Standalone `context_cost` ratios after deviations 1 and 2 were 1.38 to 1.94 over nine runs. A FULLSUITE run then failed at a ratio of 2.03, which led to deviation 3. After deviation 3, local runs printed:

```
context_cost find_1h=1 find_4h=1 t_mtf_s=2.01 t_stf_s=1.22
context_cost find_1h=1 find_4h=1 t_mtf_s=2.75 t_stf_s=1.80
context_cost find_1h=1 find_4h=1 t_mtf_s=2.85 t_stf_s=1.77
```

## Review

The code-reviewer found no Critical or High issues.

Accepted and fixed:
- The preload limit is `max(0, int((end - start) / step)) + 1 + _WARMUP_BARS`. A reversed range would otherwise give `limit(0)`, which Mongo treats as no limit.
- Two comments now state the true invariants: buckets are exactly one step long, and cached bars are oldest first.
- The cost test recreates the bar indexes.

Recorded, not changed:
- M1: the preload keeps every higher bar of the run in the api process. For a year at `1m,5m` that is about 105k `Bar` objects. Concurrent backtests are not capped.
- L1: no test pins the invariant that buckets are exactly one step long.
- L5: no backtest-path test covers a session calendar, a missing higher bar, or the 500-bar cap.
- L6: the preload's `# type: ignore[misc]` stays.

## CLOSE

- GATES: `Contracts: 6 kept, 0 broken.`; ratchet exit 0 (no ceiling change); ruff `All checks passed!`.
- FULLSUITE: `4 failed, 1215 passed, 1 skipped, 55 warnings, 4 errors in 124.52s (0:02:04)`; unexpected count `0`.
- CI run `41332031144` on `0aba1821`: `completed failure`.
  - Jobs `web`, `tests (UTC)` and `tests (Asia/Ho_Chi_Minh)` passed.
  - Job `tests (America/Chicago)` failed: `context_cost find_1h=1 find_4h=1 t_mtf_s=1.36 t_stf_s=0.67`, `assert 1.3606054279999995 <= (2 * 0.6689978550000006)`.

## Open decision

The structural goal is met: each higher interval is read once, against 779 and 419 reads before. The CI runner reads Mongo faster than Docker Desktop on Windows, so the single-interval run is faster there. The extra cost of the multi-timeframe run is the same, 0.69 s for 43,200 bars, so the ratio rises to about 2.0 even though the code is the same. The owner has been asked to choose:

1. (recommended) Keep the `find == 1` asserts in CI. Skip the timing assert when `CI` is set, and record the local `context_cost` line in each phase report.
2. Option 1, and also return the cached context list without the copy.
3. An absolute per-bar bound.
4. Relax D10 to 2.5x.

The owner answered "1+2". Task 08.3b applies both; see "Amendment (Task 08.3b)" below.

## Amendment (Task 08.3b)

- The cost test keeps `finds.get("1h") == 1` and `finds.get("4h") == 1` unconditional, still prints the `context_cost` line, and asserts `t_mtf_s <= 2 * t_stf_s` only when `CI` is unset.
- `_context_at` returns the cached list itself on the fast path instead of a copy. The cache entry is replaced by assignment in `_refresh_context` and never changed in place.
- Verify: `12 passed, 2 warnings in 17.90s`; with `CI=true`, `1 passed, 2 warnings in 14.00s`; the `list(cached)` grep prints `0`.
- GATES: `Contracts: 6 kept, 0 broken.`; ratchet exit 0 (no ceiling change); ruff `All checks passed!`.
- FULLSUITE: `4 failed, 1215 passed, 1 skipped, 55 warnings, 4 errors in 118.73s (0:01:58)`; unexpected count `0`.

## Local timing (D10)

```
context_cost find_1h=1 find_4h=1 t_mtf_s=1.62 t_stf_s=1.01
context_cost find_1h=1 find_4h=1 t_mtf_s=1.71 t_stf_s=1.07
context_cost find_1h=1 find_4h=1 t_mtf_s=1.29 t_stf_s=1.06
```

Ratios: 1.60, 1.60 and 1.22, all within the 2x bound.

## CLOSE after the amendment

- CI run `41377788029` on `8493fd39`: `completed success`.
- No metric ceiling change.
- kongming gave go before the commit: the diff matches Task 08.3b, and no code in `src` or `tests` mutates a context list.

Result: PASS
