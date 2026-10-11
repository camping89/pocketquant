---
phase: 2
title: "Characterization tests and metric baseline"
status: pending
priority: P1
effort: 2d
dependencies: [1]
---

# Phase 02: Characterization tests and metric baseline

## Context Links
- Sync jobs: `src/pocketquant/engine/market_data/app_services/sync_jobs.py`. Symbols: `SYNC_INTERVALS` (:54), `CATCHUP_TARGETS` (:72), `_sync_by_intervals` (:130), `sync_1m` (:382), `sync_verify_cascade` (:511), `sync_backfill` (:609), `register_sync_jobs` (:663).
- Integrity: `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` (`check_integrity` :33, `repair_integrity` :76). Cascade: `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` (`cascade_for_symbol` :140).
- DI: `src/pocketquant/app/di/*.py` (11 files). Test container builder: `tests/app_test/integration/app_factory.py` (`TestCoreProvider` :46, `make_test_app` :66).
- Existing snapshots: `tests/baseline/test_openapi_snapshot.py` and `tests/baseline/test_route_inventory.py`.
- Windows note: Git Bash `/tmp` and Windows Python `/tmp` are different folders, so every file a Python step reads is written to a repo-relative path (`.cache/` is gitignored).

<!-- Updated: Validation Session 1 - OKX characterization dropped; BrokerFactory pinned by T2.5 -->
## Goal
Pin today's observable behaviour before any refactor: the sync jobs, the cascade output, the DI graph (including `BrokerFactory`) and the API surface (snapshots). Record the baseline gate and the metric numbers. No production code changes in this phase. OKX code is not touched by any phase, so it gets no characterization test of its own; the venue command in T2.6 keeps its existing tests counted.

## Files to Create or Modify
- Create: `scripts/code_metrics.py`, `tests/scripts/test_code_metrics.py`
- Create: `tests/app_test/integration/test_sync_pipeline_characterization.py`, `tests/app_test/integration/test_di_resolution_characterization.py`
- Modify: `tests/app_test/integration/app_factory.py` (add `build_test_container`)
- Create: `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt`, `.../reports/metrics-baseline.json`, `.../reports/metrics-current.json`

## Tasks

### T2.1 Branch and baseline gate record
- **Goal:** A recorded green baseline, so any later failure can be attributed.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt`
- **Steps:**
  1. `git switch master && git pull --ff-only && git switch -c test/sync-characterization` (local `master` already carries the Phase 01 fixture commit).
  2. `docker info > /dev/null && echo docker-ok`
  3. `just test 2>&1 | tail -n 1`. Write it to the file as `full: <line>`.
  4. `uv run ruff check | tail -n 1`, `uv run pyright | tail -n 1` and `uv run lint-imports | grep Contracts`. Write each line as `ruff: `, `pyright: ` and `lint-imports: `.
- **Success criteria:** The baseline is green. If it is not, this is an unexplained failure, so STOP.
- **Verify:** `grep -c "passed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt` ≥ 1. `grep -c "failed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt` prints `0`. `grep -c "Contracts: 7 kept, 0 broken." plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt` prints `1`.

<!-- Updated: Validation Session 1 - --out for Windows-safe output, --ratchet reads frozen ceiling, no --soft -->
### T2.2 Metric script with a pinned definition
- **Goal:** A reproducible measure of tiny methods and pure delegations that matches the advisor's baseline, and that can enforce a frozen ceiling later.
- **Target files and symbols:** `scripts/code_metrics.py` → `measure(path: Path) -> dict`, `load_ceiling(pyproject: Path) -> dict`, `main(argv: list[str] | None = None) -> int`
- **Steps:**
  1. Population: every `ast.FunctionDef` and `ast.AsyncFunctionDef` in `*.py` under `--path` (default `src/pocketquant`), including methods and nested functions. Read files as UTF-8.
  2. Define `body` as the function body without a leading docstring (`Expr` holding a `str` `Constant`).
  3. **Measured set** for the tiny share excludes functions with any of these properties:
     - `body` is empty, or consists only of `...` or `pass`;
     - a decorator named `property`, `setter`, `cached_property` or `abstractmethod`, matched on the `Name.id` or `Attribute.attr` (for `Call` decorators, use the callee);
     - a name of the form `__x__`.
  4. `tiny` counts measured functions with `len(body) <= 2`. `tiny_share = tiny / functions_measured`, rounded to 4 decimals.
  5. `delegations` counts population functions, with no exclusions, whose `body` is exactly one `Return` or `Expr` statement. After unwrapping one `Await`, its value must be an `ast.Call` whose `func` is an `ast.Attribute`.
  6. `functions_over_60` lists `"<relative path>:<lineno> <name> <length>"` for functions where `end_lineno - lineno + 1 > 60`.
  7. The returned dict has the keys `functions_total`, `functions_measured`, `tiny`, `tiny_share`, `delegations` and `functions_over_60`.
  8. CLI flags:
     - `--path`;
     - `--json` prints the dict;
     - `--out PATH` writes the same JSON (UTF-8) to `PATH`, creating parent folders, and prints nothing else;
     - `--max-tiny-share FLOAT` and `--max-delegations INT` set explicit ceilings;
     - `--ratchet` reads the ceilings from `[tool.code-metrics]` (`max_tiny_share`, `max_delegations`) in `pyproject.toml` with `tomllib` through `load_ceiling`; a missing section prints `code-metrics: no [tool.code-metrics] ceiling` and exits 2.
     - When a measured value is above its ceiling, print `::error title=code-metrics::<metric> <value> > <ceiling>` and exit 1. Exit 0 otherwise.
  9. Write `tests/scripts/test_code_metrics.py`, importing `from scripts.code_metrics import measure, load_ceiling, main`. Write synthetic files into `tmp_path` and assert each rule:
     - a docstring is not counted;
     - a stub, a property or a dunder is excluded;
     - `return self.a.b(x)`, `await self.a.b()` and a bare `self.x.append(y)` each count as a delegation;
     - `return f(x)` does not count, and neither do two statements;
     - a 61-line function is listed in `functions_over_60`;
     - `main(["--path", str(tmp_path), "--out", str(tmp_path / "o" / "m.json")])` returns 0 and the file holds the dict;
     - `load_ceiling` reads a synthetic `pyproject.toml`; `main([... "--max-delegations", "0"])` on code with one delegation returns 1.
- **Success criteria:** The script works and the unit tests pass.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/scripts/test_code_metrics.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - writes through --out -->
### T2.3 Metric baseline at the pre-plan commit
- **Goal:** Prove the script reproduces the confirmed baseline (48% tiny, 63 delegations).
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json`, `.../reports/metrics-current.json`
- **Steps:**
  1. `git worktree add ../pq-metric-baseline 29f2f67`
  2. `uv run python scripts/code_metrics.py --path ../pq-metric-baseline/src/pocketquant --out plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json`
  3. `git worktree remove ../pq-metric-baseline`
  4. `uv run python scripts/code_metrics.py --out plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-current.json`
