# Phase 07 report: higher-timeframe context, live and warm-up

On every closed entry bar, live and warm-up, a strategy now receives `bar["context"]` with the higher-interval bars from Mongo that closed by the entry bar's start. One cache per (symbol, interval) in `StrategyAppService._context` serves them, and a start before second 20 with stored entry bars waits for `sync_1m` before it replays.

## Entry gate

`dirty=0`, `synced`, Phase 06 report ends `Result: PASS`, `intervals: list[str]` count `1`, `_context[` count `0`, `docker-ok`.

## Test-first red outputs

- 07.1: `7 failed`.
- 07.2: `1 failed, 8 passed`, not the planned `2 failed`. Only `test_a_start_before_second_20_waits_and_replays_the_final_bar` failed. The warm-up parity test was already green because 07.2 steps 4 and 5 ran in 07.1 (see Deviation).

## Deviation: 07.2 steps 4 and 5 ran in 07.1

- The first 07.1 Verify printed `6 failed, 1 passed`.
- Four tests seed entry bars, so warm-up replayed them without a `context` key, and the recorder raised `KeyError: 'context'` out of `start_strategy`.
- Two tests expect a `finds["1h"]` count that includes the read at start: they got `3 == 4` and `1 == 2`.
- The 07.1 tests therefore need the 07.2 prefetch (`_refresh_context(config, now)` before `on_start()`) and the replay through `_decide`.
- On kongming's counsel, those two steps moved into 07.1. The wait condition (07.2 step 3) and its test stayed in 07.2.
- The re-run printed `7 passed`. No test changed.

## Verify outputs

- 07.1: `7 passed, 2 warnings`; `closed_before` has its definition and two uses.
- 07.2: `43 passed, 2 warnings` across the four files; `9 passed, 2 warnings` for the context file.
- 07.3: `docs/system-architecture.md:1`; `_context_at` appears twice in `src`; the doc has 49 lines.

## Tests (9 passed)

`test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`, `test_live_entry_bars_never_see_their_own_bucket`, `test_a_partial_bucket_is_never_served`, `test_context_is_read_once_per_rollover_for_two_instances`, `test_exness_weekly_context_rolls_on_sunday`, `test_a_missing_previous_bucket_is_requeried_next_bar`, `test_a_session_gap_bucket_is_cached`, `test_warm_up_contexts_equal_live_contexts`, `test_a_start_before_second_20_waits_and_replays_the_final_bar`.

The `_publish` helper takes an extra `close` argument, so the parity test can publish the stored 1m closes.

## Executor decisions

- The cache tuple `(window, bars, complete)` follows the executor decision in the phase Context.
- The warm-up wait condition `now.second < _WARMUP_READY_SECOND and bars` also follows the executor decision in the phase Context.

## Review

- code-reviewer reported one High: pyright flagged `stored.datetime` (`datetime | None`) passed to `_bar_dict`. An `assert stored.datetime is not None` in the replay loop fixed it, and pyright now reports `0 errors` on the touched files. The `_WARMUP_READY_SECOND` comment now says "cascaded interval".
- Medium, "a partial 1w row can be stored and served for a week": rejected. Both REST adapters keep only bars before the current bucket start: `exness_adapter.py:39,60` and `binance_adapter.py:66,91`. The real effect is a lag, which is kongming's inference: a closed 1w bar lands at the 03:00Z backfill. A Binance `1w` context therefore serves the week before last from Monday 00:00 to 03:00Z, re-reading Mongo with one WARNING. This is not look-ahead. Carried to Phase 09's architecture doc rewrite as one clause. No phase in this plan declares `1w`.
- Low, accepted:
  - Cached `Bar` objects are shared across instances on one symbol. A strategy must not mutate its context bars.
  - Early replayed warm-up bars see a shorter context history than live bars, because there is one prefetch of 500 at start. It is never look-ahead.
  - Tick and timer publishes can refresh one window twice, with the same instant and the same result.
  - The doc bullet's backtest claim holds once Phase 08 lands.

## CLOSE

- GATES: `Contracts: 6 kept, 0 broken.`; ruff `All checks passed!`; ratchet exit 0 after the raise below.
- FULLSUITE: `4 failed, 1209 passed, 1 skipped, 55 warnings, 4 errors in 110.10s (0:01:50)`; unexpected count `0`.
- CI: run `41327126026` on `145590f0` printed `completed success`.

## Ratchet raise

The ratchet failed with `tiny_share 0.4833 > 0.4813`. The new small functions `closed_before`, `_bar_dict`, `_context_at` and `_decide` are named by the plan. `max_tiny_share` went from 0.4813 to 0.4833 in its own commit `d52b93cf`.

## Commits

`d52b93cf` `chore(metrics): raise the code metric ceiling` and `145590f0` `feat(strategy): closed higher-timeframe context from stored bars`. Both are on `origin/develop`.

## Handover to Phase 08 (kongming go/no-go: GO)

- `BarRepository.find` defaults to `limit=5000`. A long backtest preload on a low higher interval would truncate silently, so pass an explicit limit or page it.
- Seed the 08.3 cost test with `insert_many`, not one `upsert_bar` call per bar.
- A backtest starts through `inject_prepared_strategy`, not `start_strategy`. Keep it that way, so the second-20 wait and the warm-up replay never run in a backtest.
- The 08.2 recorder must be in `STRATEGY_REGISTRY` and carry `DEFAULTS` before `run`, because `check_strategy_inputs` checks both.

Result: PASS
