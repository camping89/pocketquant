=== FILE: plan.md ===
---
title: "Asset-class index futures (ES/NQ/YM) via TradingView"
description: "Generalize the 24/7-crypto pipeline into an asset-class + trading-calendar model, add provider routing and a TradingView adapter pair, and bring ES1!/NQ1!/YM1! into charts, paper trading and backtests."
status: pending
priority: P1
effort: 11d
branch: develop
tags: [market-data, futures, timezone, provider-routing, tradingview, calendar, backtest]
created: 2026-09-21
blockedBy: []
blocks: []
---

## Overview

PocketQuant is hardwired to one 24/7 crypto venue: DI binds exactly one REST provider
(`BinanceAdapter`) and one WS provider (`BinanceWebSocketAdapter`), and the sync,
cascade, integrity, freshness, annualization and paper-broker math all assume
continuous trading and price x quantity units. This plan makes the trading calendar
and the contract spec explicit parameters of the existing pipeline, makes provider
resolution a function of asset class plus provider id, and then adds CME/CBOT
continuous front-month index futures (`ES1!:CME_MINI`, `NQ1!:CME_MINI`,
`YM1!:CBOT_MINI`) through TradingView. No parallel futures pipeline is built.

**Phase numbering note.** The confirmed advice in
`plans/reports/advise-260921-2001-index-futures-data-provider.md` numbers its route
Phase 0 through Phase 6. This plan numbers the same seven steps 1 through 7:
advice Phase 0 = plan Phase 1, advice Phase 1 = plan Phase 2, and so on through
advice Phase 6 = plan Phase 7.

The order retires risk before it can hide: the UTC invariant and the calendar
refactor are both proven on the crypto path with the 24/7 calendar before a single
futures symbol exists, and provider routing ships with Binance as its only
registered provider before TradingView enters.

## Phases

| # | Phase | File | Effort | Depends on |
|---|-------|------|--------|-----------|
| 1 | UTC Invariant and Live Crypto Bug Fixes | [phase-01-utc-invariant-and-crypto-bugs.md](./phase-01-utc-invariant-and-crypto-bugs.md) | 1.5d | — |
| 2 | Trading Calendar Port and Asset-Class Domain Model | [phase-02-calendar-port-and-asset-class-model.md](./phase-02-calendar-port-and-asset-class-model.md) | 2d | 1 |
| 3 | Calendar-Threaded Pipeline on the 24/7 Calendar | [phase-03-calendar-threaded-pipeline.md](./phase-03-calendar-threaded-pipeline.md) | 2.5d | 2 |
| 4 | Provider Routing Adapters and Settings | [phase-04-provider-routing-adapters.md](./phase-04-provider-routing-adapters.md) | 1d | 2 |
| 5 | TradingView History Adapter, Seeding and Backfill | [phase-05-tradingview-history-and-backfill.md](./phase-05-tradingview-history-and-backfill.md) | 1.5d | 3, 4 |
| 6 | Polling Quote Adapter and Contract-Aware Trading Math | [phase-06-quote-adapter-and-contract-math.md](./phase-06-quote-adapter-and-contract-math.md) | 1.5d | 5 |
| 7 | UI, Docs and Success-Metric Run-Through | [phase-07-ui-docs-and-metrics.md](./phase-07-ui-docs-and-metrics.md) | 1d | 6 |

## Goals

- **G1** Fresh futures bars land within one cron cycle during CME session hours.
- **G2** A paper ES strategy runs a full session and reports USD PnL that matches
  points x multiplier x contracts.
- **G3** A 1h ES backtest reports dollar PnL and a Sharpe annualized on the CME
  session calendar, not on 365 x 24.
- **G4** Adding a provider is one adapter plus one config entry, with zero edits in
  `engine/` or `app/`.
- **G5** BTC/ETH/SOL behaviour, bar values, cascade output and metrics are unchanged.
- **G6** The app refuses to start on a non-UTC host, and the DST-boundary suite passes.

## Success criteria

- `uv run pytest` exits 0 with no test skipped that was not skipped before, and the
  existing crypto test count is unchanged or higher.
- `uv run ruff check .` exits 0 with the `DTZ` rules enabled.
- `uv run lint-imports` exits 0 (all 8 contracts).
- Every cron job reports the same `next_run_time` under `TZ=UTC`, `TZ=Asia/Saigon`
  and `TZ=America/Chicago`.
- Golden-file comparison: crypto bars, cascade output and performance metrics are
  byte-identical before and after the calendar refactor.
- Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
  `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across
  one full week including a weekend.
- `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0`.

## Non-goals

A real futures broker; multi-year 1m futures history (accepted trade-off — the cron
accumulates forward); Databento/IBKR adapters; tick-level fidelity beyond the
scraper; contract-roll modelling inside paper positions; redoing the margin
accounting shipped in plan `260628-2013`; any branching on the TradingView plan tier.

## Dependencies and risks

- **Hard ordering constraint (Phase 1).** `AsyncMongoClient(tz_aware=True)` and the
  `integrity_jobs.py:50` naive-`now` fix must land in the SAME commit. Flipping
  `tz_aware` alone makes the integrity check report every bar missing and triggers a
  full resync of every symbol.
- **New dependencies.** `pandas_market_calendars` (Phase 2, `core/infra` only) and
  the `tvDatafeed` scraper installed from git (Phase 5). Both sit behind interfaces
  so they are replaceable.
- **Credentials.** TradingView username/password/auth token live only in
  `../pocketquant-config/`. This repo carries field names and defaults, never values.

=== FILE: phase-01-utc-invariant-and-crypto-bugs.md ===
---
phase: 1
title: "UTC Invariant and Live Crypto Bug Fixes"
status: pending
priority: P1
effort: "1.5d"
dependencies: []
---

## Context

(Advice Phase 0.) Today the pipeline is UTC by convention, not by construction. The
APScheduler cron triggers actually run in the host timezone, the Mongo client returns
naive datetimes, `coerce_utc` silently attaches UTC to anything naive, and no deploy
file pins `TZ`. Two live crypto bugs share that root cause. All of it must be fixed
and asserted before a session-scheduled asset class exists, because after that a
timezone mistake produces bars that look right on the VPS and wrong everywhere else.

Nothing in this phase touches futures. Every change is provable on the crypto path.

## Tasks

### Task 1 — Pin `TZ=UTC` in every runtime surface

**Goal.** The process timezone is UTC in the container, in local dev, and in CI,
regardless of the host machine.

**Target files and symbols.**
- `deploy/Dockerfile` — the runtime-stage `ENV` block at lines 45-47.
- `deploy/compose.prod.yml` — the `app:` service (lines 32-60); add an
  `environment:` block.
- `justfile` — the `be:` recipe.
- `.github/workflows/cicd.yml` — the `tests:` job (line 18).

**Steps.**
1. In `deploy/Dockerfile`, add `TZ=UTC` to the existing `ENV` continuation block so
   it reads `ENV PATH="/app/.venv/bin:$PATH" \`, `PYTHONUNBUFFERED=1 \`,
   `PYTHONDONTWRITEBYTECODE=1 \`, `TZ=UTC`.
2. In `deploy/compose.prod.yml`, add to the `app:` service, as a sibling of
   `env_file:`, a block `environment:` with one entry `TZ: "UTC"`. Put it AFTER
   `env_file:` so it wins over any `TZ` key that appears in `.env`.
3. Do NOT touch `deploy/compose.local.yml`. That file defines only `mongodb` and
   `redis`; it has no `app` service, so there is nothing there to pin.
4. In `justfile`, change the `be:` recipe body to export the zone before uvicorn.
   On the `set windows-shell` split this repo uses, the portable form is a prefixed
   env assignment: `TZ=UTC {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41921`.
   Add a one-line comment above it saying the app asserts a UTC process timezone at
   startup.
5. In `.github/workflows/cicd.yml`, add to the `tests:` job a job-level
   `env:` block with `TZ: UTC`.

**Success criteria.** `grep -c 'TZ' deploy/Dockerfile deploy/compose.prod.yml justfile .github/workflows/cicd.yml` reports at least one hit per file.

**Verify.** `grep -l 'TZ=UTC\|TZ: "UTC"\|TZ: UTC' deploy/Dockerfile deploy/compose.prod.yml justfile .github/workflows/cicd.yml | wc -l` prints `4`.

---

### Task 2 — Pass `timezone=UTC` to both `CronTrigger` constructors

**Goal.** A registered cron job's `next_run_time` no longer depends on the host zone.

**Target files and symbols.**
- `src/pocketquant/core/infra/scheduling/scheduler.py` — `JobScheduler.add_cron_job`,
  the two `CronTrigger(...)` calls at lines 219 and 228. `UTC` is already imported at
  line 16.

**Steps.**
1. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call
   that starts at line 219 (the `cron_expression` branch).
2. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call
   that starts at line 228 (the `hour`/`minute`/`day_of_week` branch).
3. Above the first call, add one comment line explaining why: APScheduler applies the
   scheduler's declared timezone only when `add_job` builds the trigger from a string
   alias; a pre-built trigger with no `timezone=` falls back to `tzlocal` and pickles
   the host zone into the Mongo jobstore.

**Success criteria.** Both `CronTrigger(` call sites carry `timezone=UTC`.

**Verify.** `grep -c 'timezone=UTC' src/pocketquant/core/infra/scheduling/scheduler.py` prints `2`.

---

### Task 3 — Regression test for cron trigger timezone

**Goal.** A test fails if either `CronTrigger` ever loses its `timezone=`.

**Target files and symbols.**
- New file `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.
- Class under test: `pocketquant.core.infra.scheduling.scheduler.JobScheduler`.

**Steps.**
1. Write a test module with 3 tests. Use `monkeypatch.setenv("TZ", ...)` plus
   `time.tzset()` where the test needs a non-UTC host zone, and restore afterwards.
2. Test 1 `test_cron_expression_trigger_is_utc`: build a `CronTrigger` through the
   same code path by calling `JobScheduler.add_cron_job` on a scheduler whose
   `_scheduler` is a `unittest.mock.MagicMock`; read the trigger out of the recorded
   `add_job` call via `scheduler_mock.add_job.call_args.kwargs["trigger"]`; assert
   `str(trigger.timezone) == "UTC"`.
3. Test 2 `test_hour_minute_trigger_is_utc`: same, but call `add_cron_job` with
   `hour=3, minute=0` and no `cron_expression`.
4. Test 3 `test_next_run_time_identical_across_host_zones`: for each of
   `"UTC"`, `"Asia/Saigon"`, `"America/Chicago"`, set `TZ`, call `time.tzset()`,
   build the `hour=3` trigger the same way, and compute
   `trigger.get_next_fire_time(None, datetime(2026, 6, 1, 0, 0, tzinfo=UTC))`.
   Assert all three results are equal.
5. Restore the original `TZ` and call `time.tzset()` in a fixture teardown.

**Success criteria.** The three tests pass and fail if `timezone=UTC` is removed.

**Verify.** `uv run pytest tests/core_test/infra/scheduling/test_cron_trigger_timezone.py -q` exits 0 and prints `3 passed`.

---

### Task 4 — Startup assertion that the runtime timezone is UTC

**Goal.** The app refuses to start on a non-UTC host and logs one INFO line when it
is correct.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py` — add a new module-level function
  `assert_utc_runtime() -> None`.
- `src/pocketquant/app/main.py` — the `lifespan` function; call the new function
  inside the `try:` block, immediately before `init_backtest_tasks(app)` (line 59).
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py` — `register_sync_jobs`,
  after the five `add_cron_job` calls and before the catch-up sweep (around line 720).

**Steps.**
1. In `main_extensions.py`, add `import time` and `import tzlocal` at the top of the
   import block (tzlocal is already an installed transitive dependency of APScheduler).
2. Write `assert_utc_runtime()`:
   - compute `tz_name = str(tzlocal.get_localzone_name())`;
   - if `time.timezone != 0 or time.daylight or tz_name not in {"UTC", "Etc/UTC"}`,
     raise `RuntimeError` with the message
     `f"Process timezone must be UTC, got TZ={os.environ.get('TZ')!r} tzname={time.tzname!r} tzlocal={tz_name!r}. Set TZ=UTC."`;
   - otherwise `logger.info("runtime.timezone", tz=os.environ.get("TZ"), tzname=time.tzname, tzlocal=tz_name)`.
   - add `import os` if it is not already imported.
3. In `main.py`, add `assert_utc_runtime` to the existing import list from
   `pocketquant.app.main_extensions` (lines 9-26) and call it as the first statement
   inside the `try:` block of `lifespan`.
4. In `sync_jobs.register_sync_jobs`, after the last `add_cron_job` call, add a loop
   over `job_scheduler.get_jobs()` (add that accessor if `JobScheduler` does not
   already expose one — check first) that raises `RuntimeError` for any job whose
   `job.trigger` has a `timezone` attribute whose `str()` is not `"UTC"`. Keep the
   message naming the offending `job.id`.
5. Do NOT call `assert_utc_runtime()` from `tests/app_test/integration/app_factory.py`.
   That file defines its own lifespan and must stay host-agnostic.

**Success criteria.** The function raises on a non-UTC zone and logs once on UTC.

**Verify.** `uv run python -c "import os,time; os.environ['TZ']='Asia/Saigon'; time.tzset(); from pocketquant.app.main_extensions import assert_utc_runtime; 
try:
    assert_utc_runtime(); print('NO_RAISE')
except RuntimeError: print('RAISED')"` prints `RAISED`.

---

### Task 5 — Unit test for the startup assertion

**Goal.** The refusal-to-start behaviour is covered by a test, not only by a manual run.

**Target files and symbols.**
- New file `tests/core_test/unit/common/test_utc_runtime_guard.py`.
- Function under test: `pocketquant.app.main_extensions.assert_utc_runtime`.

**Steps.**
1. Write 2 tests. Use a fixture that records the original `TZ`, and in teardown
   restores it and calls `time.tzset()`.
2. `test_utc_host_passes`: set `TZ=UTC`, `time.tzset()`, call `assert_utc_runtime()`,
   assert no exception.
3. `test_non_utc_host_raises`: set `TZ=Asia/Saigon`, `time.tzset()`, assert
   `pytest.raises(RuntimeError, match="must be UTC")`.

**Success criteria.** Both tests pass.

**Verify.** `uv run pytest tests/core_test/unit/common/test_utc_runtime_guard.py -q` exits 0 and prints `2 passed`.

---

### Task 6 — Make the Mongo client tz-aware and fix the integrity naive site IN ONE COMMIT

**Goal.** Every datetime read from Mongo is tz-aware UTC, and the integrity check
still compares like with like.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/mongodb.py` — the `AsyncMongoClient(...)`
  construction at lines 44-49.
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` — line 50
  (`now = datetime.now(UTC).replace(tzinfo=None)`).
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` — line 24
  (the naive-epoch branch inside `get_bar_start`).
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py` — the comment at
  lines 54-55.

**Steps.**
1. THIS IS ONE COMMIT. Do not commit any sub-step alone. Flipping `tz_aware`
   without the `integrity_jobs.py` fix makes the integrity check report every bar
   missing and triggers a full resync of every symbol.
2. In `mongodb.py`, add `tz_aware=True,` and `tzinfo=UTC,` to the
   `AsyncMongoClient(...)` keyword arguments. Add `from datetime import UTC` to the
   imports if absent.
3. In `integrity_jobs.py`, change line 50 to `now = datetime.now(UTC)` (drop the
   `.replace(tzinfo=None)`). Delete the trailing comment fragment that explains the
   naivety if one exists on that line.
4. In `bar_builder_domain_service.py`, replace line 24
   (`epoch = datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`)
   with `epoch = datetime(1970, 1, 1, tzinfo=UTC)`, and add above `get_bar_start` a
   guard: `if timestamp.tzinfo is None: raise ValueError("get_bar_start requires a timezone-aware datetime")`.
5. In `bar_filters.py`, replace the comment at lines 54-55 with one line stating that
   the Mongo client is `tz_aware=True`, so raw projections already return UTC-aware
   datetimes; keep the `coerce_utc` calls as a cheap idempotent safety net.

**Success criteria.** The full suite still passes, and no naive datetime is produced
by `get_bar_start`.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py tests/core_test/unit/domain/bar/services/test_bar_builder.py tests/core_test/infra/persistence/test_bar_repository.py -q` exits 0.

---

### Task 7 — `Bar.datetime` becomes an aware UTC field; DTO and serialization cleanup

**Goal.** No naive datetime can enter the domain from an adapter, and every JSON
datetime is emitted through `to_utc_iso()`.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar.datetime` (line 35),
  `Bar.to_dict` (line 104).
- `src/pocketquant/engine/market_data/ohlcv_service.py` — line 66 and the
  `GetOHLCVQuery` dataclass (lines 14-24).
- `src/pocketquant/engine/backtest/backtest_command_service.py` — `RunBacktestCommand`
  (lines 22-38) and the `config` dict at lines 74-75.
- `src/pocketquant/engine/backtest/backtest_report_app_service.py` — lines 396-397.
- `src/pocketquant/engine/market_data/sync_status_service.py` — `_iso_z` (lines 72-73).

**Steps.**
1. In `entities.py`, add `from pydantic import field_validator` to the existing
   pydantic import, and add to `Bar` a validator:
   ```python
   @field_validator("datetime", "created_at", "updated_at", mode="after")
   @classmethod
   def _require_utc(cls, v: dt | None) -> dt | None:
       if v is None:
           return v
       if v.tzinfo is None:
           raise ValueError("Bar datetimes must be timezone-aware; adapters must emit UTC instants")
       return v.astimezone(UTC)
   ```
   Import `UTC` from `datetime`. `Bar.from_mongo` already runs `coerce_utc` before
   construction, so reads keep working.
2. In `entities.py`, change `Bar.to_dict` lines 104 and 111 to use
   `to_utc_iso(self.datetime)` and `to_utc_iso(self.updated_at)`; `to_utc_iso` is
   already importable from `pocketquant.core.common.time` (it is imported at line 8 —
   extend that import).
3. In `ohlcv_service.py` line 66, replace `bar.datetime.isoformat() if bar.datetime else None`
   with `to_utc_iso(bar.datetime)` and add the import.
4. In `ohlcv_service.py`, convert `GetOHLCVQuery` from a bare `@dataclass` into one
   whose `__post_init__` applies `coerce_utc` to `start_date` and `end_date`, so a
   naive ISO query string from the route becomes aware UTC in exactly one place.
5. In `backtest_command_service.py`, add to `RunBacktestCommand` a
   `@field_validator("start_date", "end_date", mode="after")` that returns
   `coerce_utc(v)`; replace the two `.isoformat()` calls at lines 74-75 with
   `to_utc_iso(...)`.
6. In `backtest_report_app_service.py`, replace the two `.isoformat()` calls at lines
   396-397 with `to_utc_iso(...)`.
7. In `sync_status_service.py`, replace the body of `_iso_z` with
   `return to_utc_iso(dt)` and delete the hand-rolled `.replace("+00:00", "Z")`.

**Success criteria.** No `.isoformat()` remains at the five named serialization sites,
and constructing `Bar(datetime=datetime(2026,1,1))` raises.

**Verify.** `uv run pytest tests/ -q -k "bar or ohlcv or backtest_command or sync_status"` exits 0.

---

### Task 8 — Fix the Binance weekly in-progress cutoff

**Goal.** From Thursday to Sunday, the latest persisted `1w` bar for a Binance symbol
is the previous Monday's closed bar, never a partial current week.

**Target files and symbols.**
- `src/pocketquant/core/infra/binance/binance_adapter.py` — lines 80-83
  (`now_ms`, `last_closed_open_ms`, `cutoff_dt`, `end_time_ms`).

**Steps.**
1. Import `get_bar_start` from
   `pocketquant.core.domain.bar.services.bar_builder_domain_service`.
2. Replace the epoch-floor computation with an alignment-derived one:
   ```python
   now = datetime.now(UTC)
   cutoff_dt = get_bar_start(now, interval)
   last_closed_open_ms = int(cutoff_dt.timestamp() * 1000)
   end_time_ms = last_closed_open_ms
   ```
   Delete the now-unused `now_ms` line.
3. Update the block comment above it: the cutoff is derived from the same alignment
   function the drop filter uses, so the two can never disagree; a plain
   `floor(now / 604800000)` lands on Thursday because the Unix epoch was a Thursday.

**Success criteria.** For `interval=WEEK_1` and any `now` between Thursday and
Sunday, `cutoff_dt` equals the Monday 00:00 UTC that opened the current week.

**Verify.** `uv run pytest tests/core_test/infra/binance/test_binance_client_in_progress_filter.py -q` exits 0.

---

### Task 9 — Regression test for the weekly cutoff

**Goal.** A Thursday-to-Sunday `now` never yields a cutoff inside the current week.

**Target files and symbols.**
- New file `tests/core_test/infra/binance/test_binance_weekly_cutoff.py`.

**Steps.**
1. Write 4 tests covering `now` on Thursday, Friday, Saturday and Sunday of the week
   opening Monday 2026-06-01 00:00 UTC (for example
   `datetime(2026, 6, 4, 12, 0, tzinfo=UTC)` for Thursday).
2. For each, call `get_bar_start(now, Interval.WEEK_1)` and assert the result equals
   `datetime(2026, 6, 1, 0, 0, tzinfo=UTC)`.
3. Add a fifth assertion inside each test that the result is strictly less than or
   equal to `now` and that `now - result < timedelta(days=7)`.

**Success criteria.** All 4 tests pass.

**Verify.** `uv run pytest tests/core_test/infra/binance/test_binance_weekly_cutoff.py -q` exits 0 and prints `4 passed`.

---

### Task 10 — Replace `date.today()` in the backtest strategy loader

**Goal.** No host-local calendar date is used anywhere in `src/`.

**Target files and symbols.**
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py` — line 37
  (`today = date.today()`).

**Steps.**
1. Change line 37 to `today = datetime.now(UTC).date()`.
2. Ensure `UTC` and `datetime` are imported in that module (`datetime` already is;
   add `UTC` to the same import).
3. If the `date` import becomes unused, remove it; `date` is still used in the
   signature annotations at lines 21 and 46-47, so check before deleting.

**Success criteria.** `date.today()` no longer appears in `src/`.

**Verify.** `grep -rn "date.today()" src/ | wc -l` prints `0`.

---

### Task 11 — Enable ruff `DTZ` and clear every finding

**Goal.** `uv run ruff check .` passes with the `DTZ` rule family enabled.

**Target files and symbols.**
- `pyproject.toml` — `[tool.ruff.lint] select` at the line reading
  `select = ["E", "F", "I", "N", "W", "UP", "TID"]`.
- 3 findings in `src/` and 31 in `tests/` + `scripts/` (measured on 2026-09-21).

**Steps.**
1. Change the `select` list to `["E", "F", "I", "N", "W", "UP", "TID", "DTZ"]`.
2. Run `uv run ruff check --select DTZ --output-format concise . ` and work the list.
3. `src/` findings and their fixes:
   - `core/domain/bar/services/bar_builder_domain_service.py:24` — already removed in
     Task 6.
   - `engine/backtest/backtest_strategy_loader.py:37` — already fixed in Task 10.
   - `engine/market_data/app_services/cascade_aggregator.py:81` — `DTZ901`
     `datetime.min` used as a sort key. Replace
     `sorted(bars, key=lambda b: b.datetime or datetime.min)` with
     `sorted(bars, key=lambda b: b.datetime or datetime.min.replace(tzinfo=UTC))`.
     This also removes a real crash risk: comparing a naive `datetime.min` against
     aware bar datetimes raises `TypeError`.
4. `tests/` and `scripts/` findings: all are `DTZ001` (naive `datetime(...)`
   constructor) plus 2 `DTZ901`. Add `tzinfo=UTC` to each constructor. The files and
   counts are: `tests/backtest_test/engine/test_backtest_app_service_persistence.py` (4),
   `scripts/backfill/test_binance_bars.py` (3),
   `tests/scripts/rubric/test_reconciliation.py` (2),
   `tests/backtest_test/engine/test_result_collector_mark_to_market.py` (2),
   `tests/backtest_test/engine/test_hitnrun2_backtest.py` (2),
   `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py` (2),
   `tests/backtest_test/engine/test_engulfing_backtest.py` (2),
   `tests/app_test/market_data/test_cascade_aggregator.py` (2),
   `tests/scripts/rubric/test_trade_path_analysis.py` (1),
   `tests/engine_test/test_live_metrics_query_service.py` (1),
   `tests/core_test/infra/persistence/test_trade_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_trade_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_order_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py` (1),
   `tests/backtest_test/test_backtest_stats_service.py` (1),
   `tests/backtest_test/domain/test_trade_stats_calculator.py` (1).
5. EXCEPTION: `tests/core_test/unit/domain/test_mongo_datetime_normalization.py`
   has 4 `DTZ001` findings at lines 17, 18, 35 and 36. Those naive values ARE the
   subject under test. Append `  # noqa: DTZ001 — naive input is the case under test`
   to each of those four lines instead of adding `tzinfo`.
6. Re-run the full test suite after the edits — adding `tzinfo=UTC` to fixture values
   changes comparisons in tests that mix aware and naive datetimes; fix those tests,
   never the production code.

**Success criteria.** Ruff reports zero DTZ findings across the repo, and the suite
is green.

**Verify.** `uv run ruff check . ` exits 0 and prints `All checks passed!`.

---

### Task 12 — CI timezone matrix

**Goal.** The unit suite is run under a non-UTC host zone on every push, which is the
check that would have caught the `CronTrigger` bug.

**Target files and symbols.**
- `.github/workflows/cicd.yml` — the `tests:` job (line 18).
- `justfile` — new recipe `test-tz`.

**Steps.**
1. In `cicd.yml`, add to the `tests:` job a `strategy:` block:
   ```yaml
   strategy:
     fail-fast: false
     matrix:
       tz: ["UTC", "Asia/Saigon", "America/Chicago"]
   ```
   and change the job-level `env:` added in Task 1 to `TZ: ${{ matrix.tz }}`.
2. Leave `build-app`'s `needs: [tests]` as is; GitHub waits for all matrix legs.
3. Add to `justfile`:
   ```
   # Run the unit suite under three host timezones — catches host-zone leakage.
   test-tz:
       TZ=UTC {{python}} -m pytest -q
       TZ=Asia/Saigon {{python}} -m pytest -q
       TZ=America/Chicago {{python}} -m pytest -q
   ```

**Success criteria.** The suite passes under all three zones locally.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/ -q` exits 0.

---

### Task 13 — Phase gate: prove the invariant end to end

**Goal.** Phase 1 is provably complete before Phase 2 starts.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite under the three zones.
2. Run ruff, pyright and the import contracts.
3. Record the outputs in the phase completion note.

**Success criteria.** All four commands exit 0.

**Verify.** `uv run pytest tests/ -q && uv run ruff check . && uv run lint-imports && TZ=Asia/Saigon uv run pytest tests/ -q` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `tz_aware=True` lands without the integrity fix | Medium | High — full resync of every symbol against Binance rate limits | Task 6 is explicitly one commit; the Verify step exercises the integrity path |
| `Bar.datetime` validator rejects a live adapter payload | Low | High — sync stops | `binance_mappers.py:57-58,90-91` already builds with `tz=UTC`; the suite covers it |
| Enabling `DTZ` breaks a fixture-heavy test | High | Low | Task 11 step 6 re-runs the suite and fixes tests, never production code |
| `TZ=UTC` in `justfile` breaks a Windows dev shell | Low | Low | Revert the `be:` recipe line; the container and CI pins are independent |

**Rollback.** Every task is an isolated commit except Task 6. Reverting Task 6 means
reverting `mongodb.py`, `integrity_jobs.py` and `bar_builder_domain_service.py`
together. Reverting Task 4 alone restores the previous startup behaviour.

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

=== FILE: phase-02-calendar-port-and-asset-class-model.md ===
---
phase: 2
title: "Trading Calendar Port and Asset-Class Domain Model"
status: pending
priority: P1
effort: "2d"
dependencies: [1]
---

## Context

(Advice Phase 1.) This phase introduces the vocabulary the rest of the plan depends
on: an `AssetClass` enum, a `ContractSpec` value object, and an `ITradingCalendarPort`
with two implementations — `Continuous24x7Calendar` (crypto, reproduces today's
numbers exactly) and a CME Globex equity calendar wrapping `pandas_market_calendars`.
Nothing is wired into the pipeline yet; that is Phase 3. The symbol record gains
`asset_class`, `calendar_id` and `contract_spec`, and the composite regex is widened
to accept `!`.

The trading schedule is stored alongside the asset class as a `calendar_id`
REFERENCE on the symbol record. The schedule RULES stay in code behind the port,
because CME holidays and early closes change yearly and a Mongo copy would have to be
hand-synchronised with CME notices.

## Tasks

### Task 1 — Add `pandas_market_calendars` as a dependency

**Goal.** The CME calendar library is installed and locked.

**Target files and symbols.**
- `pyproject.toml` — the `[project] dependencies` list (currently ends with `"dishka>=1.9.1",`).

**Steps.**
1. Add `"pandas-market-calendars>=5.4.0",` to the `dependencies` list, in the same
   block as `pandas`.
2. Run `uv sync`.
3. Do NOT add it to `dev` — it is a runtime dependency of `core/infra`.

**Success criteria.** The module imports and exposes the CME Globex equity alias.

**Verify.** `uv run python -c "import pandas_market_calendars as m; c=m.get_calendar('CME Globex Equity'); print(type(c).__name__, c.tz)"` prints `CMEGlobexEquitiesExchangeCalendar America/Chicago`.

---

### Task 2 — Add the `AssetClass` enum

**Goal.** A closed set of asset classes exists in the domain.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py` — add `class AssetClass(str, Enum)`
  below the existing `Interval` enum.

**Steps.**
1. Add:
   ```python
   class AssetClass(str, Enum):
       CRYPTO_SPOT = "crypto_spot"
       CRYPTO_PERP = "crypto_perp"
       INDEX_FUTURE = "index_future"
   ```
2. Leave `Interval.periods_per_year` and `Interval.periods_per_year_for` in place for
   now; Phase 3 Task 9 moves ownership of annualization onto the calendar.

**Success criteria.** The enum imports and has exactly three members.

**Verify.** `uv run python -c "from pocketquant.core.domain.shared.enums import AssetClass; print(len(list(AssetClass)), AssetClass.INDEX_FUTURE.value)"` prints `3 index_future`.

---

### Task 3 — Add the `ContractSpec` value object and the asset-class defaults

**Goal.** Contract units are data, not a hardcoded assumption of `price * quantity`.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/symbol/value_objects.py`.
- Symbols: `ContractSpec`, `LINEAR_SPEC`, `DEFAULT_CALENDAR_BY_ASSET_CLASS`,
  `DEFAULT_SPEC_BY_ASSET_CLASS`, `CALENDAR_CRYPTO_24_7`, `CALENDAR_CME_GLOBEX_EQUITY`.

**Steps.**
1. Create the file with a frozen dataclass:
   ```python
   @dataclass(frozen=True)
   class ContractSpec:
       multiplier: float = 1.0          # account currency per 1.0 of price move, per contract
       tick_size: float = 0.0           # 0.0 = no tick rounding
       lot_step: float | None = None    # None = fractional size allowed; 1.0 = integer contracts
       currency: str = "USD"
       commission_per_contract: float | None = None  # None = use the percentage model
   ```
2. Add `to_mongo()` returning a plain dict of the five fields and a
   `from_mongo(doc: dict | None) -> ContractSpec` classmethod that returns
   `LINEAR_SPEC` when the document is missing or empty.
3. Define the calendar-id constants as module-level strings:
   `CALENDAR_CRYPTO_24_7 = "CRYPTO_24_7"` and
   `CALENDAR_CME_GLOBEX_EQUITY = "CME_GLOBEX_EQUITY"`.
4. Define `LINEAR_SPEC = ContractSpec()`.
5. Define the two default maps keyed by `AssetClass`:
   - `DEFAULT_CALENDAR_BY_ASSET_CLASS`: both crypto members map to
     `CALENDAR_CRYPTO_24_7`; `INDEX_FUTURE` maps to `CALENDAR_CME_GLOBEX_EQUITY`.
   - `DEFAULT_SPEC_BY_ASSET_CLASS`: both crypto members map to `LINEAR_SPEC`;
     `INDEX_FUTURE` maps to `ContractSpec(multiplier=1.0, tick_size=0.25, lot_step=1.0, currency="USD")`
     — the per-symbol multipliers are set at seed time, not here.
6. Export all of the above from `src/pocketquant/core/domain/symbol/__init__.py`.

**Success criteria.** The value object is importable, frozen, and round-trips through
`to_mongo`/`from_mongo`.

**Verify.** `uv run python -c "from pocketquant.core.domain.symbol import ContractSpec; s=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0); print(ContractSpec.from_mongo(s.to_mongo()) == s)"` prints `True`.

---

### Task 4 — Define `ITradingCalendarPort`

**Goal.** One interface that every session-dependent computation takes as a parameter.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/trading_calendar_port.py`.
- Symbol: `ITradingCalendarPort`.

**Steps.**
1. Create an `ABC` named `ITradingCalendarPort` with these members, all abstract
   except `calendar_id` which is an abstract property:
   ```python
   @property
   def calendar_id(self) -> str: ...
   @property
   def tz(self) -> ZoneInfo: ...
   def is_open(self, instant: datetime) -> bool: ...
   def session_date(self, instant: datetime) -> date: ...
   def session_open(self, session_date: date) -> datetime: ...     # UTC instant
   def session_close(self, session_date: date) -> datetime: ...    # UTC instant
   def previous_close(self, instant: datetime) -> datetime: ...    # UTC instant
   def sessions(self, start: datetime, end: datetime) -> list[date]: ...
   def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]: ...
   def bar_start(self, instant: datetime, interval: Interval) -> datetime: ...
   def periods_per_year(self, interval: Interval) -> float: ...
   ```
2. Document in the class docstring: every `datetime` crossing this interface is a
   tz-aware UTC instant; `session_date` is the exchange-calendar day key; session
   boundaries are computed with `zoneinfo` and converted per instant, never with a
   fixed offset.
3. Add to every method docstring the exact contract:
   - `is_open(instant)` — True when `instant` falls inside a trading session.
   - `previous_close(instant)` — the most recent instant at which a bar could have
     closed. For a 24/7 calendar this is `instant` itself.
   - `trading_minutes(start, end)` — every minute-open instant in `[start, end)` that
     is a trading minute, ascending.
   - `bar_start(instant, interval)` — the open instant of the bar of `interval` that
     contains `instant`.
4. This file must not import anything from `pocketquant.core.infra` — the domain
   purity AST test at `tests/core_test/unit/domain/test_domain_purity.py` forbids it.

**Success criteria.** The port imports cleanly and the domain purity test still passes.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_domain_purity.py -q` exits 0.

---

### Task 5 — Implement `Continuous24x7Calendar`

**Goal.** Crypto's schedule is an ordinary calendar implementation, and it reproduces
today's numbers exactly.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/continuous_24x7_calendar.py`.
- Symbol: `Continuous24x7Calendar`.

**Steps.**
1. Implement `ITradingCalendarPort` with `calendar_id` returning
   `CALENDAR_CRYPTO_24_7` and `tz` returning `ZoneInfo("UTC")`.
2. `is_open` returns `True` always.
3. `session_date(instant)` returns `instant.astimezone(UTC).date()`.
4. `session_open(d)` returns `datetime(d.year, d.month, d.day, tzinfo=UTC)`;
   `session_close(d)` returns `session_open(d) + timedelta(days=1)`.
5. `previous_close(instant)` returns `instant` unchanged — this is what keeps
   `now - last_bar` freshness arithmetic byte-identical for crypto.
6. `sessions(start, end)` returns every calendar date in `[start.date(), end.date()]`.
7. `trading_minutes(start, end)` returns the dense grid
   `[start + i*timedelta(minutes=1) for i in range(int((end - start) // timedelta(minutes=1)))]`
   — exactly what `integrity_jobs.check_integrity` builds today.
8. `bar_start(instant, interval)` DELEGATES to the existing
   `pocketquant.core.domain.bar.services.bar_builder_domain_service.get_bar_start`.
   Do not re-implement the logic; this is the DRY guarantee that crypto alignment
   cannot drift.
9. `periods_per_year(interval)` returns the value from the existing
   `_PERIODS_PER_YEAR` map in `core/domain/shared/enums.py`. Import the module-private
   map directly, or expose it via a module-level function in `enums.py` and call that.

**Success criteria.** Every method matches today's behaviour for crypto.

**Verify.** `uv run python -c "
from datetime import UTC, datetime
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
c = Continuous24x7Calendar()
print(c.periods_per_year(Interval.MINUTE_1), c.bar_start(datetime(2026,6,3,14,37,tzinfo=UTC), Interval.WEEK_1).isoformat())"` prints `525600 2026-06-01T00:00:00+00:00`.

---

### Task 6 — Implement the CME Globex equity calendar adapter

**Goal.** ES/NQ/YM session boundaries are correct, including DST, holidays and early
closes, and every boundary is a UTC instant.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/calendars/` with `__init__.py`.
- New file `src/pocketquant/core/infra/calendars/cme_globex_calendar_adapter.py`.
- Symbol: `CmeGlobexCalendarAdapter`.

**Steps.**
1. Implement `ITradingCalendarPort`. `calendar_id` returns
   `CALENDAR_CME_GLOBEX_EQUITY`; `tz` returns `ZoneInfo("America/Chicago")`.
2. In `__init__`, hold `self._cal = pandas_market_calendars.get_calendar("CME Globex Equity")`.
3. Implement a private `_schedule(start_date, end_date)` that calls
   `self._cal.schedule(start_date=..., end_date=...)` and returns the resulting
   DataFrame. Wrap it in `functools.lru_cache(maxsize=64)` keyed on the two dates so
   repeated cron calls do not rebuild the schedule.
4. `session_open(d)` returns the `market_open` value for session date `d`, converted
   with `.tz_convert("UTC").to_pydatetime()`. `session_close(d)` does the same with
   `market_close`. Both raise `KeyError` with a clear message when `d` is not a
   trading session.
5. `is_open(instant)` returns True when `instant` lies in
   `[session_open(d), session_close(d))` for the session date derived from `instant`.
   Use `self._cal.open_at_time(schedule, instant)` if it is available; otherwise do
   the interval test yourself against the schedule rows covering
   `instant.date() - 1 day` through `instant.date() + 1 day`.
6. `session_date(instant)` returns the session date `d` whose
   `[session_open(d), session_close(d))` window contains `instant`. When the instant
   falls in the daily maintenance halt, return the session date of the NEXT session
   open — document that choice in the docstring.
7. `previous_close(instant)` returns `min(instant, session_close(d))` for the session
   containing or most recently preceding `instant`.
8. `sessions(start, end)` returns the schedule index dates as `date` objects.
9. `trading_minutes(start, end)` returns, for each session in range, every minute-open
   instant in `[max(start, session_open), min(end, session_close))`.
10. `bar_start(instant, interval)`:
    - `DAY_1` → `session_open(session_date(instant))`.
    - `WEEK_1` → `session_open` of the first session of the ISO week containing
      `session_date(instant)`.
    - intraday → `session_open(d) + k * interval_seconds` where `k` is the largest
      integer keeping the result `<= instant`, clipped to the session. Use
      `INTERVAL_SECONDS` from `core/domain/shared/value_objects.py`.
11. `periods_per_year(interval)` is computed deterministically from a FIXED reference
    window, the calendar year 2025-01-01 to 2025-12-31, and cached with
    `functools.lru_cache`:
    - `DAY_1` → number of sessions in the window.
    - `WEEK_1` → sessions / 5.
    - intraday → total trading minutes in the window / (interval seconds / 60).
    Document that the window is fixed so the value is reproducible across runs.
12. Never construct a session boundary by adding a fixed offset. Always build the
    exchange-local wall time and call `.astimezone(UTC)`, or let the library's
    tz-aware timestamps do it.

**Success criteria.** All port methods return tz-aware UTC instants and the DST cases
below hold.

**Verify.** `uv run python -c "
from datetime import date
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
c = CmeGlobexCalendarAdapter()
print(c.session_open(date(2026,3,9)).isoformat(), c.session_open(date(2026,11,2)).isoformat())"` prints `2026-03-08T22:00:00+00:00 2026-11-01T23:00:00+00:00`.

---

### Task 7 — Calendar test suite including the DST and holiday cases

**Goal.** The six session edge cases the audit named are covered by tests.

**Target files and symbols.**
- New file `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py`.
- New file `tests/core_test/infra/calendars/test_cme_globex_calendar.py`.

**Steps.**
1. In the 24/7 test module, write 6 tests:
   `test_is_open_always_true`, `test_session_date_is_utc_date`,
   `test_bar_start_matches_get_bar_start` (parametrized over all 7 intervals),
   `test_previous_close_is_identity`, `test_trading_minutes_is_dense`,
   `test_periods_per_year_matches_interval_enum` (parametrized over all 7 intervals,
   asserting equality with `Interval.periods_per_year`).
2. In the CME test module, write 8 tests:
   - `test_spring_forward_session_open`: `session_open(date(2026,3,9))` equals
     `datetime(2026,3,8,22,0,tzinfo=UTC)`.
   - `test_fall_back_session_open`: `session_open(date(2026,11,2))` equals
     `datetime(2026,11,1,23,0,tzinfo=UTC)`.
   - `test_sunday_reopen`: `is_open` is False at Sunday 2026-06-07 20:00 UTC and True
     at Sunday 2026-06-07 23:00 UTC (17:00 CT = 22:00 UTC in June — assert against
     `session_open(date(2026,6,8))` rather than a literal so the test states intent).
   - `test_weekend_closed`: `is_open` is False for Saturday 2026-06-06 12:00 UTC.
   - `test_daily_halt_closed`: `is_open` is False 30 minutes after
     `session_close(date(2026,6,10))`.
   - `test_holiday_is_not_a_session`: `date(2026,12,25)` is absent from
     `sessions(datetime(2026,12,20,tzinfo=UTC), datetime(2026,12,31,tzinfo=UTC))`.
   - `test_juneteenth_early_close`: for `date(2026,6,19)`, assert
     `session_close(d) - session_open(d) < timedelta(hours=23)`.
   - `test_session_spans_utc_midnight`: for `date(2026,6,10)`, assert
     `session_open(d).date() != session_close(d).date()`.
3. Every test must construct expectations with `tzinfo=UTC`, never naive.

**Success criteria.** 14 tests pass, and they pass under a non-UTC host zone too.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py tests/core_test/infra/calendars/test_cme_globex_calendar.py -q` exits 0 and prints `14 passed`.

---

### Task 8 — Build the `TradingCalendarFactory` and the cached symbol lookup

**Goal.** Any caller holding a composite symbol string can obtain that symbol's
calendar without doing a database read per bar.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/repositories/symbol_repository.py` — add
  `find_by_symbol(composite: str) -> Symbol | None`.
- New file `src/pocketquant/core/infra/persistence/symbol_lookup_helper.py` —
  `SymbolLookupHelper`.
- New file `src/pocketquant/core/infra/calendars/trading_calendar_factory.py` —
  `TradingCalendarFactory`.

**Steps.**
1. In `SymbolRepository`, add:
   ```python
   async def find_by_symbol(self, symbol: str) -> Symbol | None:
       doc = await self._collection().find_one({"symbol": symbol.upper()})
       return Symbol.from_mongo(doc) if doc else None
   ```
2. Create `SymbolLookupHelper` holding a `SymbolRepository` and a module-level
   `TTLCache(maxsize=500, ttl=60)` from `cachetools` (already a dependency). Expose
   `async def get(self, composite: str) -> Symbol | None` that checks the cache first,
   reads through on a miss, and caches both hits and misses. Log nothing above DEBUG —
   this is a per-bar hot path.
3. Create `TradingCalendarFactory` holding a `SymbolLookupHelper`. Instantiate one
   `Continuous24x7Calendar` and one `CmeGlobexCalendarAdapter` in `__init__` and store
   them in a `dict[str, ITradingCalendarPort]` keyed by `calendar_id`.
4. Expose `def get(self, calendar_id: str | None) -> ITradingCalendarPort` returning
   the 24/7 calendar when `calendar_id` is None or unknown, and logging one WARNING
   naming the unknown id (one-shot per id, not per call — guard with a `set`).
5. Expose `async def for_symbol(self, composite: str) -> ITradingCalendarPort` that
   looks the symbol up and returns `self.get(symbol.calendar_id if symbol else None)`.
6. Register both in DI as `Scope.APP` in
   `src/pocketquant/app/di/persistence.py` (for `SymbolLookupHelper`) and
   `src/pocketquant/app/di/infrastructure.py` (for `TradingCalendarFactory`). Read
   those files first and follow the existing `provide(...)` style.

**Success criteria.** `TradingCalendarFactory.get("CRYPTO_24_7")` and
`get("CME_GLOBEX_EQUITY")` return the right implementations, and an unknown id falls
back to 24/7.

**Verify.** `uv run pytest tests/app_test/integration/test_app_standalone_runtime.py -q` exits 0 (proves DI still resolves the whole graph).

---

### Task 9 — Extend `Symbol` with `asset_class`, `calendar_id` and `contract_spec`

**Goal.** The asset class and its schedule reference are persisted on the symbol
record, replacing the free-string `asset_type`.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py` — `Symbol` fields (line 38),
  `Symbol.create` (lines 62-70), `to_mongo` (lines 78-87), `from_mongo` (lines 89-99),
  `COMPOSITE_SYMBOL_RE` (line 19), `COMPOSITE_SYMBOL_PATTERN` (line 24).
- `src/pocketquant/engine/market_data/symbols_service.py` — line 20.
- `web/src/types/market-data.ts` — `SymbolInfo.asset_type` (line 26).

**Steps.**
1. Replace the field `asset_type: str | None = None` with three fields:
   ```python
   asset_class: AssetClass = AssetClass.CRYPTO_SPOT
   calendar_id: str = CALENDAR_CRYPTO_24_7
   contract_spec: ContractSpec = LINEAR_SPEC
   ```
   Add `model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)`
   — `ContractSpec` is a frozen dataclass, which pydantic v2 handles natively.
2. Change `Symbol.create` to accept `asset_class`, `calendar_id` and `contract_spec`
   keyword arguments, all defaulting to the values above, and drop `asset_type`.
3. Update `to_mongo` to write `asset_class` (the `.value`), `calendar_id`, and
   `contract_spec` (via `self.contract_spec.to_mongo()`); remove the `asset_type` key.
4. Update `from_mongo` to read the three new keys, with
   `AssetClass(doc.get("asset_class", "crypto_spot"))`,
   `doc.get("calendar_id", CALENDAR_CRYPTO_24_7)` and
   `ContractSpec.from_mongo(doc.get("contract_spec"))`.
5. Widen BOTH regexes to accept `!`:
   - `COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9_!-]+:[A-Z0-9_-]+$")`
   - `COMPOSITE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._!-]{1,32}:[A-Z0-9._-]{1,32}$")`
   Both are required: `COMPOSITE_SYMBOL_RE` gates the `Symbol` entity validator,
   while `COMPOSITE_SYMBOL_PATTERN` gates the HTTP path validator
   (`app/common/symbol_validation.py:23`) and the two tracked-symbol command
   validators (`engine/market_data/tracked_symbols_service.py:35` and
   `engine/market_data/tracked_symbols_backfill.py:65`). Missing either one blocks
   the Phase 5 seeding.
   Place `!` before the closing `-` inside the character class so it is not read as a
   range.
