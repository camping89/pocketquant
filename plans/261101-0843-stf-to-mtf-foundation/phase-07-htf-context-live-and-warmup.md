---
phase: 7
title: "Higher-timeframe context: live and warm-up"
status: completed
priority: P1
effort: 1d
dependencies: [6]
---

# Phase 07: Higher-timeframe context: live and warm-up

## Goal

On every closed entry bar, live and warm-up, the strategy receives `bar["context"] = {interval: [closed Bar, ascending]}` for `intervals[1:]`. The bars come from Mongo through one per-(symbol, interval) cache, filtered by one pure "closed before the entry bar's start" rule, and a start before second 20 never replays a partial bar.

## Context

- Design verdicts (plan.md): a higher bar `b` is visible when `b.datetime + step(b.interval) <= entry_bar_start`, and the instant is `bar["timestamp"]` in every path. There is no clock, wait, lag constant or `updated_at` check. The cache is `self._context[(symbol, interval)]`, refreshed only when `calendar.bar_start(instant, interval)` moves. A miss is cached only when the previous bucket is present or has no trading minutes; otherwise it is re-read on the next entry bar with one WARNING per (symbol, interval, window). No new module, class or lock.
- <!-- Red team 2026-11-01: #15 --> Executor decisions (plan.md does not settle these two details; both implement its verdicts and change none):
  - The cache value is `(window_start, bars, complete)`. `complete` implements the verdict "a miss is cached only when the previous bucket is present or has no trading minutes": an incomplete read is served for that entry bar only and re-read on the next one. The same flag makes the WARNING fire once per window, without a second dict.
  - The warm-up wait condition is `now.second < _WARMUP_READY_SECOND and bars`. The verdict's purpose is that warm-up never replays a partial bar. A store with no closed entry bars has nothing to replay, and a tracked symbol stores its entry interval whenever it stores a higher one, so skipping the wait there replays nothing partial. It also keeps tests that start a strategy on the wall clock over an empty store (the fixtures built on `NoStoredBars`) from sleeping up to 20 s at random.
- `_on_bar_completed` loops instances serially (`src/pocketquant/engine/strategy/strategy_app_service.py:367`), so two instances on one symbol never race on the cache.
- The only closed filter today is `_closed_bars` (`strategy_app_service.py:285-289`): `find(..., end_date=now, limit=_WARMUP_BARS)`, reversed, then `b.datetime + step <= now`. `BarRepository.find` sorts descending with `$lte` (`core/infra/persistence/repositories/bar_repository.py:100-128`).
- Warm-up calls `strategy.on_bar_completed` directly (`strategy_app_service.py:252-264`) under "No I/O from here" (`:250`). The live bar dict is built a second time at `:380-389`. Both get one `_bar_dict` helper and one `_decide` helper.
- Warm-up trap (synthesis D1): the wait at `:240-248` fires only when the last stored entry bar is missing. At hh:00:05 a cascaded entry bar (15m and up) is already stored, but partial. It passes `_closed_bars`, so a partial entry bar and a partial higher-bucket prefetch are replayed. `sync_1m` runs at second 12 (`engine/market_data/app_services/sync_jobs.py:734-740`).
- Calendars: `bar_start` and `trading_minutes` are on the port (`core/domain/market_data/trading_calendar_port.py:37-41`). Exness 1w starts Sunday 00:00Z (`core/infra/calendars/exness_session_calendar_adapter.py:84-89`). XAUUSD is closed Tue 20:58:00 to 22:00:29 UTC, so the 21:00 1h bucket has no trading minutes (`:63-66`).
- Names Phase 06 provides: `StrategyConfig.intervals: list[str]` (entry = `intervals[0]`); `_find_strategies` and `start_strategy` already read `config.intervals[0]`.
- Logs: one DEBUG `strategy.context_loaded` per Mongo read, never INFO (CLAUDE.md log policy). One WARNING `strategy.context_previous_bucket_missing`.
- Doc: one Decisions bullet in `docs/system-architecture.md`, written as a pointer per `docs/governance/documentation-rules.md`.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:
1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`.
3. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-06-subscription-contract.md` prints `Result: PASS`.
4. `git grep -n -E "^    intervals: list\[str\]" -- src/pocketquant/core/domain/strategy/value_objects.py | wc -l` prints `1`.
5. `git grep -n "_context\[" -- src/pocketquant/engine/strategy/strategy_app_service.py | wc -l` prints `0` (on a resume, skip each task whose Verify already passes).
6. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`. If it does not, start `"/c/Program Files/Docker/Docker/Docker Desktop.exe"` in the background and retry after 10 s.

<!-- Consistency sweep 2026-11-01 --> On a resume (plan.md Conventions, EG), line 1 may count only files from this phase's Files list, and line 2 may fail only when `git rev-list --count HEAD..origin/develop` prints `0` (local is ahead by this phase's own unpushed commits).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 07 after <UTC time>
```