- **Success criteria:** The baseline at `29f2f67` is functions 794, measured 661, tiny 315 (0.4766) and delegations 63.
- **Verify:** `uv run python -c "import json;d=json.load(open('plans/261009-0858-exness-venue-lean-sync-refactor/reports/metrics-baseline.json'));print(d['functions_total'],d['functions_measured'],d['tiny'],d['delegations'])"` prints `794 661 315 63`.

<!-- Updated: Validation Session 1 - later phases may edit the import line and fixture wiring only -->
### T2.4 Sync pipeline characterization test (real Mongo/Redis)
- **Goal:** Pin what the five scheduled jobs write and record, independent of module paths and provider wiring.
- **Target files and symbols:** `tests/app_test/integration/test_sync_pipeline_characterization.py`
- **Steps:**
  1. Async fixture `deps(settings)`:
     - Connect `Database()` and `Cache()` with `settings`.
     - Build `BarRepository`, `SymbolRepository`, `SyncStatusRepository`, `JobHistoryRepository` and `TrackedSymbolRepository` with the db, and call `ensure_indexes()` on each.
     - Run `delete_many({})` on the collections `bars`, `sync_status`, `symbols`, `job_history` and `tracked_symbols` (constants in `src/pocketquant/core/common/constants.py`), before and after the test.
     - Seed `TrackedSymbol(symbol="BTCUSDT:BINANCE")` with `TrackedSymbolRepository.upsert`.
  2. `FakeProvider(IDataProvider)`: `fetch_ohlcv(symbol, interval, n_bars)` appends `(symbol, interval, n_bars)` to `self.calls` and returns `n_bars` closed, aligned bars that end at `get_bar_start(now, interval) - step`. Price is deterministic, `open = 100 + i`, `high = open + 2`, `low = open - 1`, `close = open + 1`, `volume = 1 + i % 3`, `tick_count = 1`. Cap the return at 100 bars per call to keep the test fast.
  3. Build a real `SyncService(provider=fake, cache=cache, bar_repository=..., symbol_repository=..., sync_status_repository=...)` and a `FakeContainer` whose `async get(cls)` maps `SyncService`, `JobHistoryRepository`, `TrackedSymbolRepository`, `BarRepository` and `IDataProvider` to these objects.
  4. A `RecordingScheduler` with `add_cron_job(func, *, job_id, **kw)` and `add_one_off_job(func, *, job_id, **kw)` stores the calls. Call `await register_sync_jobs(container, recording_scheduler)`, imported from `pocketquant.engine.market_data.app_services.sync_jobs`. Resolve each stored `func` text `module:name` with `importlib.import_module(module)` and `getattr`.
  5. Later phases may edit only two things in this file: the `register_sync_jobs` import line, and the fixture wiring in steps 2–3 (how the fake provider reaches `SyncService` and the `FakeContainer`). Assertions never change.
  6. Assertions:
     - (a) **Registrations:** the cron jobs equal exactly this list, compared as `(job_id, kwargs)`. No catch-ups are enqueued on an empty history.
       - `("sync_1m", {"cron_expression": "*/1 * * * *", "second": 2, "misfire_grace_time": 120})`
       - `("sync_verify_cascade", {"cron_expression": "0 * * * *", "misfire_grace_time": 600})`
       - `("sync_backfill", {"hour": 3, "minute": 0, "misfire_grace_time": 3600})`
       - `("sync_integrity", {"hour": 4, "minute": 0, "misfire_grace_time": 3600})`
       - `("sync_repair", {"cron_expression": "0 */12 * * *", "misfire_grace_time": 1800})`
     - (b) **sync_1m:** after running it, `fake.calls == [("BTCUSDT:BINANCE", Interval.MINUTE_1, 100)]`, and the `bars` collection has 100 docs with `interval "1m"` and `source "rest_sync_1m"`. For every 5m, 15m, 1h, 4h and 1d doc with `source "cascade"`, O/H/L/C/V equal the aggregation of the stored 1m docs in its bucket: first open, max high, min low, last close and summed volume, computed in the test. The latest `job_history` doc for `sync_1m` has `status "completed"`, `total_inserted 100`, `total_fetched 100` and one `details` entry.
     - (c) **sync_1m again:** the latest `sync_1m` doc has `total_inserted 0`. `SyncStatusRepository.find_one("BTCUSDT:BINANCE", Interval.MINUTE_1).consecutive_empty_fetches == 1`.
     - (d) **sync_backfill:** clear `fake.calls` and run it. Then `fake.calls` equals `[("BTCUSDT:BINANCE", iv, 5000) for iv in (1m, 5m, 15m, 1h, 4h, 1d, 1w)]` in that order, and the latest `sync_backfill` doc is `completed`.
     - (e) **sync_repair:** delete one 1m bar inside the last hour with `BarRepository.delete_many_by_ids`, clear `fake.calls` and run it. `fake.calls` contains `("BTCUSDT:BINANCE", Interval.MINUTE_1, 5000)`, the deleted datetime exists again, and the latest `sync_repair` doc is `completed`.
     - (f) **sync_integrity:** the latest `sync_integrity` doc is `completed`.
     - (g) **sync_verify_cascade:** clear `fake.calls` and run it. `fake.calls == [("BTCUSDT:BINANCE", Interval.MINUTE_5, 12)]`, and the latest doc is `completed`.
     - (h) **sync_one response shape:** `SyncService.sync_one(SyncSymbolCommand(symbol="btcusdt:binance", interval=Interval.MINUTE_1, n_bars=10, source="rest_backfill")).model_dump().keys()` equals `{"symbol","interval","status","bars_synced","bars_fetched","filtered_existing","filtered_misaligned","total_bars","last_bar_at","message"}`, with `symbol == "BTCUSDT:BINANCE"` and `status == "completed"`.