6. In `symbols_service.py` line 20, replace `"asset_type": s.asset_type,` with
   `"asset_class": s.asset_class.value,` and add `"calendar_id": s.calendar_id,`.
7. In `web/src/types/market-data.ts`, rename the `SymbolInfo` field `asset_type` to
   `asset_class` and add `calendar_id: string`. Grep the SPA for other `asset_type`
   uses — on 2026-09-21 that type declaration was the only one.

**Success criteria.** `ES1!:CME_MINI` validates through both regexes, and a symbol
round-trips through `to_mongo`/`from_mongo` with its spec intact.

**Verify.** `uv run python -c "
from pocketquant.core.domain.symbol import Symbol, ContractSpec
from pocketquant.core.domain.shared.enums import AssetClass
s = Symbol.create('ES1!:CME_MINI', asset_class=AssetClass.INDEX_FUTURE, calendar_id='CME_GLOBEX_EQUITY', contract_spec=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0))
print(Symbol.from_mongo(s.to_mongo()).contract_spec.multiplier)"` prints `50.0`.

---

### Task 10 — Stop the sync pipeline from clobbering symbol metadata

**Goal.** A normal sync run never overwrites a seeded symbol's `asset_class`,
`calendar_id` or `contract_spec`.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/repositories/symbol_repository.py` —
  `upsert` (lines 15-32); add `touch`.
- `src/pocketquant/engine/market_data/sync_service.py` — `SyncService._persist_bars`
  (lines 149-154), which today calls `self._symbol_repo.upsert(Symbol.create(symbol=symbol))`.

**Steps.**
1. Read `SymbolRepository.upsert`: it sends `{"$set": doc}` with the whole document.
   `Symbol.create(symbol=symbol)` produces DEFAULT `asset_class`/`calendar_id`/
   `contract_spec`, so after this change every 1m sync of `ES1!:CME_MINI` would
   silently reset it to crypto. This must be fixed in this phase, before any futures
   symbol is seeded.
2. Add to `SymbolRepository`:
   ```python
   async def touch(self, symbol: str) -> None:
       """Ensure a symbol document exists without overwriting its metadata.

       The sync pipeline calls this on every run; a full $set would reset
       asset_class / calendar_id / contract_spec to their crypto defaults.
       """
       doc = Symbol.create(symbol=symbol).to_mongo()
       symbol_value = doc.pop("symbol")
       await self._collection().update_one(
           {"symbol": symbol_value},
           {"$setOnInsert": {**doc, "symbol": symbol_value}},
           upsert=True,
       )
   ```
3. In `SyncService._persist_bars`, replace
   `await self._symbol_repo.upsert(Symbol.create(symbol=symbol))` with
   `await self._symbol_repo.touch(symbol)`. Remove the now-unused `Symbol` import if
   nothing else in the module uses it.
4. Leave `upsert` in place — the migration and seeding scripts use it deliberately.

**Success criteria.** After a sync of an existing futures symbol, its `asset_class` in
Mongo is still `index_future`.

**Verify.** `uv run pytest tests/engine_test/market_data/test_sync_service.py tests/core_test/infra/persistence/test_bar_repository.py -q` exits 0.

---

### Task 11 — Add `session_date` and `calendar_id` to daily and weekly bars

**Goal.** Consumers get a stable session-day key while `datetime` keeps moving with DST.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar` fields, `to_mongo`, `from_mongo`.
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` —
  `ensure_indexes` (lines 284-290).

**Steps.**
1. Add to `Bar` two optional fields: `session_date: date | None = None` and
   `calendar_id: str | None = None`. Import `date` from `datetime`.
2. Write both in `to_mongo` and read both in `from_mongo`. `session_date` is stored as
   an ISO string (`"2026-06-10"`), not as a BSON date, so it cannot be mistaken for an
   instant; convert with `date.fromisoformat` on read.
3. In `BarRepository.ensure_indexes`, add a second, sparse index:
   ```python
   await collection.create_index(
       [("symbol", 1), ("interval", 1), ("session_date", 1)],
       name="ix_ohlcv_symbol_interval_session_date",
       sparse=True,
   )
   ```
   Keep the existing unique `(symbol, interval, datetime)` index exactly as it is.
4. Do NOT populate the fields yet — Phase 3 Task 6 populates them at the cascade and
   sync write path. This task only makes the shape available.

**Success criteria.** The new index exists and existing bars still load.

**Verify.** `uv run pytest tests/core_test/infra/persistence/test_bar_repository.py tests/core_test/unit/domain/bar/test_entities_audit_fields.py -q` exits 0.

---

### Task 12 — Migration script: stamp existing symbols

**Goal.** Every symbol already in Mongo carries an explicit asset class, calendar id
and contract spec.

**Target files and symbols.**
- New file `scripts/migrate_symbol_asset_class.py`.
- Collection: `symbols`.

**Steps.**
1. Follow the conventions in `scripts/README.md`: read `MONGODB_URL` from the
   environment, never from a CLI flag; default to dry-run; require `--apply` to write.
2. The script connects with `AsyncMongoClient`, then for every document in `symbols`
   that has no `asset_class` field, issues
   `{"$set": {"asset_class": "crypto_spot", "calendar_id": "CRYPTO_24_7", "contract_spec": {"multiplier": 1.0, "tick_size": 0.0, "lot_step": None, "currency": "USD", "commission_per_contract": None}}, "$unset": {"asset_type": ""}}`.
3. Print the matched and modified counts. Exit non-zero if any write fails.
4. Add a module docstring with the usage line
   `uv run python scripts/migrate_symbol_asset_class.py [--apply]`.
5. Add a one-line entry for the script in `scripts/README.md` under the existing list.

**Success criteria.** A dry run reports the count of documents that would change and
writes nothing.

**Verify.** `uv run python scripts/migrate_symbol_asset_class.py --help` exits 0 and its output contains `--apply`.

---

### Task 13 — Phase gate

**Goal.** Phase 2 is complete and the crypto path is untouched.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, ruff, pyright and the import contracts.
2. Confirm `pandas_market_calendars` is imported only from
   `src/pocketquant/core/infra/calendars/` — grep for it across `src/`.

**Success criteria.** All checks pass and the library is confined to `core/infra`.

**Verify.** `uv run pytest tests/ -q && uv run ruff check . && uv run lint-imports && test "$(grep -rln 'pandas_market_calendars' src/ | grep -vc '^src/pocketquant/core/infra/calendars/')" = "0"` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `pandas_market_calendars` session semantics differ from ES/NQ/YM reality | Medium | High — every futures bar mis-bucketed | Task 7's 8 CME tests assert concrete instants; the Phase 5 gate cross-checks against `sync_verify_cascade` |
| Only `COMPOSITE_SYMBOL_RE` widened, `COMPOSITE_SYMBOL_PATTERN` forgotten | Medium | High — Phase 5 seeding fails with HTTP 400 | Task 9 step 5 names all four call sites |
| `SyncService` clobbers seeded metadata | High if unfixed | High — futures symbols silently revert to crypto | Task 10 replaces `upsert` with `touch` before any futures symbol exists |
| `ContractSpec` as a frozen dataclass inside a pydantic model | Low | Medium | Task 3's Verify round-trips it |

**Rollback.** Tasks 1-8 add new modules only and can be dropped wholesale. Task 9 is
the only schema-shaping change; reverting it requires re-adding `asset_type` and
re-running the migration in reverse (`$rename` `asset_class` back). Task 11's index is
additive and can be dropped with `db.bars.dropIndex("ix_ohlcv_symbol_interval_session_date")`.

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

=== FILE: phase-03-calendar-threaded-pipeline.md ===
---
phase: 3
title: "Calendar-Threaded Pipeline on the 24/7 Calendar"
status: pending
priority: P1
effort: "2.5d"
dependencies: [2]
---

## Context

(Advice Phase 2.) This is the phase that retires the five day-one P0s — alignment,
cascade, integrity, freshness and annualization — while no futures symbol exists yet.
Every one of them is threaded through `ITradingCalendarPort` and executed with the
24/7 calendar only, so the crypto path must come out byte-identical. If it does not,
the refactor is wrong and the bug is caught here rather than three phases later with
a scraper in the loop.

Read all five audit findings before starting: `bar_builder_domain_service.py:10-32`
plus `bar_filters.py:72-82`; `cascade_aggregator.py:41-47,98-137`;
`integrity_jobs.py:62-63`; `sync_status_service.py:62-69` plus
`anomaly_log.py:35-40,52-59`; `shared/enums.py:5-13` plus
`performance_calculator_domain_service.py:13-14`.

## Tasks

### Task 1 — Capture golden files BEFORE any refactor

**Goal.** A committed, deterministic snapshot of today's crypto behaviour that the
refactor must reproduce exactly.

**Target files and symbols.**
- New file `tests/app_test/market_data/test_cascade_calendar_golden.py`.
- New directory `tests/app_test/market_data/golden/` with
  `cascade_boundaries.json`, `aligned_bars.json`, `periods_per_year.json`.
- Functions captured: `cascade_aggregator.compute_boundaries`,
  `bar_builder_domain_service.get_bar_start`, `Interval.periods_per_year`.

**Steps.**
1. DO THIS TASK FIRST, before editing any production file in this phase.
2. Write a `generate` helper inside the test module, guarded by an environment
   variable `POCKETQUANT_REGEN_GOLDEN=1`, that writes the three JSON files. Running
   the test without that variable compares instead of writing.
3. `cascade_boundaries.json`: for every `tf` in `CASCADE_TFS`, call
   `compute_boundaries(tf, datetime(2026,6,1,0,0,tzinfo=UTC), datetime(2026,6,3,0,0,tzinfo=UTC))`
   and store the ISO strings.
4. `aligned_bars.json`: for every `Interval` member and for each of 12 fixed sample
   instants spanning 2026-03-07 through 2026-11-03 (covering both DST dates), store
   `get_bar_start(sample, interval).isoformat()`.
5. `periods_per_year.json`: for every `Interval` member, store
   `Interval.periods_per_year`.
6. Run with `POCKETQUANT_REGEN_GOLDEN=1` once, commit the three files, then run
   without it and confirm the comparison passes.

**Success criteria.** The three JSON files exist and the comparison test passes
against the unmodified code.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_calendar_golden.py -q` exits 0 and prints `3 passed`.