## Files

- Create: `tests/backtest_test/test_higher_timeframe_context.py` (it uses the `database` fixture of `tests/backtest_test/conftest.py:38-55`; Phase 08 adds the backtest-path tests to it).
- Modify: `src/pocketquant/engine/strategy/strategy_app_service.py`, `docs/system-architecture.md`.
- Delete: none.

## Tasks

### Task 07.1 — Context tests (red), then the filter, cache and live path

**Goal:** the live path serves closed higher bars from the shared cache, with at most one Mongo read per (symbol, interval) rollover.

**Target files and symbols:** `strategy_app_service.py`: new module function `closed_before`, new module function `_bar_dict`, `StrategyAppService.__init__` (`self._context`), new `_refresh_context`, new `_context_at`, new `_decide`, `_closed_bars`, `_on_bar_completed`; the new test file.

**Steps:**
1. Write the test file. Helpers:
   - `_CountingBars(BarRepository)` overrides `find` to add one to `self.finds[interval.value]` (a `Counter`) and then call `super().find`.
   - A `bars` fixture drops `COLLECTION_BARS` from `database` and returns `_CountingBars(database)`.
   - `_Calendars(calendar)` has `async def for_symbol(self, symbol)` returning that calendar.
   - `_Recorder(IStrategyService)` appends `(bar["timestamp"], bar["close"], {k: [(b.datetime, b.close) for b in v[-3:]] for k, v in bar["context"].items()})` to `self.seen` and returns `None`.
   - `_engine(bars, calendar)` builds `StrategyAppService` with a paper factory, `OrderAppService`/`PositionAppService` over an in-memory repo (copy `_Factory` and `_Repo` from `tests/engine_test/test_strategy_warm_up.py:52-71`), `RiskCheckHandler()` and `NoClosedTrades()`.
   - `_seed(bars, symbol, interval, starts, closes)` calls `upsert_bar(..., source="test")`.
   - `_publish(engine_bus, symbol, interval, start)` calls `set_simulation_time(bar_end + 1 s)` and then publishes a `BarCompletedEvent` with `bar_end = start + step` and `closed_by="timer"`.
   - The autouse fixture rebinds `engine_module.logger` (as `test_strategy_warm_up.py:84-90` does) and clears the simulation time after the test.

   Main seed: `BTCUSDT:BINANCE` on `Continuous24x7Calendar()`; 1m bars 2026-01-05 00:00-03:09 except 01:30-01:49 (a gap); 1h bars at 2026-01-04 22:00 and 23:00 (closes 98, 99), then 2026-01-05 00:00, 01:00, 02:00 and 03:00 (closes 100, 101, 102, 999; 03:00 is the partial current bucket). Recorder intervals `["1m","1h"]`. Tests:
   - `test_live_first_entry_bar_of_a_bucket_sees_the_previous_bucket_close`: start at 00:59:25; publish 00:59 and 01:00. The 01:00 bar's `1h` context ends with `(00:00, 100.0)`.
   - `test_live_entry_bars_never_see_their_own_bucket`: same start; publish 00:59, 01:59 and 02:00. 00:59 ends with `(23:00, 99.0)`, 01:59 ends with `(00:00, 100.0)`, 02:00 ends with `(01:00, 101.0)`.
   - `test_a_partial_bucket_is_never_served`: start at 03:00:25; publish 03:00 to 03:05. Every context ends with `(02:00, 102.0)`, and no context bar has close `999.0`.
   - `test_context_is_read_once_per_rollover_for_two_instances`: two recorders `a` and `b`, both started at 00:58:25; publish 00:58, 00:59, 01:00 and 01:01. `bars.finds["1h"] == 2`.
   - `test_exness_weekly_context_rolls_on_sunday`: `EXNESS_CALENDARS[1]` (XAUUSD), symbol `XAUUSD:EXNESS`, intervals `["1h","1w"]`; 1w bars at 2026-09-27, 10-04 and 10-11. Start at 2026-10-09 20:00:25 and publish the 1h bars at 2026-10-09 19:00 and 2026-10-11 22:00. Their contexts end at 2026-09-27 and 2026-10-04.
   - `test_a_missing_previous_bucket_is_requeried_next_bar`: own seed: 1h bar 00:00 only, no 1m bars. Start at 01:59:25 and publish 02:00 and 02:01. Then upsert the 01:00 bar (close 101) and publish 02:02 and 02:03. `finds["1h"] == 4`. The 02:02 context ends with `(01:00, 101.0)`. `capture_logs` holds exactly one `strategy.context_previous_bucket_missing`.
   - `test_a_session_gap_bucket_is_cached`: XAUUSD calendar, intervals `["15m","1h"]`, 1h bars Tue 2026-10-13 18:00, 19:00 and 20:00, no 15m bars. Start at 21:59:25 and publish 22:00 and 22:15. `finds["1h"] == 2`, both contexts end at 20:00, and there is no WARNING.