- **Success criteria:** The current behaviour is pinned.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_sync_pipeline_characterization.py -q` exits 0 with `passed` and no `failed`.

<!-- Updated: Validation Session 1 - this test is the BrokerFactory characterization -->
### T2.5 DI resolution characterization (including `BrokerFactory`)
- **Goal:** Pin which concrete classes the container returns, so the policy wiring in Phase 03 and the DI merge in Phase 04 are checked. This is also the characterization of `BrokerFactory`.
- **Target files and symbols:** `tests/app_test/integration/app_factory.py` → new `build_test_container(settings) -> AsyncContainer`, which wraps today's provider list with `TestCoreProvider(settings)`. Also `tests/app_test/integration/test_di_resolution_characterization.py`.
- **Steps:**
  1. Add `build_test_container`, returning `make_async_container(TestCoreProvider(settings), PersistenceProvider(), InfrastructureProvider(), ExecutionProvider(), MarketDataProvider(), AppTradingServiceProvider(), BacktestWorkerProvider(), ServicesProvider())`.
  2. In the test, build the container and assert `isinstance` on these resolved types:
     - `IDataProvider` → `BinanceClient`
     - `IRealtimeQuoteProvider` → `BinanceWebSocketClient`
     - `BrokerFactory` → `BrokerFactory`; `get_available_types() == ["paper","okx"]`, `create("paper", {})` is a `PaperBroker`, `create("okx", {"api_key":"k","api_secret":"s","passphrase":"p"})` is an `OKXBroker`, and `create("x", {})` raises `ValueError`
     - each of `SyncService`, `BarAppService`, `QuoteAppService`, `WsSubscriptionManager`, `OrderAppService`, `PositionAppService`, `StrategyAppService`, `StrategyReconcileService`, `BacktestExecutionService`, `TrackedSymbolService`, `StrategyCommandService`, `StrategyQueryService`, `OrderPositionQueryService` and `JobScheduler` resolves to its own class.
  3. Call `await container.close()` in teardown.
- **Success criteria:** The graph is pinned.
- **Verify:** `.venv/Scripts/python.exe -m pytest tests/app_test/integration/test_di_resolution_characterization.py -q` exits 0 with `passed`.

<!-- Updated: Validation Session 1 - renumbered from T2.7 after the OKX test was dropped -->
### T2.6 Venue regression baseline
- **Goal:** One command whose pass count must stay constant through Phase 08.
- **Target files and symbols:** `plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt`
- **Steps:**
  1. `.venv/Scripts/python.exe -m pytest tests/core_test/infra/binance tests/core_test/infra/brokers tests/backtest_test/engine/test_paper_broker_limit_orders.py tests/backtest_test/engine/test_paper_broker_order_events.py -q 2>&1 | tail -n 1`
  2. Append the output line to `baseline-gate.txt` as `venue: <line>`.
- **Success criteria:** The venue pass count is recorded.
- **Verify:** `grep -c "^venue: .* passed" plans/261009-0858-exness-venue-lean-sync-refactor/reports/baseline-gate.txt` prints `1`.

<!-- Updated: Validation Session 1 - renumbered from T2.8; push also publishes the Phase 01 fixture commit -->
### T2.7 Phase gate and ship
- **Goal:** Tests and scripts are merged with a green gate. This push also publishes the Phase 01 fixture and journal commit.
- **Target files and symbols:** git
- **Steps:**
  1. Run the gate: `just test`, `uv run ruff check`, `uv run pyright` and `uv run lint-imports`.
  2. Stage the files with `git add scripts/code_metrics.py tests/scripts/test_code_metrics.py tests/app_test/integration plans/261009-0858-exness-venue-lean-sync-refactor` (the plan directory carries the Phase 01 and 02 reports; CI ignores `plans/**`).
  3. Commit with `git commit -m "test: pin sync jobs and di graph before refactor"`.
  4. Ask the user for approval, then `git switch master && git merge --ff-only test/sync-characterization && git push origin master`.
  5. Watch CI as in Phase 01 T1.7 step 6.
- **Success criteria:** Green.
- **Verify:**
  - `just test` exits 0 with `passed` and no `failed`.
  - `uv run ruff check` prints `All checks passed!`.
  - `uv run pyright` reports `0 errors`.
  - `uv run lint-imports` contains `Contracts: 7 kept, 0 broken.`.
  - `gh run watch <databaseId> --exit-status` exits 0, and `gh run view <databaseId> --log | grep "=== Verdict:" | grep -c ", 0 failures)"` prints a number ≥ 1.
  - `git rev-list --count origin/master..master` prints `0`.

## Verification
T2.3 (baseline numbers 794/661/315/63), T2.4–T2.5 (new characterization tests green on current code) and T2.7 (gate).

<!-- Updated: Validation Session 1 - stop-and-ask list for this phase -->
## Stop-and-ask
- The baseline gate in T2.1 is not green (unexplained test failure).
- Any step would edit OKX or Binance source code.

## Risks
- Time-dependent flakiness in T2.4. Mitigation: expected cascade values are computed from the stored 1m docs, not from hard-coded clock values.
- Testcontainers need Docker. Mitigation: `docker info` runs first in the gate.

## Rollback
This phase is test-only. `git revert` the merge commit.

## Failure Protocol
If any Verify step does not meet its stated pass condition, STOP this phase.
Do not improvise a fix, retry blindly, or reason around the failure.
Spawn the `kongming` subagent for next-step counsel and pass:
- the phase and task id,
- what you attempted (the steps you ran),
- the exact command and its full output,
- the pass condition it failed to meet.
Apply kongming's guidance, then re-run the Verify step.
If `kongming` cannot be spawned in this environment, STOP and report the same
failure evidence to the user. Never continue by self-reasoning.