---

### Task 2 — Thread the calendar through bar alignment

**Goal.** Alignment is a function of the symbol's calendar, and the 24/7 calendar
gives exactly today's answer.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` —
  `is_bar_aligned` (line 31), `filter_aligned_bars` (line 35).
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py` —
  `drop_misaligned_bars` (lines 72-82).
- `src/pocketquant/engine/market_data/sync_internals/bar_alignment.py` —
  `has_aligned_bar` (line 6).
- `src/pocketquant/engine/market_data/sync_internals/provider_fetch.py` —
  `fetch_with_retry` (lines 31-73), which calls `has_aligned_bar` at line 61.
- `src/pocketquant/engine/market_data/sync_service.py` — `SyncService.sync_one`
  (lines 66-81).

**Steps.**
1. Change `is_bar_aligned(timestamp, interval)` to
   `is_bar_aligned(timestamp, interval, calendar)` and implement it as
   `timestamp == calendar.bar_start(timestamp, interval)`. Keep `get_bar_start`
   unchanged — it stays the 24/7 implementation that `Continuous24x7Calendar.bar_start`
   delegates to.
2. Change `filter_aligned_bars(bars, interval)` to
   `filter_aligned_bars(bars, interval, calendar)` and pass the calendar through.
3. Change `drop_misaligned_bars(records, interval)` to
   `drop_misaligned_bars(records, interval, calendar)`. Add `calendar_id` to the
   existing `market_data.sync.misaligned_bars_dropped` WARNING payload.
4. Change `has_aligned_bar(records, interval)` to
   `has_aligned_bar(records, interval, calendar)`.
5. Change `fetch_with_retry(provider, symbol, interval, n_bars)` to
   `fetch_with_retry(provider, symbol, interval, n_bars, calendar)` and pass the
   calendar to `has_aligned_bar` at line 61.
6. In `SyncService.__init__`, add a `calendar_factory: TradingCalendarFactory`
   parameter and store it. In `sync_one`, resolve the calendar once at the top:
   `calendar = await self._calendar_factory.for_symbol(symbol)`. Pass it to
   `fetch_with_retry` (line 66) and `drop_misaligned_bars` (line 80).
7. `MarketDataProvider.sync_service = provide(SyncService, scope=Scope.APP)` in
   `src/pocketquant/app/di/market_data.py:26` resolves constructor parameters by type,
   so registering `TradingCalendarFactory` in Phase 2 Task 8 is enough — no edit here.
   Confirm by running the DI integration test.

**Success criteria.** Every caller passes a calendar; no call site retains the
two-argument form.

**Verify.** `grep -rn "is_bar_aligned(\|filter_aligned_bars(\|drop_misaligned_bars(\|has_aligned_bar(" src/ | grep -vc "calendar" ` prints `0`.

---

### Task 3 — Thread the calendar through the cascade aggregator

**Goal.** Bucket boundaries and expected bar counts come from the calendar, and 24/7
reproduces the UTC-epoch grid exactly.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` —
  `_TF_EXPECTED_BARS` (lines 41-47), `compute_boundaries` (lines 98-137),
  `cascade_for_symbol` (lines 140-235).
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py` — `sync_1m`
  (the `cascade_for_symbol` call around line 413).
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py` — the
  `cascade_for_symbol` import at line 22 and its `_cascade` call site.

**Steps.**
1. Change the signature to
   `compute_boundaries(tf, range_start, range_end, calendar)`. Keep it a PURE
   function — the calendar is a parameter, not a lookup.
2. Replace the epoch-floor body with:
   ```python
   first = calendar.bar_start(range_start, tf)
   boundaries = []
   current = first
   while current < range_end:
       boundaries.append(current)
       current = calendar.bar_start(current + timedelta(seconds=secs), tf)
   ```
   Stepping through `calendar.bar_start` (rather than adding a fixed `secs`) is what
   makes the loop correct across a session gap and across a DST transition. For the
   24/7 calendar it produces exactly the old grid.
3. Guard against a non-advancing loop: if `calendar.bar_start(current + secs, tf)`
   is not strictly greater than `current`, advance by `timedelta(seconds=secs)` and
   log one DEBUG `cascade.boundary_step_fallback`.
4. Replace the `_TF_EXPECTED_BARS` constant lookup in `cascade_for_symbol` with
   `expected_count = len(calendar.trading_minutes(boundary, bucket_end))`. Delete
   `_TF_EXPECTED_BARS`. For the 24/7 calendar this yields 5/15/60/240/1440 — the same
   numbers — because `Continuous24x7Calendar.trading_minutes` is the dense grid.
5. Change `cascade_for_symbol(symbol, lookback_minutes, bar_repo)` to
   `cascade_for_symbol(symbol, lookback_minutes, bar_repo, calendar)`.
6. When writing the cascaded `Bar`, set `calendar_id=calendar.calendar_id` and, for
   `tf in (Interval.DAY_1,)`, `session_date=calendar.session_date(boundary)`.
7. Update both call sites to resolve the calendar first: in `sync_jobs.sync_1m`
   resolve via `await calendar_factory.for_symbol(ts.symbol)` inside the per-symbol
   loop (get `TradingCalendarFactory` from the container alongside `bar_repo`);
   in `tracked_symbols_backfill.TrackedSymbolBackfillService`, add a
   `calendar_factory` constructor parameter and resolve in `_cascade`.
8. Add `calendar_id` to the `cascade.partial_aggregate` WARNING payload.

**Success criteria.** The golden cascade boundaries from Task 1 still match.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_calendar_golden.py tests/app_test/market_data/test_cascade_aggregator.py -q` exits 0.

---

### Task 4 — Thread the calendar through the integrity check

**Goal.** The expected-bar grid is the calendar's trading minutes, not a dense
arithmetic grid, so weekends, halts and holidays stop reading as gaps.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` —
  `check_integrity` (lines 36-76), `repair_integrity` (lines 79-140).
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py` — `_run_integrity`
  (line 285) and `_run_repair` (line 329).

**Steps.**
1. Change `check_integrity(symbol, interval, bar_repo, days_back=7)` to
   `check_integrity(symbol, interval, bar_repo, calendar, days_back=7)`.
2. Replace the arithmetic `expected` set at lines 62-63 with:
   - `Interval.DAY_1` → `{calendar.session_open(d) for d in calendar.sessions(start, end)}`
   - `Interval.WEEK_1` → skip the gap check entirely: return the report with
     `missing_count=0` and `gap_ranges=[]`, and add a `skipped_reason="weekly_convention"`
     key. Document that weekly repair is deferred until a weekly convention exists.
   - everything else → derive from `calendar.trading_minutes(start, end)`, keeping
     only instants where `instant == calendar.bar_start(instant, interval)`.
3. Replace `is_bar_aligned(d["datetime"], interval)` at line 57 with the
   calendar-aware three-argument form.
4. Update the docstring at lines 46-47 — it currently says the check is only reliable
   for 24/7 markets. Replace that with a statement that the expected grid comes from
   the symbol's calendar.
5. Change `repair_integrity(...)` to accept and forward the calendar, and skip the
   resync entirely when `report.get("skipped_reason")` is set.
6. In `sync_jobs._run_integrity` and `_run_repair`, resolve the calendar per symbol
   from `TradingCalendarFactory` (obtain it from the container the same way
   `BarRepository` is obtained) and pass it down.

**Success criteria.** For a crypto symbol the missing-bar counts are unchanged; for a
`WEEK_1` interval the check short-circuits.

**Verify.** `uv run pytest tests/app_test/integration/test_sync_backfill_gap_fill.py -q` exits 0.

---

### Task 5 — Make freshness and anomaly gating session-aware

**Goal.** A closed market is reported as closed, not as stuck, and no `no_progress`
WARNING is emitted while the market is shut.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_status_service.py` — `_is_stuck`
  (lines 62-69), `SyncStatusResult` (lines 47-59), `SyncStatusQueryService.get_sync_status`
  and `get_symbol_sync_status`.
- `src/pocketquant/engine/market_data/sync_internals/anomaly_log.py` —
  `emit_no_progress` (lines 20-61).
- `src/pocketquant/engine/market_data/sync_service.py` — the `emit_no_progress` call
  (lines 102-111).
- `src/pocketquant/app/routes/market_data_status.py` — both response dicts.
- `web/src/types/market-data.ts` — the `SyncStatus` interface (the `is_stuck` field
  at line 88).
- `web/src/components/monitor/data-health-row.tsx` (lines 50, 55, 72) and
  `web/src/components/monitor/format-helpers.ts` (line 19).

**Steps.**
1. Change `_is_stuck(latest_bar_dt, interval)` to
   `_is_stuck(latest_bar_dt, interval, calendar)` and measure the age against
   `calendar.previous_close(datetime.now(UTC))` instead of `datetime.now(UTC)`. For
   the 24/7 calendar `previous_close` is the identity, so crypto arithmetic is
   unchanged.
2. Add `is_market_open: bool = True` to `SyncStatusResult`.
3. In `SyncStatusQueryService`, add a `calendar_factory: TradingCalendarFactory`
   constructor parameter; resolve the calendar per symbol, set
   `is_market_open=calendar.is_open(datetime.now(UTC))`, and pass the calendar to
   `_is_stuck`. Resolve calendars with `asyncio.gather` alongside the existing
   `_enrich_with_bars` gather so the endpoint stays one round of concurrency.
4. Add `calendar` as a keyword-only parameter to `emit_no_progress` and short-circuit
   at the top:
   ```python
   if not calendar.is_open(datetime.now(UTC)):
       logger.debug("market_data.sync.skipped_closed", symbol=symbol, interval=interval.value)
       return
   ```
   DEBUG, not INFO: this fires once per symbol per minute while a market is closed,
   which is a hot path under the CLAUDE.md log-frequency rule.
5. Pass the already-resolved calendar from `SyncService.sync_one` into
   `emit_no_progress`.
6. Add `"is_market_open": s.is_market_open,` to both route response dicts in
   `market_data_status.py`.
7. In the SPA, add `is_market_open?: boolean` to the `SyncStatus` interface, and in
   `data-health-row.tsx` and `format-helpers.ts` show a neutral `CLOSED` badge instead
   of the stuck badge when `is_market_open === false`.

**Success criteria.** With a closed calendar, `emit_no_progress` writes no WARNING and
the status DTO reports `is_market_open=false`.

**Verify.** `uv run pytest tests/app_test/unit/handlers/status/test_sync_status_service.py tests/app_test/unit/handlers/sync/test_no_progress_tracking.py -q` exits 0.

---

### Task 6 — Populate `session_date` and `calendar_id` on the sync write path

**Goal.** Daily and weekly bars carry the stable session-day key added in Phase 2.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_service.py` — `SyncService._persist_bars`
  (lines 149-154).

**Steps.**
1. Before persisting, for `interval in (Interval.DAY_1, Interval.WEEK_1)`, set on each
   record `bar.calendar_id = calendar.calendar_id` and
   `bar.session_date = calendar.session_date(bar.datetime)`.
2. For every other interval set only `calendar_id`, leaving `session_date` as `None`.
3. Pass the calendar resolved in `sync_one` into `_persist_bars` as a parameter.

**Success criteria.** A 1d bar written by the sync path carries both fields.

**Verify.** `uv run pytest tests/engine_test/market_data/test_sync_service.py -q` exits 0.

---

### Task 7 — Gate the sync job on the calendar

**Goal.** While a market is closed the job does not call the provider at all.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py` —
  `_sync_by_intervals` (lines 130-232), `sync_1m` (line 382).

**Steps.**
1. Add a `calendar_factory: TradingCalendarFactory` parameter to
   `_sync_by_intervals` and resolve the calendar once per symbol at the top of the
   outer `for symbol in symbols:` loop (line 164).
2. Immediately after resolving, compute a grace-aware open test:
   ```python
   now = datetime.now(UTC)
   grace = timedelta(seconds=INTERVAL_SECONDS[max(intervals, key=lambda i: INTERVAL_SECONDS[i])])
   is_open = calendar.is_open(now) or (now - calendar.previous_close(now)) <= grace
   ```
   One interval of grace after close so the final bar of the session is still fetched.