2. Run `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`. Expected red: `7 failed` (no `context` key; the recorder raises and the engine logs `strategy_on_bar_error`).
3. Implement in `strategy_app_service.py`:
   - `def closed_before(bars: list[Bar], step: timedelta, instant: datetime) -> list[Bar]` returns `[b for b in bars if b.datetime is not None and b.datetime + step <= instant]` (input ascending). `_closed_bars` becomes `closed_before(list(reversed(found)), step, now)`.
   - `def _bar_dict(symbol, interval, source, start) -> dict` builds the eight keys of `:380-389` from any object with `open/high/low/close/volume`.
   - In `__init__`: `self._context: dict[tuple[str, str], tuple[datetime, list[Bar], bool]] = {}` with the comment "Process lifetime in live, one run in a backtest; one entry per (symbol, higher interval)."
   - `async def _refresh_context(self, config, instant)`: return when `len(config.intervals) < 2`. Get the calendar from `self._calendar_factory.for_symbol(config.symbol)`. For each name in `intervals[1:]`: compute `interval`, `step` and `window = calendar.bar_start(instant, interval)`. Skip when the cached window equals `window` and `complete` is true. Otherwise `bars = await self._closed_bars(config.symbol, interval, step, instant)` and `complete = (bool(bars) and bars[-1].datetime == window - step) or not calendar.trading_minutes(window - step, window)`. Log DEBUG `strategy.context_loaded` (symbol, interval, window, bars). If incomplete and the cache did not already hold this window, log WARNING `strategy.context_previous_bucket_missing` (symbol, interval, window). Store `(window, bars, complete)`.
   - `def _context_at(self, config, instant) -> dict[str, list[Bar]]` returns `{n: closed_before(self._context[(config.symbol, n)][1], step(n), instant) for n in config.intervals[1:]}`. Put a WHY comment above it: the instant is the entry bar's start, so an entry bar never reads its own higher bucket (`docs/governance/no-look-ahead-rules.md`).
   - `async def _decide(self, strategy, bar) -> Signal | None` sets `bar["context"] = self._context_at(strategy.config, bar["timestamp"])` and returns `await strategy.on_bar_completed(bar)`.
   - In `_on_bar_completed`, replace the dict at `:380-389` and the call at `:391` with `await self._refresh_context(strategy.config, event.bar_start)`, then `signal = await self._decide(strategy, _bar_dict(event.symbol, event.interval, event, event.bar_start))`, both inside the existing `try`, so a Mongo error logs `strategy_on_bar_error` and skips only that instance.
4. Commit nothing yet (CLOSE commits).

**Success criteria:** the seven tests pass; `git grep -n "closed_before" -- src` shows the definition and at least two uses.

