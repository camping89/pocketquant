---
phase: 8
title: "Backtest intervals, real sandbox wiring, backtest-path context test"
status: pending
priority: P1
effort: 0.75d
dependencies: [7]
---

# Phase 08: Backtest intervals, real sandbox wiring, backtest-path context test

## Goal

A backtest runs on an ordered `intervals` list that is validated before the run. Its sandbox engine reads real stored bars through the real calendar and tracks positions as live does, and a test proves the backtest hands the strategy the same higher-timeframe context as live at every bucket boundary and across a gap. A multi-timeframe backtest reads each higher interval from Mongo once per run and is at most twice as slow as the same run on the entry interval alone (plan.md D10).

## Context

- Design verdicts (plan.md): the backtest sandbox gets the real bar repository and calendar factory and starts the position tracker. Backtest results keep the top-level `interval` as the entry interval, so the index `ix_backtests_strategy_symbol_interval_started` (`core/infra/persistence/repositories/backtest_repository.py:125-128`) and the rail filter stay. Validation goes through `check_strategy_inputs(code, intervals, parameters)` (Phase 06), which returns 422 for unsorted or duplicate lists and for a parameter of the wrong type, never a silent sort or a 500. <!-- Red team 2026-11-01: #15 --> Legacy backtest runs are not migrated: all are STF and Phase 17 deletes them. Until then they carry only `interval`, so `BacktestResult.from_mongo` reads `intervals` with `.get` (it already ignores legacy keys, `core/domain/backtest/entities.py:78-96`) and a legacy run lists with `intervals == []`. New runs store `intervals` and the entry interval as `interval`.
- Sandbox today: `build_backtest_sandbox()` (`src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:125-139`) builds the engine with `NoStoredBars()` (`:58-60`) and `Continuous24x7CalendarFactory()` (`:68-70`). It never starts `PositionAppService` (comment `:120-124`), so in a backtest the risk check always sees no position (scout-backend trap 5). The only caller is `engine/backtest/backtest_execution_service.py:120`, which holds `self._bar_repo` and `self._calendar_factory` (`:59,63`). `PositionAppService.start()` only loads and subscribes on the bus it is given (`engine/execution/position_app_service.py:31-34`); the in-memory repo has `find_open` (`backtest_sandbox_app_service.py:48-49`).
- Interval readers to change: `BacktestConfig.interval` (`core/domain/backtest/config.py:14`); `RunBacktestCommand.interval` and the payload (`engine/backtest/backtest_command_service.py:20,56`); `_config_from_dict` (`backtest_execution_service.py:36`) and the `StrategyConfig(...)` call in `run` (`:110-118`, which Phase 06 left building `intervals` from the single interval; locate it with `git grep -n "StrategyConfig(" -- src/pocketquant/engine/backtest`); the stream and event (`backtest_app_service.py:104,113`); annualization and persistence (`backtest_report_app_service.py:308-316,336,359`); `BacktestResult` (`core/domain/backtest/entities.py:25-27,51,64,96`); the list route (`app/routes/backtest.py:177-195`).
- The web reads `config_snapshot.interval` to anchor the chart (`web/src/api/backtest-api.ts:236-247`) and still posts `interval` until Phase 12. On `develop` the web backtest form returns 422 between this phase and Phase 12. Nothing deploys before Phase 15.
- R3 (plan.md): with the tracker started, a backtest rejects an entry against an open position as live does. Old runs keep their stored results.
- Test doubles: the stubs move to `tests/strategy_doubles.py` (Phase 05 created it), not a second file (synthesis §3). Importers: `git grep -l -E "NoStoredBars|Continuous24x7CalendarFactory" -- tests` prints 18 files on `e4a998b8` and 15 after Phase 05 deletes the three STF backtest tests. `NoClosedTrades` stays in src (the sandbox uses it). <!-- Red team 2026-11-01: #9 -->
- <!-- Red team 2026-11-01: #15 --> One strategy double (plan.md verdict): the backtest risk test uses `ScriptedStrategy` from `tests/strategy_doubles.py` (Phase 05), registered as `"probe"` by the `probe_registry` fixture; no local strategy class. This phase is the first that needs a per-bar script, so it adds the script mode to `ScriptedStrategy` (Task 08.2 step 1). Later phases extend that mode instead of adding a second one.
- <!-- Red team 2026-11-01: #9 --> Five `BacktestConfig(interval=...)` sites in four test files build the config directly and match neither Files grep: `tests/backtest_test/engine/test_backtest_app_service_persistence.py:117,213`, `test_paper_broker_signal_bar.py:91`, `test_report_annualization_source.py:25`, `test_result_collector_mark_to_market.py:51`. After Phase 05, `git grep -n "BacktestConfig(" -- tests` lists exactly these five.
- Backtest context cost (plan.md D10; `reports/spike-go-no-go.md` rows S4 and `### S4 diagnosis`): the spike measured `find_calls=900 rollovers=900 t_mtf_s=9.57 t_stf_s=1.17` on 30 days of 1m bars with intervals `1m,1h,4h`. A cProfile put 8.6 s of 9.6 s in the per-rollover context read: each rollover re-reads up to `_WARMUP_BARS` (500) bars through `BarRepository.find` and re-parses them, and one Mongo round trip (about 3 ms) already exceeds the 1.3 ms per rollover the bound allows. The owner chose to keep the bound and fix it here: the backtest loads each higher interval once before the replay and slices it in memory, as warm-up does (Phase 07 Task 07.2). The live and warm-up paths keep their behaviour.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:
1. `git status --porcelain -- src web deploy tests scripts docs .github | wc -l` prints `0`.
2. `git fetch -q origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo synced` prints `synced`.
3. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-07-htf-context-live-and-warmup.md` prints `Result: PASS`.
4. `git grep -n "def check_strategy_inputs" -- src | wc -l` prints `1`, and `test -f tests/strategy_doubles.py && echo doubles` prints `doubles`.
5. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`. If it does not, start Docker Desktop in the background and retry after 10 s.