3. When `is_open` is False: `continue` to the next symbol, increment a `skipped`
   counter, and record a job-history detail with `status="skipped"` and
   `error="closed"` when `doc_id` is set. Do not call `sync_service.sync_one`.
4. Include `skipped_count` in the existing
   `logger.info(f"market_data.{job_name}.completed", ...)` payload at line 226.
5. Update both `_run_sync` (line 234) and `sync_1m` (line 398) to obtain
   `TradingCalendarFactory` from the container and pass it through.
6. For the 24/7 calendar `is_open` is always True, so crypto behaviour is unchanged.

**Success criteria.** A symbol whose calendar is closed produces zero provider calls
and one `skipped` job-history detail.

**Verify.** `uv run pytest tests/app_test/test_sync_jobs_phase.py tests/app_test/unit/market_data/test_sync_jobs_catchup.py -q` exits 0.

---

### Task 8 — Fetch 1d and 1w natively for calendar-based asset classes

**Goal.** Futures daily and weekly bars come from the provider's own session bars, not
from cascading 1m across UTC midnight.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` —
  `CASCADE_TFS` (lines 32-38).
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py` — `SYNC_INTERVALS`
  (lines 54-62) and the comment above it.

**Steps.**
1. Turn `CASCADE_TFS` into a function
   `cascade_tfs(calendar) -> list[Interval]` that returns the current list for the
   24/7 calendar and `[MINUTE_5, MINUTE_15, HOUR_1, HOUR_4]` (no `DAY_1`) for any
   other calendar id.
2. In `cascade_for_symbol`, iterate `for tf in cascade_tfs(calendar):`.
3. `SYNC_INTERVALS` already contains `DAY_1` and `WEEK_1`, so the REST path already
   fetches them for every symbol. Leave the list unchanged and extend the comment
   above it to say that for calendar-based asset classes 1d and 1w are REST-only,
   because a cascade across UTC midnight would produce a daily bar that never matches
   the vendor chart.

**Success criteria.** For a CME calendar, `cascade_tfs` excludes `DAY_1`; for 24/7 it
is unchanged.

**Verify.** `uv run python -c "
from pocketquant.engine.market_data.app_services.cascade_aggregator import cascade_tfs
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
print(len(cascade_tfs(Continuous24x7Calendar())), len(cascade_tfs(CmeGlobexCalendarAdapter())))"` prints `5 4`.

---

### Task 9 — Move annualization onto the calendar

**Goal.** The `Interval` enum stops owning a calendar it does not own.

**Target files and symbols.**
- `src/pocketquant/engine/backtest/backtest_report_app_service.py` — line 368
  (`Interval.periods_per_year_for(self._config.interval)`), the only production call
  site (grep-verified on 2026-09-21).
- `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py` —
  `TRADING_DAYS_PER_YEAR` (line 14), used at line 52 in `cagr`.
- `src/pocketquant/core/domain/shared/enums.py` — `Interval.periods_per_year`
  (line 26) and `periods_per_year_for` (line 34).
- `src/pocketquant/engine/live/live_metrics_query_service.py` — line 64 passes
  `periods_per_year=None` deliberately; leave it alone.

**Steps.**
1. In `backtest_report_app_service.py`, replace line 368 with a calendar lookup. The
   service must receive a `ITradingCalendarPort` for `self._config.symbol`; add a
   `calendar` constructor parameter and resolve it where the report service is
   constructed (`engine/backtest/backtest_dispatch.py` and
   `engine/backtest/backtest_app_service.py` — grep for the constructor call and
   thread it through). Then:
   ```python
   periods_per_year = self._calendar.periods_per_year(Interval(self._config.interval))
   ```
   Keep the existing `None` fallback for an interval string that is not a valid
   `Interval` member — wrap the conversion in `try/except ValueError`.
2. In `performance_calculator_domain_service.py`, change `cagr` to take
   `days_per_year: float = 365` as a keyword argument instead of reading the module
   constant, and pass `calendar.periods_per_year(Interval.DAY_1)` from
   `PerformanceCalculatorDomainService.build`. Keep the module constant as the
   default so the domain service stays usable without a calendar.
3. Mark `Interval.periods_per_year` and `Interval.periods_per_year_for` as deprecated
   in their docstrings — "the calendar owns annualization; this is the 24/7 default,
   kept as the `Continuous24x7Calendar` data source". Do NOT delete them:
   `Continuous24x7Calendar.periods_per_year` reads the same table.

**Success criteria.** For a crypto backtest the reported `periods_per_year` is
unchanged; for a CME calendar it is the session-derived value.

**Verify.** `uv run pytest tests/backtest_test/domain/test_performance_calculator_annualization.py tests/core_test/unit/domain/shared/test_interval.py -q` exits 0.

---

### Task 10 — Calendar annualization test

**Goal.** The CME annualization is in the right range and crypto is exact.

**Target files and symbols.**
- New file `tests/backtest_test/domain/test_performance_calculator_calendar_annualization.py`.

**Steps.**
1. Write 4 tests.
2. `test_crypto_1m_is_525600`: `Continuous24x7Calendar().periods_per_year(Interval.MINUTE_1) == 525600`.
3. `test_crypto_1d_is_365`: same for `DAY_1` equals `365`.
4. `test_cme_sessions_per_year_in_range`: `CmeGlobexCalendarAdapter().periods_per_year(Interval.DAY_1)`
   is between `245` and `255` inclusive.
5. `test_cme_hourly_in_range`: `periods_per_year(Interval.HOUR_1)` is between `5000`
   and `6200` inclusive (23h x 252 sessions is about 5796).

**Success criteria.** 4 tests pass.

**Verify.** `uv run pytest tests/backtest_test/domain/test_performance_calculator_calendar_annualization.py -q` exits 0 and prints `4 passed`.

---

### Task 11 — Phase gate: crypto must be byte-identical

**Goal.** Prove G5 before any futures code is written.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the golden comparison from Task 1 WITHOUT regenerating.
2. Run the full suite under all three CI timezones.
3. Run ruff, pyright and the import contracts.
4. Deploy to the VPS and watch one full `sync_1m` cycle plus the hourly
   `sync_verify_cascade`. Compare the `synced_count` and `cascade` counts in
   `job_history` with the previous day's run for the same hour. Record the numbers in
   the phase completion note.

**Success criteria.** The golden files match unmodified, the suite is green under all
three zones, and one prod cron cycle produces the same counts as before.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_calendar_golden.py -q && uv run pytest tests/ -q && TZ=America/Chicago uv run pytest tests/ -q && uv run ruff check . && uv run lint-imports` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The boundary-stepping loop in Task 3 fails to advance and spins forever | Medium | High — cron job hangs | Task 3 step 3 adds an explicit non-advancement fallback |
| A calendar resolution is added to a per-bar hot path and hammers Mongo | Medium | Medium | `SymbolLookupHelper` caches with a 60s TTL; calendars are resolved once per symbol per job run, never per bar |
| Crypto cascade output shifts by one bucket | Medium | High — silent data corruption | Task 1's golden files are captured before any edit and compared in Task 11 |
| `backtest_report_app_service` constructor threading misses a call site | Medium | Medium — `TypeError` at runtime | Task 9 step 1 requires grepping for every constructor call |
| Annualization change alters an existing backtest's stored Sharpe | Low | Low | Crypto values are identical by construction; historical runs are not recomputed |

**Rollback.** Revert this phase as one unit. The signature changes are pervasive
enough that a partial revert leaves callers passing the wrong arity. The Phase 2
artefacts (port, implementations, factory) survive a Phase 3 revert untouched.

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

=== FILE: phase-04-provider-routing-adapters.md ===
---
phase: 4
title: "Provider Routing Adapters and Settings"
status: pending
priority: P1
effort: "1d"
dependencies: [2]
---

## Context

(Advice Phase 3.) Today DI binds exactly one `IDataProviderPort` (`app/di/infrastructure.py:30-31`)
and one `IRealtimeQuoteProviderPort` (`app/di/market_data.py:34-36`). This phase
replaces both bindings with routing adapters that hold a `dict[provider_id, adapter]`
and resolve the provider list per symbol from the symbol's asset class plus optional
per-symbol overrides. Because the routing adapters implement the SAME ports,
`SyncService`, `fetch_with_retry`, `WsSubscriptionAppService`, `QuoteAppService` and
`TrackedSymbolBackfillService` need no edits — that is G4.

This phase ships with Binance as the ONLY registered provider, so the crypto path must
stay byte-for-byte unchanged.

## Tasks

### Task 1 — Provider settings

**Goal.** The provider map and per-symbol overrides are configuration, not code.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — `Settings` (lines 30-74).

**Steps.**
1. Add a `# Market-data provider routing` section after `enable_jobs` (line 57):
   ```python
   market_data_providers: dict[AssetClass, list[str]] = {
       AssetClass.CRYPTO_SPOT: ["binance"],
       AssetClass.CRYPTO_PERP: ["binance"],
       AssetClass.INDEX_FUTURE: ["tradingview"],
   }
   symbol_provider_overrides: dict[str, list[str]] = {}
   ```
2. Import `AssetClass` from `pocketquant.core.domain.shared.enums`. `core.config`
   importing `core.domain` is allowed by every import-linter contract; confirm with
   `uv run lint-imports`.
3. pydantic-settings parses a `dict`-typed field from a JSON string in the
   environment, so `MARKET_DATA_PROVIDERS={"index_future":["tradingview","binance"]}`
   works with no custom parser.
4. Document both field names (names only, never values) in `README.md` next to the
   existing env-var list, and in `docs/system-architecture.md` under `## Configuration`.

**Success criteria.** The settings load with defaults and accept a JSON override.

**Verify.** `MARKET_DATA_PROVIDERS='{"index_future":["tradingview","binance"]}' uv run python -c "
from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import AssetClass
print(Settings().market_data_providers[AssetClass.INDEX_FUTURE])"` prints `['tradingview', 'binance']`.

---

### Task 2 — Pure provider-resolution function

**Goal.** One place decides which providers serve a symbol, shared by both routing
adapters.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/provider_routing_domain_service.py`.
- Symbol: `resolve_provider_ids`.

**Steps.**
1. Write a pure module-level function, following the precedent of
   `bar_builder_domain_service.py` (module of pure functions, no class):
   ```python
   def resolve_provider_ids(
       symbol: str,
       asset_class: AssetClass,
       provider_map: dict[AssetClass, list[str]],
       overrides: dict[str, list[str]],
   ) -> list[str]:
       """Ordered provider ids for a composite symbol: primary first, then fallbacks."""
   ```
2. Behaviour: an override keyed by the upper-cased composite symbol wins outright;
   otherwise return `provider_map.get(asset_class, [])`. Return a NEW list, never the
   stored one, so a caller cannot mutate settings.
3. Add no I/O and no logging — this is domain code covered by the purity AST test.

**Success criteria.** Overrides win, the map is the fallback, and an unmapped asset
class returns an empty list.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_provider_routing.py -q` exits 0 and prints `4 passed` (test written in Task 3).

---

### Task 3 — Provider-resolution tests

**Goal.** The routing rule is pinned before any adapter depends on it.

**Target files and symbols.**
- New file `tests/core_test/unit/domain/market_data/test_provider_routing.py`.

**Steps.**
1. Write 4 tests: `test_asset_class_map_is_used`,
   `test_symbol_override_beats_asset_class`,
   `test_override_lookup_is_case_insensitive` (pass `es1!:cme_mini`, expect the
   override registered under `ES1!:CME_MINI`),
   `test_unmapped_asset_class_returns_empty_list`.

**Success criteria.** 4 tests pass.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_provider_routing.py -q` exits 0 and prints `4 passed`.

---

### Task 4 — `RoutingDataProviderAdapter`

**Goal.** REST history is fetched from the symbol's primary provider, falling back to
the next on exception or empty result.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/market_data/` with `__init__.py`.
- New file `src/pocketquant/core/infra/market_data/routing_data_provider_adapter.py`.
- Symbol: `RoutingDataProviderAdapter`, implementing
  `pocketquant.core.domain.market_data.data_provider_port.IDataProviderPort`.

**Steps.**
1. Constructor takes `providers: dict[str, IDataProviderPort]`, `settings: Settings`
   and `symbol_lookup: SymbolLookupHelper`.
2. Implement `fetch_ohlcv(symbol, interval, n_bars)`:
   - resolve the symbol record via `symbol_lookup.get(symbol)`; use
     `AssetClass.CRYPTO_SPOT` when it is missing (a brand-new symbol being synced for
     the first time);
   - call `resolve_provider_ids(...)`;
   - iterate the ids in order; skip an id with no registered adapter after logging one
     WARNING naming the id (guard with a `set` so it is one-shot per id);
   - call the adapter; on a non-empty result return it immediately;
   - on an exception or an empty list, log DEBUG `market_data.routing.fallback` with
     the symbol, the failed provider id and the next one, then continue;
   - after the last provider, return `[]`.
   Do not log per-attempt at INFO — `fetch_ohlcv` runs once per symbol per interval
   per minute.
3. Implement `search_symbols(query)` by delegating to the FIRST provider registered in
   `market_data_providers[AssetClass.CRYPTO_SPOT]`, and document that symbol search
   stays single-provider for now.
4. Implement `close()` by awaiting `close()` on every registered provider, collecting
   exceptions and re-raising the first one after all have been attempted.

**Success criteria.** A fake primary that raises falls through to a fake secondary
that returns bars.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_routing_data_provider_adapter.py -q` exits 0 and prints `6 passed` (tests written in Task 6).

---

### Task 5 — `RoutingRealtimeQuoteAdapter`

**Goal.** WS subscriptions are delegated to the one provider that owns each symbol.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/market_data/routing_realtime_quote_adapter.py`.
- Symbol: `RoutingRealtimeQuoteAdapter`, satisfying the 9-member
  `IRealtimeQuoteProviderPort` Protocol declared at
  `src/pocketquant/core/domain/market_data/realtime_quote_provider_port.py:15-58`:
  `last_tick_at`, `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`,
  `is_connected`, `subscription_count`, `subscriptions`.

**Steps.**
1. Constructor takes `providers: dict[str, IRealtimeQuoteProviderPort]`,
   `settings: Settings` and `symbol_lookup: SymbolLookupHelper`. Keep
   `self._owner: dict[str, str]` mapping composite symbol to the provider id that owns
   its subscription.
2. `subscribe(symbol, callback)`: resolve the ordered ids and use ONLY THE FIRST one.
   Do NOT fall back. Two realtime providers streaming the same symbol would
   double-count ticks in `BarBuilderDomainService`. Record the owner and return the
   child's subscription key.
3. `unsubscribe(symbol)`: look up the owner, delegate, and drop the owner entry.
4. `connect()` / `disconnect()`: `await` every child in turn; on `disconnect`, swallow
   and log each child's exception at WARNING so one bad child cannot block shutdown.
5. `run_forever()`: `await asyncio.gather(*(p.run_forever() for p in providers.values()))`.
   Let `CancelledError` propagate so lifespan teardown works.
6. `is_connected()`: True when at least one child is connected.
7. `subscription_count`: sum of the children's counts.
8. `subscriptions`: a merged dict built from every child, so
   `WsSubscriptionAppService._reconcile` (which reads `provider.subscriptions.keys()`
   at `ws_subscription_app_service.py:68`) sees the full desired set.
9. `last_tick_at`: implement as a property returning the maximum non-`None`
   `last_tick_at` across children, or `None`. The Protocol declares it as a plain
   attribute; a read-only property satisfies structural typing.

**Success criteria.** `isinstance(adapter, IRealtimeQuoteProviderPort)` is True (the
Protocol is `@runtime_checkable`).

**Verify.** `uv run python -c "
from pocketquant.core.domain.market_data.realtime_quote_provider_port import IRealtimeQuoteProviderPort
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import RoutingRealtimeQuoteAdapter
print(hasattr(RoutingRealtimeQuoteAdapter, 'run_forever'), issubclass(RoutingRealtimeQuoteAdapter, IRealtimeQuoteProviderPort) if hasattr(IRealtimeQuoteProviderPort, '_is_runtime_protocol') else 'n/a')"` prints a line starting with `True`.

---

### Task 6 — Routing adapter tests

**Goal.** Fallback, no-fallback-for-realtime and the merged subscription view are
pinned.

**Target files and symbols.**
- New package dir `tests/core_test/infra/market_data/`.
- New file `tests/core_test/infra/market_data/test_routing_data_provider_adapter.py`.
- New file `tests/core_test/infra/market_data/test_routing_realtime_quote_adapter.py`.

**Steps.**
1. In the REST test module, write 6 tests with `unittest.mock.AsyncMock` fakes:
   `test_primary_result_returned`, `test_exception_falls_through_to_secondary`,
   `test_empty_result_falls_through_to_secondary`,
   `test_all_providers_exhausted_returns_empty_list`,
   `test_unknown_provider_id_is_skipped`,
   `test_symbol_override_selects_the_overridden_provider_first`.
2. In the realtime test module, write 4 tests:
   `test_subscribe_uses_only_the_first_provider`,
   `test_unsubscribe_reaches_the_owning_provider`,
   `test_subscriptions_merges_children`,
   `test_last_tick_at_is_the_max_across_children`.
3. In `test_symbol_override_selects_the_overridden_provider_first`, assert with
   `git diff --stat` reasoning in a comment that the override needed no change in
   `engine/` or `app/` — this is the G4 evidence.

**Success criteria.** 10 tests pass.