**Verify:** `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `7 passed` and no `failed`.

### Task 07.2 — Warm-up prefetch, slicing, and the second-20 wait

**Goal:** warm-up replays with the same context the live path gives, without I/O inside the replay, and never replays a partial bar.

**Target files and symbols:** `StrategyAppService.start_strategy` (`strategy_app_service.py:219-283`); the test file.

**Steps:**
1. Add the tests:
   - `test_warm_up_contexts_equal_live_contexts`: main seed. Engine A starts its recorder at 03:10:25 (warm-up replays 00:00-03:09). Engine B starts at 00:00:25 and publishes every stored 1m start from 00:00 to 03:09 through `_publish`. `A.seen == B.seen`. The gap and every hour boundary are inside the range, so governance check 2 holds.
   - `test_a_start_before_second_20_waits_and_replays_the_final_bar`: 24/7 calendar, intervals `["15m","1h"]`. 15m bars at 11:00, 11:15, 11:30 and 11:45 (11:45 close 1.0), 1h bars at 10:00 and 11:00 (11:00 close 1.0). The simulation time is 12:00:05. `real = asyncio.sleep`. `monkeypatch.setattr(engine_module.asyncio, "sleep", fake)`, where `fake(s)` awaits `real(s)` when `s < 1`; otherwise it records `s`, upserts 11:45 15m and 11:00 1h with close 2.0, and sets the simulation time to 12:00:20. Start, then publish the 15m bar 12:00. Asserts: recorded sleeps `== [15.0]`; the replayed 11:45 entry has close `2.0`; the 12:00 context ends with `(11:00, 2.0)`; `finds["1h"] == 1`.
2. Run `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`. Expected red: `2 failed`.
3. In `start_strategy`, replace the wait condition at `:240-244` with `if now.second < _WARMUP_READY_SECOND and bars:`. Keep the sleep and the re-read. Put this comment above it: "A cascaded interval stores its in-progress bar, so before sync_1m settles the last bucket at second 12 the newest stored entry and higher bars may be partial; wait for it." Update the constant's comment at `:46` to match.
4. After the wait and before `on_start()`, call `await self._refresh_context(config, now)`. This is the one prefetch per context interval; for the live path it is also the cache entry of the current window.
5. Replace the replay call at `:253-264` with `signal = await self._decide(strategy, _bar_dict(config.symbol, config.intervals[0], stored, stored.datetime))`. `_decide` does no I/O, so the "No I/O from here" comment stays true.

**Success criteria:** all nine tests pass. `tests/engine_test/test_strategy_warm_up.py` still passes unchanged (its clock is at second 25).

**Verify:** `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py tests/engine_test/test_strategy_warm_up.py tests/engine_test/test_strategy_entry_guards.py tests/engine_test/test_concurrent_opens.py -q 2>&1 | tail -1` contains `passed` and no `failed`. Then `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `9 passed`.

### Task 07.3 — Architecture bullet

**Goal:** the cross-file decision and its known limit are written once.

**Target files and symbols:** `docs/system-architecture.md`, section `## Decisions` (after the "Strategies are declarative" bullet).

**Steps:**
1. Add exactly one bullet: "- **Higher-timeframe context comes from stored bars.** On each closed entry bar the engine gives the strategy the higher-interval bars from Mongo that closed by the entry bar's start, through one cache per symbol and interval (`StrategyAppService._context_at`). Live, warm-up and backtest use the same rule (`docs/governance/no-look-ahead-rules.md`). Rejected: bars built from live ticks in the trader, which a backtest cannot replay. Limit: if `sync_1m` stores a bucket's final value only after the first entry bar of the next bucket has closed (a worker handover or a slow vendor call), the engine serves that partial bucket until the next rollover; the data-lag monitor is the only signal."
2. Check that every path and symbol in the bullet exists: `git grep -n "_context_at" -- src | wc -l` prints at least `1`.

**Success criteria:** one new bullet; the doc stays under 800 lines.

**Verify:** `git grep -n -c "Higher-timeframe context comes from stored bars" -- docs/system-architecture.md` prints `docs/system-architecture.md:1`.

### Task 07.4 — CLOSE

**Goal:** the phase lands on `develop` with every gate green; nothing deploys.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet alone fails.

**Steps:**
1. GATES: `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; `uv run ruff check src tests scripts; echo "exit=$?"` prints `exit=0`. If only the ratchet fails, raise the ceiling in its own commit `chore(metrics): raise the code metric ceiling` and record the old and new values in the report.
2. FULLSUITE: run `docker ps` (start Docker Desktop if it fails), then `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. The tail contains `4 failed` and `4 errors`; the count prints `0`.
3. Commit: `feat(strategy): closed higher-timeframe context from stored bars`.
4. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
5. `sleep 15`, then repeat the Verify command until it prints `completed`.

**Success criteria:** CI on the pushed HEAD concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.headSha) \(.status) \(.conclusion)"'` prints `<git rev-parse HEAD> completed success`.

## Rollback

Nothing is deployed. Run `git revert --no-edit <phase-commit>` (plus the metric commit, if any) on `develop` and push. No stored data changes. A strategy with one interval gets `bar["context"] == {}`.

## Report

`reports/phase-07-htf-context-live-and-warmup.md` holds: the commit SHAs; the nine test names with pass counts; the FULLSUITE tail line; the CI run id and conclusion; any metric ceiling change (old → new); and a note that the cache tuple and the warm-up wait condition follow the executor decisions in Context. It ends with `Result: PASS`.

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