<!-- Consistency sweep 2026-11-01 --> On a resume (plan.md Conventions, EG), line 1 may count only files from this phase's Files list, and line 2 may fail only when `git rev-list --count HEAD..origin/develop` prints `0` (local is ahead by this phase's own unpushed commits).

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 08 after <UTC time>
```

## Files

- Modify (src): `src/pocketquant/core/domain/backtest/config.py`, `src/pocketquant/core/domain/backtest/entities.py`, `src/pocketquant/engine/backtest/backtest_command_service.py`, `src/pocketquant/engine/backtest/backtest_execution_service.py`, `src/pocketquant/engine/backtest/backtest_app_service.py`, `src/pocketquant/engine/backtest/backtest_report_app_service.py`, `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py`, `src/pocketquant/app/routes/backtest.py`, `src/pocketquant/engine/strategy/strategy_app_service.py` (Task 08.3 only).
- Modify (tests): `tests/strategy_doubles.py`, `tests/backtest_test/test_higher_timeframe_context.py`, `tests/backtest_test/test_backtest_single_run_direct_task.py`, `tests/app_test/integration/test_backtest_orders_api.py`, `tests/backtest_test/engine/test_backtest_app_service_persistence.py`, `tests/backtest_test/engine/test_paper_broker_signal_bar.py`, `tests/backtest_test/engine/test_report_annualization_source.py`, `tests/backtest_test/engine/test_result_collector_mark_to_market.py` (the `BacktestConfig(` sites), <!-- Red team 2026-11-01: #9 --> every file listed by `git grep -l -E "NoStoredBars|Continuous24x7CalendarFactory" -- tests`, and every payload site listed by `git grep -n -E "\"interval\": ?\"" -- tests/backtest_test tests/app_test` that feeds `_config_from_dict` or `RunBacktestCommand`.
- Create: `tests/backtest_test/test_backtest_context_cost.py` (Task 08.3).
- Delete: none.

## Tasks

### Task 08.1 — Backtest intervals, validated before the run

**Goal:** `POST /backtest/run` takes `intervals`, rejects an invalid list with 422 before any document is written, and a stored run carries `intervals`, `config_snapshot.intervals` and the entry interval as `interval`.

**Target files and symbols:** `BacktestConfig`, `RunBacktestCommand`, `BacktestCommandService.run`, `_config_from_dict`, `BacktestExecutionService.run`, `BacktestAppService.run`, `BacktestReportAppService` (annualization and `config_snapshot`), `BacktestResult` (`intervals` field, `started`, `to_mongo`, `from_mongo`), `list_backtests`.

**Steps:**
1. Tests first.
   - In `tests/backtest_test/test_backtest_single_run_direct_task.py`, change the `_command()` helper to `"intervals": ["1m"]` and use the `probe_registry` fixture where the file already does. Add `test_run_rejects_unsorted_intervals_before_saving`: `_command(intervals=["5m","1m"])` → `cmd_svc.run` raises an `AppError` whose `error_code == "INVALID_INTERVALS"` and `status_code == 422`; `backtest_runs` has 0 documents. Add `test_a_run_stores_intervals_and_the_entry_interval`: `_command(intervals=["1m","5m"])` → the saved started doc has `intervals == ["1m","5m"]`, `interval == "1m"`, `config_snapshot["intervals"] == ["1m","5m"]` and `config_snapshot["interval"] == "1m"`. <!-- Red team 2026-11-01: #9 --> Add `test_run_rejects_a_parameter_of_the_wrong_type_before_saving`: `_command(parameters={"min_bars": "3"})` → `cmd_svc.run` raises an `AppError` with `error_code == "INVALID_PARAMETERS"` and `status_code == 422`; `backtest_runs` has 0 documents.
   - In `tests/app_test/integration/test_backtest_orders_api.py`, the seeded config (`:36`) gains `"intervals": [interval]`, and the list test (`:150-157`) also asserts `row["intervals"] == ["1m"]`.
2. Run `uv run python -m pytest tests/backtest_test/test_backtest_single_run_direct_task.py tests/app_test/integration/test_backtest_orders_api.py -q 2>&1 | tail -1`. Expected red: `failed` (the command has no `intervals`).
3. `BacktestConfig.interval: str` becomes `intervals: list[str]`.
4. `RunBacktestCommand.interval` becomes `intervals: list[str] = Field(..., description="Ordered intervals, entry first")`. At the top of `BacktestCommandService.run`, call `check_strategy_inputs(cmd.strategy_id, cmd.intervals, cmd.parameters or {})`. The payload writes `"intervals": list(cmd.intervals)` and `"interval": cmd.intervals[0]`, with the comment "The entry interval keeps the history index and the chart anchor."
5. `_config_from_dict` reads `intervals=list(payload["intervals"])`. The `StrategyConfig(...)` in `run` passes `intervals=list(config.intervals)`.
6. `BacktestAppService.run` streams and publishes `config.intervals[0]` (`:104,113`). The report annualizes on `Interval(self._config.intervals[0])`; its `config_snapshot` holds `"intervals"` and `"interval": intervals[0]`; `BacktestResult(...)` gets `interval=intervals[0]` and `intervals=list(intervals)`.
7. `BacktestResult` gains `intervals: list[str] = field(default_factory=list)` after `interval`. `started()` sets `intervals=list(config_snapshot.get("intervals", []))`; `to_mongo` writes `"intervals"`; `from_mongo` reads `data.get("intervals", [])`.
8. `list_backtests` adds `"intervals": r.intervals` next to `"interval"`.
9. Update every payload or command site from the Files grep to `intervals` (for example `tests/backtest_test/test_backtest_dispatch_contract_spec.py:59`, `tests/app_test/integration/test_app_standalone_runtime.py:110`). Sites that only build a stored doc through `BacktestResult.started` may keep `interval`. <!-- Red team 2026-11-01: #9 --> Change each of the five `BacktestConfig(interval=X)` sites listed in Context to `BacktestConfig(intervals=[X])`.

**Success criteria:** the three new tests and the updated list test pass; `git grep -n -E "config\.interval\b|_config\.interval\b" -- src/pocketquant/engine/backtest | wc -l` prints `0`.

**Verify:** `uv run python -m pytest tests/backtest_test tests/app_test/integration/test_backtest_orders_api.py tests/app_test/integration/test_backtest_name_api.py tests/app_test/integration/test_backtest_verdict_api.py -q 2>&1 | tail -1` contains `passed` and no `failed`.

### Task 08.2 — Real sandbox wiring and the backtest-path context test

**Goal:** the sandbox engine reads Mongo through the real calendar, risk sees the run's own positions, and backtest contexts equal live contexts.

**Target files and symbols:** `build_backtest_sandbox`, its comment, `NoStoredBars`, `Continuous24x7CalendarFactory` (`backtest_sandbox_app_service.py:58-70,120-139`); `BacktestExecutionService.run` (`:120`); `tests/strategy_doubles.py` (`ScriptedStrategy.SCRIPT`, `ScriptedStrategy.script`); `tests/backtest_test/test_higher_timeframe_context.py`.

**Steps:**
1. <!-- Red team 2026-11-01: #15 --> Script mode on the shared double, in `tests/strategy_doubles.py`: `ScriptedStrategy` gains `SCRIPT: ClassVar[tuple[dict | None, ...] | None] = None`, and `__init__` sets `self.script: list[dict | None] | None = None if self.SCRIPT is None else list(self.SCRIPT)`. In `on_bar_completed`, after appending the bar: when `self.script is not None`, pop its first item (`None` once it is empty); a `dict` item returns `dataclasses.replace(<the fixed-rule LONG signal built from this bar>, **item)`, and `None` returns `None`; otherwise the fixed rule runs unchanged. One `#` comment above `SCRIPT`: a backtest builds its own instance, so a test sets the script on the class with `monkeypatch`, which restores it after the test. Tests that hold the instance may set `script` on it instead.
2. Tests first, added to `tests/backtest_test/test_higher_timeframe_context.py`. Reuse its seed helpers and `_Recorder`. Build the service as `_execution(database)` in `test_backtest_single_run_direct_task.py:96-106` does, and run through `BacktestCommandService.run` then `execute_and_persist`.
   - `test_backtest_contexts_equal_live_contexts_at_every_boundary`: the Phase 07 main seed; `monkeypatch.setitem(STRATEGY_REGISTRY, "recorder", _Recorder)`. `_Recorder` appends to a class-level list `_Recorder.runs` as well as `self.seen`, so the instance the service builds is readable; reset it at the test start. Run intervals `["1m","1h"]` from 2026-01-05 00:00 to 03:09, `parameters={}`. The live list comes from the Phase 07 live helper (an engine started at 00:00:25 that publishes every stored 1m start). The two lists are equal entry by entry, and every entry whose timestamp is on the hour (01:00, 02:00, 03:00) ends with the previous hour's bar (governance checks 1-3).
   - `test_backtest_rejects_an_entry_against_its_open_position` (`@pytest.mark.usefixtures("probe_registry")`, code `"probe"`): `monkeypatch.setattr(ScriptedStrategy, "SCRIPT", ({}, {"direction": Direction.SHORT, "stop_loss_price": 101.0, "take_profit_price": 99.0}))`, so the first bar gives the fixed-rule LONG (stop 99, target 101) and the second bar a SHORT. Seed six flat 1m bars (open, high, low and close 100.0) and run intervals `["1m"]` with `slippage_bps=0` and `commission_bps=0`; no stop or target is touched. `BacktestOrderRepository(database).list_by_run(run_id)` has exactly 1 order (side BUY). Without the tracker the SHORT fills and closes the long: 2 orders.
3. Run `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1`. Expected red: `2 failed` (the stub repo gives no context; the SHORT fills).
4. `build_backtest_sandbox(*, bar_repository: BarRepository, calendar_factory: TradingCalendarFactory)` (type imports under `TYPE_CHECKING`). Keep the tracker in a local, `positions = PositionAppService(bus, _InMemoryPositionRepo())`, and pass both to `StrategyAppService`. After `await engine.start()`, call `await positions.start()`. The order matters: strategies subscribe to `BarCompletedEvent` first, and the tracker only subscribes to `OrderFilledEvent`.
5. Rewrite the comment above it: "A backtest must not share the live EventBus: replayed bars or synthetic exit fills would drive live handlers and let concurrent runs cross-talk. The position tracker runs on the private bus, so risk and EXIT read the run's own position as live does. Bars and calendars are the real ones, so higher-timeframe context matches live."
6. `BacktestExecutionService.run` calls `build_backtest_sandbox(bar_repository=self._bar_repo, calendar_factory=self._calendar_factory)`.
7. Move `NoStoredBars` and `Continuous24x7CalendarFactory` verbatim into `tests/strategy_doubles.py` and delete them from src, together with the now-unused imports (`Bar`, `Continuous24x7Calendar`, `ITradingCalendarPort`). In every file from `git grep -l -E "NoStoredBars|Continuous24x7CalendarFactory" -- tests`, import them from `tests.strategy_doubles` (the form `from tests.x import` already works, `tests/app_test/integration/test_safeguards_api.py:18`). Keep `NoClosedTrades` imported from the sandbox module.

**Success criteria:** both tests pass; `git grep -n "(IStrategyService)" -- tests/backtest_test/test_higher_timeframe_context.py | grep -v -c "class _Recorder"` prints `0` (no new local strategy class); `git grep -n -E "class NoStoredBars|class Continuous24x7CalendarFactory" -- src | wc -l` prints `0`; `git grep -n "build_backtest_sandbox()" -- src tests | wc -l` prints `0`.

**Verify:** `uv run python -m pytest tests/backtest_test tests/engine_test -q 2>&1 | tail -1` contains `passed` and no `failed`, and `uv run python -m pytest tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `11 passed`.

### Task 08.3 — Backtest context loaded once per run

**Goal:** a backtest makes one `BarRepository.find` per higher interval for the whole run, serves every rollover from memory with the same `closed_before` rule, and stays within `t_mtf_s <= 2 * t_stf_s`.

**Target files and symbols:** `StrategyAppService` (`_refresh_context`, `_closed_bars`, a new method that preloads a run's higher bars) in `src/pocketquant/engine/strategy/strategy_app_service.py`; `BacktestExecutionService.run` (where it starts the strategy, after Task 08.2 step 6); new `tests/backtest_test/test_backtest_context_cost.py`.

**Steps:**
1. Test first, in the new file. Seed 30 days of 1m bars (43,200) for `BTCUSDT:BINANCE` from 2026-01-01 with their 1h (720) and 4h (180) aggregates, as the spike did. Wrap the repository the execution service uses in a `find` counter per interval (the `_CountingBars` pattern from `tests/backtest_test/test_higher_timeframe_context.py`). Use the `probe_registry` fixture and `monkeypatch.setattr(ScriptedStrategy, "SCRIPT", ())`, so the probe returns no signal on every bar and both runs measure replay cost only. Time `BacktestCommandService.run` plus `execute_and_persist` once with intervals `["1m","1h","4h"]` and once with `["1m"]` (`time.perf_counter`). Print one line `context_cost find_1h=<n> find_4h=<n> t_mtf_s=<x> t_stf_s=<y>`. Assert `finds["1h"] == 1`, `finds["4h"] == 1` and `t_mtf_s <= 2 * t_stf_s`. Name it `test_a_multi_timeframe_backtest_reads_each_higher_interval_once`.
2. Run `uv run python -m pytest tests/backtest_test/test_backtest_context_cost.py -q -s 2>&1 | tail -3`. Expected red: the find counts are about 720 and 180, and the time bound fails.
3. Implement. `StrategyAppService` gains one method the backtest calls once per run, after the strategy is loaded and before the first replayed bar. For each name in `config.intervals[1:]` it reads the higher bars once, from `_WARMUP_BARS` bars before the run start through the run end, and keeps them in memory per `(symbol, interval)`. When that preload exists for a key, `_refresh_context` takes the window's bars from it with `closed_before(preloaded, step, instant)` (keep at most `_WARMUP_BARS` of them, as `_closed_bars` does), instead of calling `_closed_bars`. Slice by start time (for example `bisect` over the sorted starts) rather than re-filtering the whole run list on every bar. Keep the completeness check and the WARNING exactly as Phase 07 wrote them. `_context_at` and `closed_before` stay unchanged, so no look-ahead rule moves. Live and warm-up never call the new method and keep their Mongo reads. Put one `#` WHY comment above the new method: a backtest replays thousands of rollovers, and one Mongo round trip per rollover costs more than the whole replay of a bar.
4. Run the new test and the context tests from Task 08.2.

**Success criteria:** the cost test passes with `find_1h=1 find_4h=1` and the time bound met; `test_backtest_contexts_equal_live_contexts_at_every_boundary` still passes unchanged, so the preloaded contexts equal live at every boundary and across the gap.

**Verify:** `uv run python -m pytest tests/backtest_test/test_backtest_context_cost.py tests/backtest_test/test_higher_timeframe_context.py -q 2>&1 | tail -1` contains `12 passed` and no `failed`, and `uv run python -m pytest tests/backtest_test/test_backtest_context_cost.py -q -s 2>&1 | grep -c "^context_cost find_1h=1 find_4h=1 "` prints `1`.

### Task 08.4 — CLOSE

**Goal:** the phase lands on `develop` with every gate green; nothing deploys.

**Target files and symbols:** none new; `pyproject.toml` `[tool.code-metrics]` only if the ratchet alone fails.

**Steps:**
1. GATES: `uv run lint-imports | tail -1` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet; echo "exit=$?"` prints `exit=0`; `uv run ruff check src tests scripts; echo "exit=$?"` prints `exit=0`. If only the ratchet fails, raise the ceiling in its own commit `chore(metrics): raise the code metric ceiling` and record the old and new values in the report.
2. FULLSUITE: `uv run python -m pytest tests/ -q > .cache/pytest.txt 2>&1; tail -1 .cache/pytest.txt; grep -E "^(FAILED|ERROR) " .cache/pytest.txt | grep -v -E "test_utc_runtime_guard|test_cron_trigger_timezone" | wc -l`. The tail contains `4 failed` and `4 errors`; the count prints `0`.
3. Commit: `feat(backtest): run over ordered intervals with stored context and live risk`.
4. Push: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop && git fetch origin && test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo pushed` prints `pushed`.
5. `sleep 15`, then repeat the Verify command until it prints `completed`.

**Success criteria:** CI on the pushed HEAD concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.headSha) \(.status) \(.conclusion)"'` prints `<git rev-parse HEAD> completed success`.

## Rollback

Nothing is deployed. Run `git revert --no-edit <phase-commit>` (plus the metric commit, if any) and push. Stored runs written by this code carry `intervals` in addition to `interval`; the old code ignores the extra key.

## Report

`reports/phase-08-backtest-intervals-backend.md` holds: the commit SHAs; the new and changed test names with pass counts; the number of importer files moved to `tests.strategy_doubles` (15 expected); the five `BacktestConfig(` sites changed; the `context_cost` line from Task 08.3 verbatim; the FULLSUITE tail line; the CI run id and conclusion; any metric ceiling change. It ends with `Result: PASS`.

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