**Verify.** `uv run pytest tests/core_test/infra/market_data/ -q` exits 0 and prints `10 passed`.

---

### Task 7 — Bind the routing adapters in DI, Binance only

**Goal.** The container hands every consumer a routing adapter, with Binance as the
sole registered provider.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` — `InfrastructureProvider.get_data_provider`
  (lines 29-31).
- `src/pocketquant/app/di/market_data.py` — `MarketDataProvider.get_realtime_quote_provider`
  (lines 34-36).

**Steps.**
1. In `infrastructure.py`, change `get_data_provider` to build the map and wrap it:
   ```python
   @provide(scope=Scope.APP)
   def get_data_provider(
       self, settings: Settings, symbol_lookup: SymbolLookupHelper
   ) -> IDataProviderPort:
       return RoutingDataProviderAdapter(
           providers={"binance": BinanceAdapter(settings=settings)},
           settings=settings,
           symbol_lookup=symbol_lookup,
       )
   ```
2. In `market_data.py`, do the same for the realtime port with
   `{"binance": BinanceWebSocketAdapter()}`. Keep the existing
   `# type: ignore[return-value]` comment style for the Protocol return.
3. Do NOT register a TradingView provider here — Phase 5 adds it.
4. Verify no other file constructs `BinanceAdapter` or `BinanceWebSocketAdapter`
   outside DI and tests.

**Success criteria.** The whole DI graph still resolves and no consumer changed.

**Verify.** `uv run pytest tests/app_test/integration/ -q && test "$(grep -rln 'BinanceAdapter(\|BinanceWebSocketAdapter(' src/ | grep -vc '^src/pocketquant/app/di/')" = "0"` exits 0.

---

### Task 8 — Phase gate: crypto unchanged through the routing layer

**Goal.** Prove the routing layer is transparent before TradingView enters.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite plus ruff, pyright and the import contracts.
2. Deploy to the VPS and observe one `sync_1m` cycle. Compare `synced_count` and
   `bars_inserted` in `job_history` against the pre-deploy run at the same minute of
   the previous hour.
3. Confirm the WS quote feed still delivers ticks: `GET /api/v1/market-data/quotes/BTCUSDT%3ABINANCE`
   returns a timestamp within the last 60 seconds.

**Success criteria.** Identical counts and a live quote.

**Verify.** `uv run pytest tests/ -q && uv run ruff check . && uv run lint-imports` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Routing adapter breaks the `IRealtimeQuoteProviderPort` structural match and DI fails at startup | Medium | High | Task 5's Verify plus Task 7's integration-test run |
| `symbol_lookup` read on the WS subscribe path adds latency to reconcile | Low | Low | 60s TTL cache; reconcile runs every 5s over a handful of symbols |
| A new symbol has no `symbols` document yet, so routing defaults to crypto | Medium | Low | Task 4 step 2 documents the default explicitly; seeding in Phase 5 writes the record before the first sync |
| Settings JSON key casing does not match the enum values | Medium | Medium | Task 1's Verify uses the lower-case enum value `index_future` |

**Rollback.** Revert Task 7 alone to restore the direct Binance bindings; the routing
adapters stay in the tree unused and harmless.

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

=== FILE: phase-05-tradingview-history-and-backfill.md ===
---
phase: 5
title: "TradingView History Adapter, Seeding and Backfill"
status: pending
priority: P1
effort: "1.5d"
dependencies: [3, 4]
---

## Context

(Advice Phase 4.) The first futures data lands here. The scraper library is isolated
behind an internal client interface so it can be swapped without touching the adapter,
the mapper never trusts the library's DataFrame index for timestamps, and the bar cap
and credentials are configuration with no branching on the TradingView plan tier.

Two verified facts drive the design:
- `tvDatafeed`'s `__create_df` builds each bar timestamp with
  `datetime.datetime.fromtimestamp(float(xi[4]))` — NAIVE HOST-LOCAL time. The raw
  epoch is consumed inside the library and is not re-exposed on the DataFrame.
- The library is not on PyPI; it installs from
  `git+https://github.com/rongardF/tvdatafeed.git` and imports as `tvDatafeed`
  (capital D).

## Tasks

### Task 1 — Add the scraper dependency and TradingView settings

**Goal.** The library is installed and every entitlement knob is a setting.

**Target files and symbols.**
- `pyproject.toml` — `[project] dependencies`.
- `src/pocketquant/core/config.py` — `Settings`.

**Steps.**
1. Add to `dependencies`:
   `"tvdatafeed @ git+https://github.com/rongardF/tvdatafeed.git",`
2. Run `uv sync` and confirm the lock updates.
3. Add to `Settings`, under a `# TradingView (index futures data source)` comment:
   ```python
   tradingview_username: str | None = None
   tradingview_password: SecretStr | None = None
   tradingview_auth_token: SecretStr | None = None
   tradingview_max_bars: int = 5000
   tradingview_poll_seconds: int = 60
   tradingview_delayed_data: bool = True
   ```
   `SecretStr` is already imported at `core/config.py:6`.
4. `tradingview_poll_seconds` defaults to 60, not 10: with delayed CME data (the
   default on every plan until the non-professional add-on is bought) polling faster
   only increases ban risk.
5. Document the field NAMES in `README.md`. Put the VALUES only in
   `../pocketquant-config/vps/default/.env` (prod) and
   `../pocketquant-config/local/all-local.env` (dev). Never write a value into this
   repository, its tests, its docs or a commit message.

**Success criteria.** The library imports and the settings load with defaults.

**Verify.** `uv run python -c "import tvDatafeed; from pocketquant.core.config import Settings; print(hasattr(tvDatafeed,'TvDatafeed'), Settings().tradingview_max_bars)"` prints `True 5000`.

---

### Task 2 — Internal TradingView client interface

**Goal.** The scraper is behind one narrow seam, so replacing it is one new class.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/tradingview/` with `__init__.py`.
- New file `src/pocketquant/core/infra/tradingview/tradingview_client_interface.py`.
- Symbols: `RawBar`, `ITradingViewClient`.

**Steps.**
1. Define a frozen dataclass `RawBar` with fields
   `epoch_seconds: float`, `open: float`, `high: float`, `low: float`,
   `close: float`, `volume: float`. This is the seam's currency — an instant plus
   OHLCV, with no library types leaking through.
2. Define a `Protocol` named `ITradingViewClient` with:
   ```python
   async def fetch_bars(
       self, code: str, exchange: str, interval: Interval, n_bars: int, fut_contract: int | None
   ) -> list[RawBar]: ...
   def is_authenticated(self) -> bool: ...
   ```
3. Naming follows the repo precedent `strategy_service_interface.py` /
   `IStrategyService` (docs/code-standards.md, "Class Naming by Layer"). This is an
   infra-internal seam, not a domain port, so it stays in `core/infra`.

**Success criteria.** The module imports with no dependency on `tvDatafeed`.

**Verify.** `uv run python -c "
import sys
from pocketquant.core.infra.tradingview.tradingview_client_interface import ITradingViewClient, RawBar
print('tvDatafeed' not in sys.modules)"` prints `True`.

---

### Task 3 — `TvDatafeedClient`

**Goal.** The synchronous, thread-based library runs off the event loop and yields
epoch-bearing raw bars.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tvdatafeed_client.py`.
- Symbol: `TvDatafeedClient`.

**Steps.**
1. Constructor takes `settings: Settings`. Build the underlying client lazily on the
   first call, inside `asyncio.to_thread`, because login performs blocking network I/O.
2. Login: when `tradingview_username` and `tradingview_password` are both set, call
   `TvDatafeed(username=..., password=...)`. On any exception, log one WARNING
   `provider.tradingview.auth` with `status="degraded"` and the exception type (NEVER
   the credentials), then fall back to `TvDatafeed()` (the library's anonymous mode).
   The process must never crash on a login failure.
3. `is_authenticated()` returns whether the logged-in construction succeeded.
4. `fetch_bars(...)` runs
   `await asyncio.to_thread(self._tv.get_hist, symbol=code, exchange=exchange, interval=<mapped>, n_bars=n_bars, fut_contract=fut_contract)`.
5. Convert the returned DataFrame to `list[RawBar]`. For the epoch, DO NOT read the
   index value as if it were UTC. Recover the original epoch:
   ```python
   idx = row_timestamp.to_pydatetime()
   epoch = idx.timestamp() if idx.tzinfo is None else idx.astimezone(UTC).timestamp()
   ```
   A naive datetime's `.timestamp()` interprets it in the host zone — which is exactly
   the zone the library used to build it — so the round trip recovers the true epoch on
   ANY host, not only under `TZ=UTC`. This is what lets the CI timezone matrix from
   Phase 1 Task 12 pass.
6. Return `None`/empty safely: `get_hist` returns `None` when its regex match fails.
   Treat that as an empty list and log one DEBUG.
7. Log at DEBUG only — this runs once per symbol per interval per cron tick.

**Success criteria.** The client returns `RawBar`s whose `epoch_seconds` are
host-zone independent.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q` exits 0 (tests written in Task 5).

---

### Task 4 — TradingView mappers

**Goal.** Composite symbols, intervals and raw bars translate in exactly one place.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_mappers.py`.
- Symbols: `INTERVAL_TO_TRADINGVIEW`, `split_futures_symbol`, `raw_bar_to_bar`.

**Steps.**
1. `split_futures_symbol(composite: str) -> tuple[str, str, int | None]`:
   split on `:` (the composite format is `{CODE}:{EXCHANGE}`); when the code ends with
   `1!`, strip the suffix and return `fut_contract=1`; otherwise return the code
   unchanged and `fut_contract=None`. So `ES1!:CME_MINI` becomes
   `("ES", "CME_MINI", 1)`.
2. `INTERVAL_TO_TRADINGVIEW`: a `dict[Interval, tvDatafeed.Interval]` covering all
   seven members. Verify the exact enum member names against the installed package
   before writing them (step 5 below) — the expected names are `in_1_minute`,
   `in_5_minute`, `in_15_minute`, `in_1_hour`, `in_4_hour`, `in_daily`, `in_weekly`.
   Import `tvDatafeed.Interval` under an alias so it does not shadow the domain
   `Interval`.
3. `raw_bar_to_bar(raw: RawBar, symbol: str, interval: Interval) -> Bar` builds
   `datetime=datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)` and copies OHLCV.
   Set `tick_count=0`. Never construct a naive datetime here — `Bar`'s validator from
   Phase 1 Task 7 rejects it.
4. Keep the mapper module free of any network call, exactly like
   `core/infra/binance/binance_mappers.py`.
5. Before writing the interval map, print the real member names and fix the map to
   match: run the Verify command below.

**Success criteria.** All seven domain intervals map to a real `tvDatafeed.Interval`
member.

**Verify.** `uv run python -c "
import tvDatafeed
from pocketquant.core.infra.tradingview.tradingview_mappers import INTERVAL_TO_TRADINGVIEW
from pocketquant.core.domain.shared.enums import Interval
print(len(INTERVAL_TO_TRADINGVIEW) == len(list(Interval)), all(isinstance(v, tvDatafeed.Interval) for v in INTERVAL_TO_TRADINGVIEW.values()))"` prints `True True`.

---

### Task 5 — Offline mapper tests with a host-zone matrix

**Goal.** The naive-local-time trap is provably closed.

**Target files and symbols.**
- New package dir `tests/core_test/infra/tradingview/`.
- New file `tests/core_test/infra/tradingview/test_tradingview_mappers.py`.
- New fixture file `tests/core_test/infra/tradingview/fixtures/es_1h_raw.json`.

**Steps.**
1. Build the fixture as a JSON list of 6 objects, each with keys
   `epoch_seconds`, `open`, `high`, `low`, `close`, `volume`. Use real ES 1h values
   with epochs spanning the 2026-03-08 DST transition. STORE THE EPOCHS, never a
   formatted datetime string — a stored local-time string would itself be
   zone-dependent and the fixture would be useless.
2. Write 6 tests:
   - `test_split_es_futures_symbol`: `split_futures_symbol("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)`.
   - `test_split_non_futures_symbol`: `split_futures_symbol("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)`.
   - `test_interval_map_is_total`: every `Interval` member has an entry.
   - `test_raw_bar_to_bar_is_utc_aware`: the produced `Bar.datetime.tzinfo` is `UTC`.
   - `test_raw_bar_epoch_round_trip`: `bar.datetime.timestamp() == raw.epoch_seconds`
     for all 6 fixture rows.
   - `test_naive_local_datetime_recovers_the_same_epoch`: for each fixture epoch,
     build `naive = datetime.fromtimestamp(epoch)` (host-local, mirroring the library),
     then assert `naive.timestamp() == epoch`. Run this test's module under the CI
     timezone matrix.
3. Add no network access and no `tvDatafeed` import to the test module other than for
   the interval-map assertion.

**Success criteria.** 6 tests pass under UTC AND under a non-UTC zone.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q && TZ=America/Chicago uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q` exits 0 and each run prints `6 passed`.

---

### Task 6 — `TradingViewAdapter` (the history port)

**Goal.** A provider that satisfies `IDataProviderPort`, clamps to the configured bar
cap, and never returns an in-progress bar.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_adapter.py`.
- Symbol: `TradingViewAdapter(IDataProviderPort)`.

**Steps.**
1. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_factory: TradingCalendarFactory`.
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - `n_bars = min(n_bars, settings.tradingview_max_bars)`;
   - `code, exchange, fut_contract = split_futures_symbol(symbol)`;
   - `raws = await client.fetch_bars(code, exchange, interval, n_bars, fut_contract)`;
   - map each through `raw_bar_to_bar`;
   - resolve `calendar = await calendar_factory.for_symbol(symbol)` and DROP any bar
     whose `datetime >= calendar.bar_start(datetime.now(UTC), interval)` — that is the
     in-progress bar. Log the dropped count at DEBUG, mirroring
     `binance_adapter.py`'s `binance.in_progress_bar_filtered`;
   - return the list ascending by `datetime`.
3. `search_symbols(query)` returns `[]` and logs one DEBUG. Symbol search stays a
   Binance capability; the routing adapter already delegates search to the crypto
   primary (Phase 4 Task 4 step 3).
4. `close()` is a no-op coroutine.
5. Log one INFO `tradingview.fetch_completed` per call with symbol, interval and bar
   count — one-shot per symbol per interval per cron tick, which is within the
   CLAUDE.md log-frequency rule. Never log the raw payload above DEBUG.

**Success criteria.** The adapter clamps `n_bars` and drops the in-progress bar.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q` exits 0 and prints `5 passed` (tests written in Task 7).

---

### Task 7 — Adapter tests against a fake client

**Goal.** Adapter behaviour is pinned with no network access.

**Target files and symbols.**
- New file `tests/core_test/infra/tradingview/test_tradingview_adapter.py`.

**Steps.**
1. Build a `FakeTradingViewClient` implementing `ITradingViewClient` from the JSON
   fixture.
2. Write 5 tests: `test_n_bars_is_clamped_to_max_bars`,
   `test_futures_symbol_is_split_with_fut_contract_1`,
   `test_in_progress_bar_is_dropped`,
   `test_returned_bars_are_utc_aware_and_ascending`,
   `test_empty_client_result_returns_empty_list`.
3. `test_in_progress_bar_is_dropped` must freeze "now" by injecting a stub calendar
   whose `bar_start` returns a fixed instant, so the test does not depend on the clock.

**Success criteria.** 5 tests pass with no network access.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q` exits 0 and prints `5 passed`.

---

### Task 8 — Register TradingView in DI

**Goal.** `INDEX_FUTURE` symbols route to TradingView; crypto still routes to Binance.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` — `get_data_provider` (edited in
  Phase 4 Task 7).

**Steps.**
1. Add `"tradingview": TradingViewAdapter(client=TvDatafeedClient(settings=settings), settings=settings, calendar_factory=calendar_factory)`
   to the `providers` dict, and add `calendar_factory: TradingCalendarFactory` to the
   provider method signature so Dishka injects it.
2. Change nothing else. The asset-class map in `Settings` already points
   `INDEX_FUTURE` at `["tradingview"]`.
3. Confirm the `providers` dict is the ONLY place in `src/` that names the string
   `"tradingview"` outside `core/infra/tradingview/` and `core/config.py`.

**Success criteria.** The container resolves and one adapter entry was the whole change.

**Verify.** `uv run pytest tests/app_test/integration/ -q && test "$(grep -rln '"tradingview"' src/ | grep -vc -e '^src/pocketquant/app/di/' -e '^src/pocketquant/core/config.py' -e '^src/pocketquant/core/infra/tradingview/')" = "0"` exits 0.

---

### Task 9 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist in both `symbols`
and `tracked_symbols` with the right asset class, calendar and contract spec.

**Target files and symbols.**
- New file `scripts/seed_index_futures.py`.
- Collections: `symbols`, `tracked_symbols`.
- Repositories: `SymbolRepository.upsert`, `TrackedSymbolRepository.upsert`.

**Steps.**
1. Follow `scripts/README.md` conventions: environment-only configuration, dry-run by
   default, `--apply` to write.
2. Define the three records inline:
   | symbol | name | multiplier | tick_size | lot_step |
   |---|---|---|---|---|
   | `ES1!:CME_MINI` | E-mini S&P 500 continuous | 50.0 | 0.25 | 1.0 |
   | `NQ1!:CME_MINI` | E-mini Nasdaq-100 continuous | 20.0 | 0.25 | 1.0 |
   | `YM1!:CBOT_MINI` | E-mini Dow continuous | 5.0 | 1.0 | 1.0 |
   All three get `asset_class=AssetClass.INDEX_FUTURE`,
   `calendar_id="CME_GLOBEX_EQUITY"`, `currency="USD"`.
3. Use `SymbolRepository.upsert` (the full `$set` form) — this is the deliberate
   metadata write, unlike the sync path which now uses `touch`.
4. Use `TrackedSymbolRepository.upsert` with `seeded_from="script"`.
5. Print each symbol and its resulting `asset_class`/`calendar_id`.
6. Add a line for the script to `scripts/README.md`.

**Success criteria.** All three symbols validate through the widened regexes and are
persisted with `asset_class=index_future`.

**Verify.** `uv run python -c "
from pocketquant.core.domain.symbol.entities import COMPOSITE_SYMBOL_RE, COMPOSITE_SYMBOL_PATTERN
syms = ['ES1!:CME_MINI','NQ1!:CME_MINI','YM1!:CBOT_MINI']
print(all(COMPOSITE_SYMBOL_RE.match(s) and COMPOSITE_SYMBOL_PATTERN.match(s) for s in syms))"` prints `True`.

---

### Task 10 — Initial backfill to the configured cap

**Goal.** Each futures symbol has history at every timeframe up to the bar cap, and
the cron accumulates from there.

**Target files and symbols.**
- Endpoint `POST /api/v1/market-data/tracked-symbols/{symbol}/backfill`
  (`src/pocketquant/app/routes/tracked_symbols.py:82-108`).
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py` —
  `BackfillTrackedSymbolCommand.resolved_mode` (lines 77-80).

**Steps.**
1. In `resolved_mode`, return `"direct"` for `DAY_1` when the symbol's calendar is not
   the 24/7 one. The simplest correct place is the service: in
   `TrackedSymbolBackfillService.run`, after resolving the calendar, override
   `mode = "direct"` when `cmd.interval is Interval.DAY_1 and calendar.calendar_id != CALENDAR_CRYPTO_24_7`.
   Add a comment: cascading a futures daily bar across UTC midnight produces a bar
   that never matches the vendor chart.
2. Run the backfill for each of the three symbols at 1m, 5m, 15m, 1h, 4h, 1d, 1w with
   `n` equal to `tradingview_max_bars`. The route caps `n` at 5000
   (`tracked_symbols.py:90`), which matches the default cap.
3. Record the resulting bar counts per symbol and interval.

**Success criteria.** `bars` count for `ES1!:CME_MINI` at 1m equals
`min(tradingview_max_bars, available)`, and 1d bars open at 17:00 America/Chicago.

**Verify.** `curl -s "http://localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1d?limit=3" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['count'], [b['datetime'] for b in d['data']])"` prints a count of `3` and three datetimes ending in `22:00:00Z` or `23:00:00Z`.

---

### Task 11 — End-to-end futures sync test

**Goal.** One automated test drives a futures symbol through the whole pipeline with a
stubbed provider.

**Target files and symbols.**
- New file `tests/app_test/integration/test_futures_sync_end_to_end.py`.

**Steps.**
1. Build the app through `tests/app_test/integration/app_factory.py` against the
   testcontainer Mongo and Redis.
2. Seed `ES1!:CME_MINI` directly through `SymbolRepository.upsert` and
   `TrackedSymbolRepository.upsert` with the CME calendar and the ES spec.
3. Register a stub `IDataProviderPort` in the container that returns session-aligned
   1h bars for a known CME session (for example 2026-06-10, whose session opens at
   `session_open(date(2026,6,10))`).
4. Run `SyncService.sync_one` for 1h and assert: zero bars are dropped as misaligned;
   the persisted bars carry `calendar_id="CME_GLOBEX_EQUITY"`; a 1d sync persists a
   bar whose `session_date` equals `2026-06-10`.
5. Run `check_integrity` for 1m over a window containing a weekend and assert
   `missing_count == 0`.
6. Run `emit_no_progress` with a closed instant and assert no WARNING is emitted
   (use `caplog`).

**Success criteria.** 4 tests pass.

**Verify.** `uv run pytest tests/app_test/integration/test_futures_sync_end_to_end.py -q` exits 0 and prints `4 passed`.

---

### Task 12 — Phase gate: one live week

**Goal.** Prove G1 and the quiet-weekend property on real data.

**Target files and symbols.** None (verification only).

**Steps.**
1. Deploy and let the cron run for one full week including a weekend.
2. Query the logs for `misaligned_bars_dropped`, `integrity.issues_found`,
   `no_progress`, `stuck_threshold_crossed` and `partial_aggregate` scoped to
   `ES1!:CME_MINI`. The count must be zero for each.
3. Point `sync_verify_cascade` at `ES1!:CME_MINI` for 24 consecutive runs and confirm
   `divergent_fraction = 0.0`.
4. During a live session, confirm G1.
5. Record all numbers in the phase completion note.

**Success criteria.** Zero anomaly events, zero cascade divergence, G1 met.

**Verify.** `curl -s "http://localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1m?limit=1" | python3 -c "
import sys, json, datetime as d
b = json.load(sys.stdin)['data'][0]
age = (d.datetime.now(d.UTC) - d.datetime.fromisoformat(b['datetime'].replace('Z','+00:00'))).total_seconds()
print('FRESH' if age <= 720 else f'STALE {age}')"` prints `FRESH` while a CME session is open.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The scraper's login breaks (open issues Dec 2025, Mar 2026) | High over time | Medium | Task 3 degrades to anonymous mode with a WARNING and never crashes; `ITradingViewClient` makes a replacement one class |
| `tvDatafeed.Interval` member names differ from the assumed map | Medium | High — every fetch raises | Task 4 step 5 and its Verify assert against the installed package |
| The DataFrame index is tz-aware on some library version | Low | Medium | Task 3 step 5 branches on `tzinfo` |
| The git dependency breaks the Docker build (no `git` in the runtime stage) | Medium | High — image fails to build | `git` IS installed in the builder stage (`deploy/Dockerfile:9-11`) and `uv sync` runs there; the runtime stage only copies `.venv`. Verify the image builds before deploying. |
| TradingView rate-limits or bans the account | Medium | Medium | `tradingview_poll_seconds` defaults to 60; history fetches are once per cron tick |

**Rollback.** Remove the `"tradingview"` entry from the DI `providers` dict (Task 8) —
the three futures symbols then get an empty provider list and sync becomes a no-op,
while crypto is untouched. Deleting the seeded symbols is a `tracked_symbols` delete
through the admin route.

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

=== FILE: phase-06-quote-adapter-and-contract-math.md ===
---
phase: 6
title: "Polling Quote Adapter and Contract-Aware Trading Math"
status: pending
priority: P1
effort: "1.5d"
dependencies: [5]
---

## Context

(Advice Phase 5.) Two independent pieces that together deliver G2 and G3: a realtime
quote adapter that polls TradingView while the session is open, and contract-aware
PnL so that a 0.25-point ES move on 2 contracts is 25.00 USD rather than 0.50.

The margin accounting that shipped in plan `260628-2013`
(`docs/journals/2026-06-28-paper-broker-futures-accounting.md`) stays exactly as it
is. Only the unit conversion is added. The PnL arithmetic lives in two places in
`PositionAggregate` — `reduce_quantity` (the `realized` computation) and the
`unrealized_pnl` property — both of which multiply `_calculate_pnl_per_unit(...)` by
`quantity`. Putting the multiplier on the aggregate keeps the change to those two
lines instead of scattering it across the broker.

## Tasks

### Task 1 — `PerContractCommissionModel`

**Goal.** Futures commission is charged per contract, not as a percentage of notional.

**Target files and symbols.**
- `src/pocketquant/core/domain/trading/commission_model.py` — the `CommissionModel`
  Protocol (lines 4-5) and `PercentageCommissionModel` (lines 8-13).

**Steps.**
1. Add:
   ```python
   class PerContractCommissionModel:
       """Flat fee per contract, the CME convention. `quantity` is contracts."""
       def __init__(self, usd_per_contract: float) -> None:
           self._usd_per_contract = usd_per_contract

       def compute(self, price: float, quantity: float) -> float:
           return abs(quantity) * self._usd_per_contract
   ```
2. Export it from `src/pocketquant/core/domain/trading/__init__.py` alongside
   `PercentageCommissionModel`.
3. Do not change `PercentageCommissionModel` or the Protocol.

**Success criteria.** `PerContractCommissionModel(2.5).compute(4500.0, 2) == 5.0`.

**Verify.** `uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q` exits 0.

---

### Task 2 — Contract multiplier on `PositionAggregate`

**Goal.** Realized and unrealized PnL are expressed in account currency for any
contract size.

**Target files and symbols.**
- `src/pocketquant/core/domain/position/entities.py` — `PositionAggregate` fields
  (lines 28-44), `open` factory (lines 47-89), `reduce_quantity` (lines 127-190, the
  `realized = pnl_per_unit * quantity` line), `unrealized_pnl` property (lines 223-227),
  `market_value` (line 235), `cost_basis` (line 239), `to_mongo` (lines 245-263),
  `from_mongo` (lines 265-286).

**Steps.**
1. Add a field `multiplier: float = 1.0` with the docstring "account currency per 1.0
   of price move per contract; 1.0 for linear instruments".
2. Add `multiplier: float = 1.0` as a keyword parameter of the `open` classmethod and
   pass it into the constructor.
3. In `reduce_quantity`, change `realized = pnl_per_unit * quantity` to
   `realized = pnl_per_unit * quantity * self.multiplier`.
4. In the `unrealized_pnl` property, change the return to
   `self._calculate_pnl_per_unit(self.current_price) * self.quantity * self.multiplier`.
5. Leave `market_value` and `cost_basis` as `quantity * price` — they are notional
   quantities used for display and the existing margin checks, and changing them
   would alter the shipped margin accounting. Add a one-line comment stating that.
6. Write `multiplier` in `to_mongo` and read it in `from_mongo` with
   `doc.get("multiplier", 1.0)`, so existing position documents load as linear.
7. `TradeClosedEvent.pnl` already carries `realized`, so it inherits the multiplier
   with no further change. Confirm by reading `reduce_quantity`'s event construction.

**Success criteria.** A 2-contract ES position entering 4500.00 and exiting 4500.25
with `multiplier=50.0` realizes exactly 25.00.

**Verify.** `uv run python -c "
from pocketquant.core.domain.position.entities import PositionAggregate
from pocketquant.core.domain.position.enums import PositionSide
p = PositionAggregate.open(subscription_id='s', symbol='ES1!:CME_MINI', side=PositionSide.LONG, entry_price=4500.00, quantity=2, multiplier=50.0)
p.reduce_quantity(2, 4500.25)
print(round(p.realized_pnl, 6))"` prints `25.0`.

---

### Task 3 — Thread `ContractSpec` through the paper broker

**Goal.** A paper broker created for a futures symbol prices its fills in contracts.

**Target files and symbols.**
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` — `__init__`
  (lines 108-125), `_open_position` (line 561), `_can_afford` (lines 487-500),
  `_commission` (lines 484-485).
- `src/pocketquant/core/infra/brokers/broker_factory.py` — `BrokerFactory.create`,
  the `"paper"` branch (lines 32-44).
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py` — `create_broker`
  (lines 111-136) and the placeholder at line 151.

**Steps.**
1. Add a `contract_spec: ContractSpec = LINEAR_SPEC` keyword parameter to
   `PaperBrokerAdapter.__init__` and store it as `self._contract_spec`.
2. In `_open_position`, pass `multiplier=self._contract_spec.multiplier` into
   `PositionAggregate.open(...)`.
3. In `_can_afford` (line 499-500), keep the notional check on
   `fill_price * order.quantity` — that is the margin accounting that shipped in plan
   `260628-2013` and is explicitly out of scope. Add a one-line comment saying so.
4. In `BrokerFactory.create`, read `config.get("contract_spec")` and
   `config.get("commission_per_contract")`. When `commission_per_contract` is not
   `None`, build a `PerContractCommissionModel`; otherwise keep
   `PercentageCommissionModel(bps=commission_bps)`. Pass the spec through.
5. In `BacktestSandboxAppService.create_broker`, add a
   `contract_spec: ContractSpec = LINEAR_SPEC` parameter and pass it through. Leave
   the `placeholder_broker` at line 151 on the default linear spec.
6. Every new parameter defaults to the linear spec, so every existing caller and test
   keeps its current behaviour.

**Success criteria.** Existing paper-broker tests pass unchanged and a spec-carrying
broker produces contract-scaled PnL.

**Verify.** `uv run pytest tests/core_test/infra/brokers/ tests/backtest_test/engine/ -q` exits 0.

---

### Task 4 — Contract-aware position sizing

**Goal.** Sizing for a futures symbol yields a whole number of contracts.

**Target files and symbols.**
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py` —
  `PositionCalculatorDomainService.calculate` (lines 17-46).

**Steps.**
1. Add a keyword parameter `contract_spec: ContractSpec | None = None` after
   `commission_model`.
2. After `size = min(risk_amount / price_risk, cap)` (line 41), insert:
   ```python
   if contract_spec is not None and contract_spec.multiplier != 1.0:
       size = size / contract_spec.multiplier
   if contract_spec is not None and contract_spec.lot_step:
       size = math.floor(size / contract_spec.lot_step) * contract_spec.lot_step
   ```
   Dividing by the multiplier first is what makes `risk_amount / price_risk` mean
   "contracts" rather than "index points of exposure".
3. Recompute `notional = size * entry_price * (contract_spec.multiplier if contract_spec else 1.0)`.
4. Return `PositionCalculation(0.0, 0.0, 0.0, 0.0)` when the floor produces `0` — a
   sub-one-contract signal must not open a fractional futures position.
5. Import `math`. Keep the default path (`contract_spec=None`) byte-identical for crypto.

**Success criteria.** With the ES spec and a balance that affords 1.7 contracts, the
result is 1.0.

**Verify.** `uv run pytest tests/backtest_test/engine/test_r7_worked_example_defaults.py -q` exits 0.

---

### Task 5 — Wire the spec into the strategy and backtest paths

**Goal.** A strategy or backtest on `ES1!:CME_MINI` picks up the ES spec without the
caller naming it.

**Target files and symbols.**
- `src/pocketquant/engine/strategy/strategy_app_service.py` —
  `_get_or_create_broker` (lines 421-432) and the sizing call site (grep for
  `PositionCalculatorDomainService.calculate`).
- `src/pocketquant/core/domain/backtest/config.py` — `BacktestConfig` (lines 8-40).
- `src/pocketquant/engine/backtest/backtest_dispatch.py` — the `create_broker` call at
  line 92.
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py` — the `create_broker`
  call at line 106.

**Steps.**
1. Add `contract_spec: ContractSpec = LINEAR_SPEC` to `BacktestConfig` as the last
   field (dataclass ordering: it has a default, so it may follow the existing
   defaults).
2. In `backtest_dispatch.py` and `backtest_strategy_loader.py`, resolve the symbol's
   spec via `SymbolLookupHelper` before building the config, and pass it into both
   `BacktestConfig(...)` and `sandbox.create_broker(...)`.
3. In `strategy_app_service._get_or_create_broker`, the broker is shared across
   subscriptions of the same broker type, so it CANNOT carry a per-symbol spec.
   Instead: keep the broker linear and resolve the spec per order. Read the sizing
   call site and pass `contract_spec=` into
   `PositionCalculatorDomainService.calculate`, and pass `multiplier=` through the
   order into `_open_position`. If that thread proves to need more than three call
   edits, STOP and follow the Failure Protocol — a broker keyed by
   `(broker_type, contract_spec)` is the alternative and is a design decision, not an
   improvisation.
4. Do not add a `contract_spec` field to `OrderAggregate`. The order carries a
   quantity in contracts; the spec belongs to the symbol.

**Success criteria.** A backtest config for a futures symbol carries the ES spec and
the broker prices fills with it.

**Verify.** `uv run pytest tests/backtest_test/ -q` exits 0.

---

### Task 6 — Contract math tests

**Goal.** G2's worked example is a test, not a manual observation.

**Target files and symbols.**
- New file `tests/core_test/infra/brokers/test_paper_broker_contract_spec.py`.

**Steps.**
1. Write 6 tests:
   - `test_es_round_trip_realizes_25_usd`: 2 contracts, entry 4500.00, exit 4500.25,
     `multiplier=50.0`, zero commission → realized PnL exactly 25.00.
   - `test_es_round_trip_with_per_contract_commission`: the same with
     `PerContractCommissionModel(2.5)` → realized 25.00 and total commission 10.00
     (2 contracts entry + 2 contracts exit).
   - `test_nq_multiplier_20`: 1 contract, 1.00-point move → 20.00.
   - `test_ym_multiplier_5`: 1 contract, 1.00-point move → 5.00.
   - `test_linear_default_is_unchanged`: `multiplier=1.0` reproduces the current
     crypto arithmetic.
   - `test_equity_curve_has_no_jump_at_fill_beyond_commission`: assert the balance
     delta at fill time equals `realized_pnl - commission`.

**Success criteria.** 6 tests pass.

**Verify.** `uv run pytest tests/core_test/infra/brokers/test_paper_broker_contract_spec.py -q` exits 0 and prints `6 passed`.

---

### Task 7 — `TradingViewQuoteAdapter` (the realtime port)

**Goal.** A polling quote source that is quiet while the market is closed and emits
the existing quote-dict contract.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_quote_adapter.py`.
- Symbol: `TradingViewQuoteAdapter`, satisfying the 9-member
  `IRealtimeQuoteProviderPort` Protocol.
- Contract reference: the quote dict produced by
  `src/pocketquant/core/infra/binance/binance_mappers.py:93-106` — keys `symbol`,
  `timestamp`, `last_price`, `volume`, `bid`, `ask`, `change`, `change_percent`,
  `open_price`, `high_price`, `low_price`, `prev_close`.

**Steps.**
1. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_factory: TradingCalendarFactory`.
2. `subscribe(symbol, callback)` records `(symbol, callback)` and starts one
   `asyncio.Task` per symbol. `unsubscribe(symbol)` cancels that task and removes the
   entry. Return the composite symbol as the subscription key, matching
   `BinanceWebSocketAdapter`.
3. Each poll task loops: resolve the calendar; when
   `calendar.is_open(datetime.now(UTC))` is False, sleep
   `settings.tradingview_poll_seconds` and continue WITHOUT calling the client; when
   open, fetch the latest 1m bar, and if its `close` differs from the previously
   emitted close, build the quote dict and `await` the callback.
4. Build the quote dict with `timestamp` set to the bar's UTC `datetime`,
   `last_price` to its close, `volume` to its volume, and every other key `None` —
   exactly the Binance shape, so `QuoteAppService.on_quote_update` needs no change.
   Note in the docstring that `volume` here is a bar total, not a per-tick delta, and
   that `tick_count` is therefore 1 per poll.
5. `last_tick_at` is set on every successful emission. `is_connected()` returns
   `client.is_authenticated() and bool(self._tasks)`.
6. `run_forever()` awaits an `asyncio.Event` that is never set, so
   `WsSubscriptionAppService` and the lifespan task management behave as they do for
   the WS adapter; let `CancelledError` propagate.
7. `connect()` and `disconnect()` start and cancel all tasks respectively.
8. Log per-poll at DEBUG only.
9. Register it in `src/pocketquant/app/di/market_data.py` inside the
   `RoutingRealtimeQuoteAdapter` providers dict under the key `"tradingview"`.

**Success criteria.** With a closed calendar the poll task issues zero client calls;
with an open calendar a price change emits one quote dict.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q` exits 0 and prints `5 passed` (tests written in Task 8).

---

### Task 8 — Quote adapter tests and a relaxed staleness threshold

**Goal.** The polling adapter is covered, and the 30s staleness watchdog does not fire
on a 60s poll cadence.

**Target files and symbols.**
- New file `tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py`.
- `src/pocketquant/core/infra/binance/binance_websocket_adapter.py` —
  `_stale_connection_watchdog` (around line 237). Read it and note its threshold.
- `src/pocketquant/engine/market_data/app_services/quote_app_service.py` — any
  staleness check on `provider.last_tick_at`.

**Steps.**
1. Write 5 tests with a fake client and a stub calendar:
   `test_closed_market_makes_no_client_call`,
   `test_open_market_emits_quote_on_price_change`,
   `test_unchanged_close_emits_nothing`,
   `test_quote_dict_matches_the_binance_key_set`,
   `test_unsubscribe_cancels_the_poll_task`.
2. Read `_stale_connection_watchdog` and any `last_tick_at` staleness check in
   `quote_app_service.py`. The Binance watchdog belongs to the Binance adapter and is
   not shared, so no change is needed there. If `QuoteAppService` applies a global
   staleness threshold to `provider.last_tick_at`, raise it to
   `max(existing, settings.tradingview_poll_seconds * 3)` and add a comment naming the
   polling provider as the reason. If it does not, change nothing and note that in the
   phase completion note.

**Success criteria.** 5 tests pass and no false staleness alert appears in a
60s-cadence run.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/ tests/app_test/unit/market_data/test_quote_app_service.py -q` exits 0.

---

### Task 9 — Phase gate: G2 and G3

**Goal.** Prove the two user-facing goals on real data.

**Target files and symbols.** None (verification only).

**Steps.**
1. G2: run a paper strategy on `ES1!:CME_MINI` for one full CME session. Execute one
   round trip of 2 contracts entering at 4500.00 and exiting at 4500.25 (or the
   nearest real prices) and confirm the recorded realized PnL is
   `(exit - entry) * 50 * 2` minus commission, and that the equity curve has no jump
   at fill time other than commission.
2. G3: run a 1h backtest on `ES1!:CME_MINI` over the available window. Confirm the
   reported `periods_per_year` is the session-derived value (roughly 5796), not 8760,
   and that dollar PnL equals points x 50 x contracts.
3. Record both numbers in the phase completion note.

**Success criteria.** Both match to the cent.

**Verify.** `uv run pytest tests/ -q && uv run ruff check . && uv run lint-imports` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A shared paper broker per broker type cannot carry a per-symbol spec | High | Medium | Task 5 step 3 names the limit and routes the decision to the Failure Protocol rather than improvising |
| `market_value`/`cost_basis` left unmultiplied desynchronises the margin check | Medium | Medium | Task 2 step 5 makes it a deliberate, commented decision, preserving the shipped accounting |
| Polling at 60s misses intra-bar moves, so paper fills are optimistic | High | Low | Stated trade-off; `tradingview_delayed_data` is surfaced in the UI in Phase 7 |
| A persisted position document without `multiplier` loads wrong | Low | High | Task 2 step 6 defaults it to `1.0` |

**Rollback.** Task 7 and its DI registration revert independently of Tasks 1-6. Tasks
1-6 are additive with linear defaults, so reverting them restores the previous
arithmetic exactly.

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

=== FILE: phase-07-ui-docs-and-metrics.md ===
---
phase: 7
title: "UI, Docs and Success-Metric Run-Through"
status: pending
priority: P2
effort: "1d"
dependencies: [6]
---

## Context

(Advice Phase 6.) The three futures symbols must be selectable everywhere a crypto
symbol is, the SPA must stop presenting Binance as the only possible venue, the
"closed" state added in Phase 3 must be visible, and the documentation must describe
the provider table and the new settings. The phase closes with a run-through of the
18 success metrics.

## Tasks

### Task 1 — Generic SPA placeholders

**Goal.** No input hint in the SPA implies Binance is the only venue.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx` — lines 21, 23, 24, 72.
- `web/src/components/backtest/backtest-form.tsx` — line 72.
- `web/src/lib/symbol-format.ts` — the module docstring at line 2.
- `web/src/components/chart/trading-chart.tsx` — the prop docstring at line 38.
- `web/src/components/controls/symbol-selector.tsx` — line 6.
- `web/src/components/ticker-widget/ticker-widget.tsx` — line 6.
- `web/src/types/market-data.ts` — line 20.
- `web/src/types/quote.ts` — line 3.

**Steps.**
1. Replace the user-visible strings in `add-symbol-dialog.tsx` (the error messages at
   lines 23-24 and the `placeholder` at line 72) with
   `CODE:EXCHANGE (e.g. BTCUSDT:BINANCE or ES1!:CME_MINI)`.
2. Do the same for the error message in `backtest-form.tsx` line 72.
3. In every docstring listed above, change the example from
   `"BTCUSDT:BINANCE"` to `"BTCUSDT:BINANCE" or "ES1!:CME_MINI"`.
4. Do NOT change the default symbol values at `web/src/routes/__root.tsx:17`,
   `web/src/routes/index.tsx:21` or `web/src/components/backtest/backtest-form.tsx:44`
   — the default landing symbol stays `BTCUSDT:BINANCE`.
5. Confirm the composite parser at `web/src/lib/symbol-format.ts:6-10` splits on the
   FIRST `:` and therefore handles `ES1!:CME_MINI` with no change.

**Success criteria.** The SPA builds and no user-visible hint names only Binance.

**Verify.** `cd web && npm run build` exits 0.

---

### Task 2 — Exchange badge and closed-market state

**Goal.** A futures symbol renders its exchange badge and shows CLOSED rather than a
red stuck badge outside session hours.

**Target files and symbols.**
- `web/src/components/monitor/data-health-row.tsx` — lines 50, 55, 72
  (`StuckBadge show={!!s.is_stuck}`).
- `web/src/components/monitor/format-helpers.ts` — line 19.
- `web/src/types/market-data.ts` — the `SyncStatus` interface (line 88).
- `web/src/lib/datetime.ts` — `ageColorClass` (lines 88-97).

**Steps.**
1. These edits were started in Phase 3 Task 5. Finish them: when
   `s.is_market_open === false`, render a neutral `CLOSED` badge instead of
   `StuckBadge`, and return `'age-neutral'` from the status helper.
2. In `ageColorClass`, add an optional third parameter `isMarketOpen?: boolean` and
   return `'age-neutral'` when it is explicitly `false`. Update the call sites — grep
   for `ageColorClass(` across `web/src`.
3. Confirm the exchange badge component renders `CME_MINI` and `CBOT_MINI` — it uses
   `parseSymbol(...).exchange`, which is venue-agnostic.

**Success criteria.** With `is_market_open: false` the row shows CLOSED, not STUCK.

**Verify.** `cd web && npm run build` exits 0 and `grep -c "is_market_open" web/src/components/monitor/data-health-row.tsx web/src/types/market-data.ts` reports at least `1` per file.

---

### Task 3 — Provider status on `/health`

**Goal.** "Why are there no ES bars" is answered by one request.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py` — `register_health_checks` (lines 267-270)
  and the `health_check` route (around line 366).

**Steps.**
1. Add a health check named `market_data_providers` that reports, per registered
   provider id: whether it is authenticated (for TradingView, `client.is_authenticated()`;
   for Binance, `True`), and per tracked symbol the resolved provider id and
   `calendar.is_open(now)`.
2. Keep the payload bounded: report at most the tracked symbols, never bar arrays.
3. Register it beside the existing `database` and `redis` checks with
   `hc.register("market_data_providers", ...)`.
4. Report a degraded TradingView login as a non-fatal `degraded` status, not as
   unhealthy — the container health check at `deploy/Dockerfile:53-54` must not start
   flapping because the scraper lost its session.

**Success criteria.** `/health` includes a `market_data_providers` entry and the
overall status stays healthy when TradingView is degraded.

**Verify.** `curl -s http://localhost:41921/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('market_data_providers' in json.dumps(d))"` prints `True`.

---

### Task 4 — Update the architecture documentation

**Goal.** The docs describe the provider table, the calendar port and the new
settings.

**Target files and symbols.**
- `docs/system-architecture.md` — `## Where Does X Live?` (line 479),
  `## Dependency Injection (Dishka)` (line 670), `## Configuration` (line 773),
  `## Dependencies` (line 777), `## Ops Context` external services (line 796), and
  the Symbol description at line 173.
- `README.md` — the settings list and the line claiming 7 import-linter contracts.
- `docs/visuals/collection-erd.mmd` — line 20 (`string asset_type`).

**Steps.**
1. In `## Where Does X Live?`, add five rows:
   | Trading calendar port + 24/7 implementation | `core/domain/market_data/trading_calendar_port.py`, `core/domain/market_data/continuous_24x7_calendar.py` |
   | CME Globex equity calendar | `core/infra/calendars/cme_globex_calendar_adapter.py` |
   | Provider routing adapters | `core/infra/market_data/` |
   | TradingView client, mappers, adapters | `core/infra/tradingview/` |
   | Asset class + contract spec | `core/domain/shared/enums.py`, `core/domain/symbol/value_objects.py` |
2. In the DI section, update the provider description: `InfrastructureProvider` now
   builds a `RoutingDataProviderAdapter` over `{binance, tradingview}` and
   `MarketDataProvider` builds a `RoutingRealtimeQuoteAdapter`.
3. In `## Configuration`, add `MARKET_DATA_PROVIDERS`, `SYMBOL_PROVIDER_OVERRIDES`,
   `TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD`, `TRADINGVIEW_AUTH_TOKEN`,
   `TRADINGVIEW_MAX_BARS`, `TRADINGVIEW_POLL_SECONDS`, `TRADINGVIEW_DELAYED_DATA` and
   `TZ` (names only, never values).
4. In `## Dependencies`, add `pandas_market_calendars` (CME session calendar) and
   `tvdatafeed` (TradingView scraper, installed from git).
5. In `## Ops Context`, add TradingView to the external-services list with a note that
   it is an unofficial scraper with no stability promise.
6. Fix line 173: `Symbol` now carries `asset_class`, `calendar_id` and `contract_spec`
   instead of `asset_type`.
7. In `docs/visuals/collection-erd.mmd` line 20, replace `string asset_type` with
   `string asset_class`, `string calendar_id` and `object contract_spec`.
8. In `README.md`, list the new settings by name and correct "7 import-linter
   contracts" to "8" (`pyproject.toml` defines 8).
9. `docs/vi/system-architecture.md:173` mirrors line 173 of the English file — update
   it too, keeping the Vietnamese wording.

**Success criteria.** No document still says `asset_type` for the `symbols` collection.

**Verify.** `grep -rn "asset_type" docs/ README.md web/src src/ | wc -l` prints `0`.

---

### Task 5 — Journal the timezone and calendar decision

**Goal.** The reasoning behind the UTC invariant and the calendar port survives in the
repository.

**Target files and symbols.**
- New file `docs/journals/2026-09-21-asset-class-trading-calendar.md`
  (follow the format of `docs/journals/2026-06-28-paper-broker-futures-accounting.md`).

**Steps.**
1. Record: the `CronTrigger` host-zone bug and how it was found; the
   `tz_aware` + `integrity_jobs` commit-ordering constraint and why splitting it
   triggers a full resync; why calendar rules live in code while `calendar_id` lives
   on the symbol record; why realtime routing has no fallback chain; why the
   TradingView mapper recovers the epoch through `.timestamp()` instead of trusting
   the library's index.
2. Do not name plan ids, phase numbers or audit labels in any source comment — those
   belong here, in the journal.

**Success criteria.** The journal exists and covers the five points.

**Verify.** `test -f docs/journals/2026-09-21-asset-class-trading-calendar.md && grep -c "tz_aware" docs/journals/2026-09-21-asset-class-trading-calendar.md` prints a number of at least `1`.

---

### Task 6 — Success-metric run-through

**Goal.** Every stated metric is measured and recorded, not assumed.

**Target files and symbols.**
- New file `plans/260921-1436-asset-class-index-futures/completion-report.md`.

**Steps.**
1. Measure and record each of the following, with the command used and the observed
   value:
   1. `TZ=Asia/Saigon` startup refuses; `TZ=UTC` starts.
   2. Identical cron `next_run_time` under the three zones; `sync_backfill` fires at
      03:00 UTC.
   3. On a Thursday-to-Sunday run, the latest `1w` bar for `BTCUSDT:BINANCE` opens on
      the previous Monday 00:00 UTC.
   4. Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
      `stuck_threshold_crossed` and `partial_aggregate` for `ES1!:CME_MINI` over one
      week including a weekend and one early-close holiday.
   5. Futures 1d bars open 17:00 CT and close 16:00 CT on both sides of a DST
      transition, with `session_date` populated.
   6. Golden-file comparison: crypto bars, cascade output and metrics unchanged.
   7. `uv run ruff check .` passes with `DTZ`; `uv run pytest` passes with no added skips.
   8. The DST suite passes: `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
      `session_open(2026-11-02) == 2026-11-01T23:00:00Z`.
   9. G1 during a session.
   10. Weekend quiet: `job_history` shows `sync_1m` runs for the three futures symbols
       with a skipped-closed detail and zero `no_progress` entries.
   11. `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0` for
       24 consecutive runs, and 4h bar datetimes are session-open anchored.
   12. Backfill depth at 1m equals `min(tradingview_max_bars, available)` and grows by
       about 1,380 per trading day.
   13. G2.
   14. G3.
   15. G4: a mock third provider registered via config only receives fetches for an
       overridden symbol, and the change touches no file under `engine/` or `app/`.
   16. G5: `sync_1m` for BTC/ETH/SOL produces the same `synced_count` and bar values
       as before; crypto `periods_per_year` at 1m is still 525600.
   17. G6: the app refuses to start on a non-UTC host and the DST suite passes.
   18. Secrets: the credential grep below finds only field declarations.
2. For any metric that cannot be measured yet (a holiday that has not occurred, a
   full week that has not elapsed), record the date on which it will be measured
   rather than marking it passed.

**Success criteria.** All 18 metrics are recorded with a command and a value.

**Verify.** `git grep -i "tradingview_.*=" -- ':!*.md' | grep -v "SecretStr\|str | None\|int =\|bool =" | wc -l` prints `0`.

---

### Task 7 — Final full gate

**Goal.** The repository is green on every gate the project defines.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the suite under all three CI timezones.
2. Run ruff, pyright and the import contracts.
3. Build the SPA.
4. Build the Docker image to confirm the git dependency resolves in the builder stage.

**Success criteria.** Every command exits 0.

**Verify.** `uv run pytest tests/ -q && TZ=Asia/Saigon uv run pytest tests/ -q && TZ=America/Chicago uv run pytest tests/ -q && uv run ruff check . && uv run pyright && uv run lint-imports && (cd web && npm run build)` exits 0.

## Risks and rollback

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The `/health` provider check makes a blocking scraper call and the container health check times out | Medium | High — the container restarts in a loop | Task 3 step 1 reads a cached `is_authenticated()` flag; it must never issue a network call |
| A metric cannot be measured because the week or holiday has not passed | High | Low | Task 6 step 2 records the future measurement date rather than a false pass |
| SPA build breaks on the renamed `SymbolInfo` field | Medium | Low | Task 1's Verify builds the SPA |
| Docs drift again after the next change | Medium | Low | The journal in Task 5 records the reasoning, so the next editor has context |

**Rollback.** Every task in this phase is documentation or presentation and can be
reverted individually with no runtime effect, except Task 3, which is removed by
deleting one `hc.register(...)` line.

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
