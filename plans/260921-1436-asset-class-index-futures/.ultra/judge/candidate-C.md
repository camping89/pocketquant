=== FILE: plan.md ===
---
title: "Asset-class model and index futures (ES/NQ/YM) through the existing pipeline"
description: "Make UTC a checked invariant, introduce an asset-class + trading-calendar model, route data providers per asset class, and deliver ES1!/NQ1!/YM1! via TradingView without a parallel futures pipeline."
status: pending
priority: P1
effort: 11.5d
branch: develop
tags: [market-data, asset-class, trading-calendar, timezone, provider-routing, tradingview, futures, backtest]
created: 2026-09-21
blockedBy: []
blocks: []
---

## Overview

PocketQuant is hardwired to one 24/7 crypto venue: DI binds exactly one REST provider and
one WebSocket provider, and the sync, cascade, integrity, freshness, annualization and
paper-broker maths all assume continuous trading and `price x quantity` units. This plan
delivers CME/CBOT continuous front-month index futures (`ES1!:CME_MINI`, `NQ1!:CME_MINI`,
`YM1!:CBOT_MINI`) for charts, live paper trading and higher-timeframe forward-accumulating
backtests, sourced from TradingView, through two generalizations inside the **existing**
pipeline: an asset-class plus trading-calendar model that drives session, annualization
and contract maths, and provider resolution keyed by asset class plus provider id. There
is no parallel futures pipeline; every futures behaviour is a parameter whose default
reproduces today's crypto numbers. The order is risk-retirement order: the UTC invariant
and the routing layer are each provable on the crypto path before a single futures bar
exists, so timezone drift and provider mis-routing are eliminated before the scraper's own
flakiness enters.

**Phase numbering.** The confirmed advice in
`plans/reports/advise-260921-2001-index-futures-data-provider.md` numbers its route Phase 0
through Phase 6. This plan maps advice Phase 0 to plan Phase 1, and so on through advice
Phase 6 to plan Phase 7.

## Phases

| # | Phase | File | Depends on | Effort |
|---|-------|------|-----------|--------|
| 1 | UTC invariant and the two live crypto bugs | [phase-01-utc-invariant-and-crypto-bugs.md](phase-01-utc-invariant-and-crypto-bugs.md) | — | 1.5d |
| 2 | Trading-calendar port and asset-class domain model | [phase-02-calendar-port-and-asset-class-model.md](phase-02-calendar-port-and-asset-class-model.md) | 1 | 2.5d |
| 3 | Thread the calendar through the pipeline (24/7 only) | [phase-03-thread-calendar-through-pipeline.md](phase-03-thread-calendar-through-pipeline.md) | 2 | 2d |
| 4 | Provider routing adapters and settings | [phase-04-provider-routing-adapters.md](phase-04-provider-routing-adapters.md) | 3 | 1d |
| 5 | TradingView history adapter, seed and backfill | [phase-05-tradingview-history-and-backfill.md](phase-05-tradingview-history-and-backfill.md) | 4 | 2d |
| 6 | Polling quotes and contract-aware broker and backtest | [phase-06-quotes-and-contract-aware-trading.md](phase-06-quotes-and-contract-aware-trading.md) | 5 | 1.5d |
| 7 | UI, docs and success-metric run-through | [phase-07-ui-docs-and-metrics.md](phase-07-ui-docs-and-metrics.md) | 6 | 1d |

## Goals

- **G1** Fresh futures bars land within one cron cycle during session hours.
- **G2** A paper ES strategy runs a full session with correct USD PnL.
- **G3** A 1h ES backtest reports dollar PnL and Sharpe consistent with the contract spec.
- **G4** Adding a provider is one adapter plus one config entry, with zero caller edits.
- **G5** BTC/ETH/SOL behaviour and every existing crypto test are unchanged.
- **G6** The app refuses to start on a non-UTC host and the DST-boundary suite passes.

## Success criteria

- `uv run pytest tests/ -q` exits 0 with no test removed or skipped, before and after.
- `uv run ruff check src tests` exits 0 with `DTZ` enabled; `uv run lint-imports` exits 0.
- The unit suite produces identical results under `TZ=UTC`, `TZ=Asia/Saigon` and
  `TZ=America/Chicago`, and every registered cron job reports the same `next_run_time`.
- A golden-file comparison proves crypto bars, cascade output and performance metrics
  are byte-identical across the calendar refactor.
- Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
  `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across one
  full week including a weekend.
- `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0`.
- `git grep -i "tradingview_.*=" -- ':!*.md'` finds only settings field declarations,
  never values.

## Non-goals and constraints

Non-goals: a real futures broker; multi-year 1m futures history (deferred, accepted
trade-off); Databento or IBKR adapters; tick-level fidelity beyond the scraper; modelling
contract roll inside paper positions; redoing the margin accounting shipped in plan
`260628-2013`; any branching on the TradingView plan tier.

Constraints: single uvicorn process; ports in `core/domain`, adapters in `core/infra`, all
repositories in `core.infra.persistence.repositories`; `fastapi` only in `app`
(import-linter, 8 contracts); routes use `FromDishka[...]` with `DishkaRoute`, never
`Depends()`; UUIDv7 primary keys; composite symbol format `{CODE}:{EXCHANGE}`; credentials
only in `../pocketquant-config/`; log level is frequency plus audience; KISS and DRY.

=== FILE: phase-01-utc-invariant-and-crypto-bugs.md ===
---
phase: 1
title: "UTC invariant and the two live crypto bugs"
status: pending
priority: P1
effort: "1.5d"
dependencies: []
---

## Context

The pipeline is UTC by convention, not by construction. `core/infra/scheduling/scheduler.py:79`
declares `timezone="UTC"` on the scheduler, but the `CronTrigger(...)` constructors at
`scheduler.py:219` and `scheduler.py:228` pass no `timezone=`, so APScheduler falls back to
`tzlocal.get_localzone()` and pickles the host zone into the Mongo jobstore. No deploy file
pins `TZ`. The Mongo client is not `tz_aware`, so raw projections return naive datetimes and
`integrity_jobs.py:50` is deliberately naive to match them. Separately,
`core/infra/binance/binance_adapter.py:80-83` floors the 1w cutoff to a Thursday-aligned epoch
week, so from Thursday to Sunday the in-progress Monday weekly kline is persisted partial.

This phase makes UTC a checked invariant at five layers (dependency, container, boot, lint, CI)
and fixes both live crypto bugs. No futures code exists yet; every change here pays for itself
on the crypto path.

**Hard ordering constraint.** Task 4 must land as ONE commit. Flipping
`AsyncMongoClient(tz_aware=True)` without making `integrity_jobs.py:50` aware in the same change
makes the integrity check report every bar missing and triggers a full resync of every symbol.

## Tasks

### Task 1.1 — Guarantee the IANA time-zone database is present at runtime

**Goal.** `zoneinfo.ZoneInfo("America/Chicago")` resolves in every environment, including the
slim production container.

**Target files and symbols.**
- `pyproject.toml` -> `[project] dependencies` list.
- `uv.lock` (regenerated).

**Steps.**
1. Open `pyproject.toml`. In the `[project] dependencies` array, after the `"dishka>=1.9.1",`
   entry, add the line `"tzdata>=2025.3",`.
2. Add a comment directly above it: `# Explicit: the transitive tzdata pin is win32/emscripten-only, and the python:3.14-rc-slim runtime image carries no OS tz database.`
3. Run `uv sync` to regenerate `uv.lock`.

**Success criteria.** `tzdata` appears in `uv.lock` without a `sys_platform` marker on the
pocketquant dependency edge, and `ZoneInfo("America/Chicago")` constructs without raising.

**Verify.**
`uv run python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Chicago').key)"`
exits 0 and prints exactly `America/Chicago`.

### Task 1.2 — Pin `TZ=UTC` in the container, the prod compose file and local dev

**Goal.** No process that runs this application inherits a host time zone.

**Target files and symbols.**
- `deploy/Dockerfile` -> the `ENV` block in the `runtime` stage (currently lines 45-47).
- `deploy/compose.prod.yml` -> the `app:` service (currently lines 32-55).
- `justfile` -> top-level exported variables.
- `deploy/compose.local.yml` -> NO CHANGE. It defines only `mongodb` and `redis`; there is no
  `app` service there, so there is nothing to pin. Local dev is covered by the `justfile` change.

**Steps.**
1. In `deploy/Dockerfile`, change the runtime-stage `ENV` block to add `TZ=UTC` as a fourth
   entry, so it reads:
   ```
   ENV PATH="/app/.venv/bin:$PATH" \
       PYTHONUNBUFFERED=1 \
       PYTHONDONTWRITEBYTECODE=1 \
       TZ=UTC
   ```
2. In `deploy/compose.prod.yml`, inside the `app:` service and directly above the existing
   `env_file:` key, add:
   ```
       environment:
         TZ: "UTC"
   ```
   Add a comment above it: `# Explicit, not via env_file: a missing key in .env must not be able to unpin the process time zone.`
3. In `justfile`, immediately below the `python := ...` assignment line, add:
   ```
   # Every recipe runs in UTC. The startup assertion in app/main_extensions.py
   # refuses a non-UTC process, so this keeps `just be` working on any dev machine
   # without touching the machine's own zone.
   export TZ := "UTC"
   ```

**Success criteria.** All three files contain the pin; `compose.local.yml` is untouched.

**Verify.**
`grep -c 'TZ=UTC' deploy/Dockerfile` prints `1`, `grep -c 'TZ: "UTC"' deploy/compose.prod.yml`
prints `1`, and `just --evaluate TZ` exits 0 and prints `UTC`.

### Task 1.3 — Make every cron trigger explicitly UTC and expose trigger zones

**Goal.** Registered cron jobs fire at the same UTC instant regardless of host zone.

**Target files and symbols.**
- `core/infra/scheduling/scheduler.py` -> `JobScheduler.add_cron_job`, the two `CronTrigger(...)`
  constructors at lines 219 and 228; new method `JobScheduler.trigger_timezones`.
- New test file `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.

**Steps.**
1. In `core/infra/scheduling/scheduler.py`, confirm `from datetime import UTC` is imported
   (the module already imports `datetime` and `UTC` for `add_one_off_job`; if `UTC` is absent,
   add it to the existing `from datetime import ...` line).
2. Add `timezone=UTC,` as the final keyword argument to the `CronTrigger(...)` call that starts
   at line 219 (the `cron_expression` branch) and to the one that starts at line 228 (the
   `hour`/`minute`/`day_of_week` branch).
3. Above the first of the two, add the comment:
   `# A pre-built trigger keeps its OWN timezone; the scheduler-level timezone="UTC" at __init__ only applies when add_job builds the trigger from a string alias. Without this, APScheduler calls tzlocal.get_localzone() and pickles the host zone into the Mongo jobstore.`
4. Add a public accessor after `get_jobs`:
   ```python
   def trigger_timezones(self) -> dict[str, str]:
       """Map job_id -> str(trigger.timezone) for every registered job.

       Public so the startup assertion never reaches into the private scheduler.
       """
       if self._scheduler is None:
           return {}
       return {
           job.id: str(getattr(job.trigger, "timezone", ""))
           for job in self._scheduler.get_jobs()
       }
   ```
5. Create `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py` with exactly three
   test functions:
   - `test_cron_expression_trigger_is_utc` — initialize a `JobScheduler`, call `add_cron_job`
     with `cron_expression="0 */12"`, assert `str(scheduler.trigger_timezones()[job_id])` equals
     `"UTC"`.
   - `test_hour_minute_trigger_is_utc` — same with `hour=3, minute=0`.
   - `test_next_run_time_identical_across_host_zones` — for each of `"UTC"`,
     `"Asia/Saigon"`, `"America/Chicago"`, set `os.environ["TZ"]`, call `time.tzset()`, build a
     fresh `CronTrigger(hour=3, minute=0, timezone=UTC)`, compute
     `trigger.get_next_fire_time(None, datetime(2026, 3, 8, 12, 0, tzinfo=UTC))`, and assert all
     three results are equal. Restore the original `TZ` in a `finally` block.
   Use an in-memory jobstore for the first two tests (pass a `Settings` object whose
   `mongodb_url` points at a non-existent local host is NOT acceptable — instead build the
   `AsyncIOScheduler` through `JobScheduler.initialize` only if it does not connect eagerly;
   if it does, construct `CronTrigger` directly and assert on `trigger.timezone`).

**Success criteria.** Both `CronTrigger` call sites carry `timezone=UTC`; the new test file
passes.

**Verify.**
`uv run pytest tests/core_test/infra/scheduling/test_cron_trigger_timezone.py -q` exits 0 and
prints `3 passed`.

### Task 1.4 — Make Mongo tz-aware and remove the naive integrity site (ONE COMMIT)

**Goal.** No naive datetime crosses the persistence boundary, and the integrity check keeps
comparing like with like.

**Target files and symbols.**
- `core/infra/persistence/mongodb.py` -> `Database.connect`, the `AsyncMongoClient(...)` call at
  lines 44-49.
- `engine/market_data/app_services/integrity_jobs.py` -> `check_integrity`, line 50.
- `core/domain/bar/services/bar_builder_domain_service.py` -> `get_bar_start`, line 24.
- `engine/market_data/sync_internals/bar_filters.py` -> `filter_new_bars`, the comment at
  lines 54-55.

**Steps.**
1. In `core/infra/persistence/mongodb.py`, add `from datetime import UTC` at the top of the
   import block and change the client construction to:
   ```python
   client = AsyncMongoClient(
       str(settings.mongodb_url),
       minPoolSize=settings.mongodb_min_pool_size,
       maxPoolSize=settings.mongodb_max_pool_size,
       serverSelectionTimeoutMS=5000,
       tz_aware=True,
       tzinfo=UTC,
   )
   ```
2. In `engine/market_data/app_services/integrity_jobs.py`, change line 50 from
   `now = datetime.now(UTC).replace(tzinfo=None)` to `now = datetime.now(UTC)` and delete the
   surrounding comment if it mentions naivety.
3. In `core/domain/bar/services/bar_builder_domain_service.py`, replace line 24
   (`epoch = datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`)
   with:
   ```python
   if timestamp.tzinfo is None:
       raise ValueError("get_bar_start requires a timezone-aware timestamp")
   epoch = datetime(1970, 1, 1, tzinfo=UTC)
   ```
4. In `engine/market_data/sync_internals/bar_filters.py`, replace the two-line comment at
   lines 54-55 with: `# Both sides are tz-aware UTC (Mongo client is tz_aware). coerce_utc stays as a no-op safety net.`
5. Stage all four files and commit them together in a single commit.

**Success criteria.** The repository has no remaining `.replace(tzinfo=None)` inside `src/`,
and the existing normalization and integrity tests still pass.

**Verify.**
`git grep -n "replace(tzinfo=None)" -- src/` exits 1 (no match), AND
`uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py tests/core_test/unit/domain/bar/services/test_bar_builder.py tests/core_test/infra/persistence/test_bar_repository.py -q`
exits 0 and its final line contains `passed` and does not contain `failed`.

### Task 1.5 — Reject naive datetimes at the entity and DTO boundaries; unify serialization

**Goal.** A provider or a client cannot push a naive datetime past the boundary, and every
datetime serialized to the SPA uses the documented `to_utc_iso()` form.

**Target files and symbols.**
- `core/domain/bar/entities.py` -> `Bar.datetime` field (line 35); `Bar.to_dict` (line 104).
- `engine/market_data/ohlcv_service.py` -> `GetOHLCVQuery` (line 14); the `bar.datetime.isoformat()`
  at line 66.
- `engine/backtest/backtest_command_service.py` -> `RunBacktestCommand.start_date` / `.end_date`
  (lines 31-32); the two `.isoformat()` calls at lines 74-75.
- `engine/backtest/backtest_report_app_service.py` -> the two `.isoformat()` calls at lines 396-397.
- `engine/market_data/sync_status_service.py` -> `_iso_z` (lines 72-73).
- New test file `tests/core_test/unit/domain/bar/test_bar_rejects_naive_datetime.py`.

**Steps.**
1. In `core/domain/bar/entities.py`, import `AwareDatetime` from `pydantic` and change the field
   declaration `datetime: dt | None = None` to `datetime: AwareDatetime | None = None`. Add a
   `field_validator("datetime", "created_at", "updated_at", mode="after")` named
   `_normalise_to_utc` that returns `value.astimezone(UTC)` when `value` is not None. Import
   `UTC` from `datetime`.
2. In the same file, `Bar.from_mongo` keeps calling `coerce_utc` (Mongo is now tz-aware, so this
   is a no-op safety net). Do not change `from_mongo`.
3. In `Bar.to_dict` (lines 104 and 111), replace `self.datetime.isoformat() if self.datetime else None`
   with `to_utc_iso(self.datetime)` and `self.updated_at.isoformat() if self.updated_at else None`
   with `to_utc_iso(self.updated_at)`. `to_utc_iso` is already importable from
   `pocketquant.core.common.time`; add it to the existing import line.
4. In `engine/market_data/ohlcv_service.py` line 66, replace
   `"datetime": bar.datetime.isoformat() if bar.datetime else None,` with
   `"datetime": to_utc_iso(bar.datetime),` and add the import.
5. In `engine/market_data/ohlcv_service.py`, add to `GetOHLCVQuery` a normalisation that attaches
   UTC to naive `start_date`/`end_date`. `GetOHLCVQuery` is a `@dataclass`; add a
   `__post_init__` that calls `coerce_utc` on both fields. Add a comment:
   `# Naive ISO input from the API edge is still accepted (documented behaviour) but is normalised here so nothing past this boundary is naive.`
6. In `engine/backtest/backtest_command_service.py`, add a
   `@field_validator("start_date", "end_date", mode="after")` to `RunBacktestCommand` named
   `_normalise_to_utc` that returns `coerce_utc(v)`. Replace the two `.isoformat()` calls at
   lines 74-75 with `to_utc_iso(cmd.start_date)` and `to_utc_iso(cmd.end_date)`.
7. In `engine/backtest/backtest_report_app_service.py` lines 396-397, replace
   `self._config.start_date.isoformat()` with `to_utc_iso(self._config.start_date)` and the
   same for `end_date`.
8. In `engine/market_data/sync_status_service.py`, delete the body of `_iso_z` and make it
   `return to_utc_iso(dt)`.
9. Create `tests/core_test/unit/domain/bar/test_bar_rejects_naive_datetime.py` with exactly
   three test functions:
   - `test_bar_rejects_naive_datetime` — `pytest.raises(ValidationError)` on
     `Bar(symbol="BTCUSDT:BINANCE", interval=Interval.MINUTE_1, datetime=datetime(2026, 5, 4, 0, 0))  # noqa: DTZ001`.
   - `test_bar_normalises_non_utc_aware_datetime` — build a `Bar` whose datetime is
     `datetime(2026, 5, 4, 0, 0, tzinfo=ZoneInfo("America/Chicago"))` and assert
     `bar.datetime == datetime(2026, 5, 4, 5, 0, tzinfo=UTC)`.
   - `test_bar_to_dict_emits_z_suffix` — assert `Bar(...).to_dict()["datetime"]` ends with `"Z"`.

**Success criteria.** Constructing a `Bar` with a naive datetime raises; every serialized bar
datetime ends in `Z`.

**Verify.**
`uv run pytest tests/core_test/unit/domain/bar/test_bar_rejects_naive_datetime.py -q` exits 0 and
prints `3 passed`, AND `uv run pytest tests/ -q` exits 0 with a final line containing `passed`
and not containing `failed` or `error`.

### Task 1.6 — Fix the Binance in-progress weekly-bar cutoff

**Goal.** A weekly `BTCUSDT:BINANCE` bar is never persisted partial.

**Target files and symbols.**
- `core/infra/binance/binance_adapter.py` -> `BinanceAdapter.fetch_ohlcv`, lines 80-83.
- `tests/core_test/infra/binance/test_binance_client_in_progress_filter.py` (existing, 4 tests).

**Steps.**
1. In `core/infra/binance/binance_adapter.py`, add
   `from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start`
   to the imports.
2. Replace lines 80-83 with:
   ```python
   now = datetime.now(UTC)
   # Derive the last-closed-bar open from the SAME alignment function the sync filter
   # uses, so the two can never disagree. A plain floor(epoch / 604800000) lands on a
   # Thursday (the Unix epoch was a Thursday), so from Thursday to Sunday the
   # in-progress Monday-open weekly kline slipped past the cutoff and was stored partial.
   cutoff_dt = get_bar_start(now, interval)
   last_closed_open_ms = int(cutoff_dt.timestamp() * 1000)
   end_time_ms = last_closed_open_ms
   ```
3. Delete the now-unused `now_ms` local if nothing else references it.
4. Append one test function `test_weekly_cutoff_is_monday_aligned_on_a_thursday` to
   `tests/core_test/infra/binance/test_binance_client_in_progress_filter.py`: freeze
   `datetime.now` to Thursday `2026-05-07T12:00:00Z` (monkeypatch the module-level `datetime`
   the adapter imports, or inject through an explicit parameter if the existing tests already
   do so — follow the pattern already used in that file), fetch `Interval.WEEK_1` against a
   stubbed HTTP client, and assert the computed `endTime` parameter corresponds to
   `2026-05-04T00:00:00Z` (the Monday of that week).

**Success criteria.** The cutoff for `WEEK_1` equals the Monday 00:00 UTC open of the current
week, not the Thursday epoch floor.

**Verify.**
`uv run pytest tests/core_test/infra/binance/ -q` exits 0 and prints `5 passed` (4 existing plus
the new one).

### Task 1.7 — Fail fast on a non-UTC process at startup

**Goal.** The application refuses to start when the process time zone is not UTC, and refuses
when any registered trigger is not UTC.

**Target files and symbols.**
- `app/main_extensions.py` -> new functions `assert_process_timezone_utc` and
  `assert_registered_triggers_utc`.
- `app/main.py` -> `lifespan`, inside the `try:` block (currently line 54 onwards).
- New test file `tests/app_test/unit/test_utc_startup_assertion.py`.

**Steps.**
1. In `app/main_extensions.py`, add at the end of the import block: `import os`, `import time`,
   and `import tzlocal` (tzlocal is already installed as an APScheduler dependency).
2. Add:
   ```python
   _ALLOWED_TZ_NAMES = {"UTC", "Etc/UTC"}


   def assert_process_timezone_utc() -> None:
       """Refuse to run on a non-UTC host. There is no legitimate non-UTC deployment.

       tzlocal is checked because that is what APScheduler consults when a trigger
       carries no explicit timezone; time.timezone/time.daylight cover the stdlib side.
       """
       local_name = tzlocal.get_localzone_name()
       ok = time.timezone == 0 and not time.daylight and local_name in _ALLOWED_TZ_NAMES
       logger.info(
           "runtime.timezone",
           tz_env=os.environ.get("TZ"),
           tznames=list(time.tzname),
           tzlocal=local_name,
           utc=ok,
       )
       if not ok:
           raise RuntimeError(
               "Process timezone must be UTC. "
               f"TZ={os.environ.get('TZ')!r} tzlocal={local_name!r} "
               f"tzname={time.tzname!r}. Set TZ=UTC."
           )


   async def assert_registered_triggers_utc(container: AsyncContainer) -> None:
       """Every registered cron trigger must be UTC. No-op when jobs are disabled."""
       settings = await container.get(Settings)
       if not settings.enable_jobs:
           return
       scheduler = await container.get(JobScheduler)
       offenders = {
           job_id: tz
           for job_id, tz in scheduler.trigger_timezones().items()
           if tz not in _ALLOWED_TZ_NAMES
       }
       if offenders:
           raise RuntimeError(f"Non-UTC cron triggers registered: {offenders}")
   ```
3. In `app/main.py`, add both names to the existing `from pocketquant.app.main_extensions import (...)`
   block.
4. In `lifespan`, call `assert_process_timezone_utc()` as the FIRST statement inside the `try:`
   block, before `app.state.database = await container.get(Database)`.
5. In `lifespan`, call `await assert_registered_triggers_utc(container)` on the line immediately
   after `await start_background_jobs(container)`.
6. Create `tests/app_test/unit/test_utc_startup_assertion.py` with exactly two test functions:
   - `test_assert_process_timezone_utc_passes_under_utc` — set `os.environ["TZ"]="UTC"`,
     `time.tzset()`, call `assert_process_timezone_utc()`, assert it does not raise; restore in
     `finally`.
   - `test_assert_process_timezone_utc_raises_under_saigon` — set `os.environ["TZ"]="Asia/Saigon"`,
     `time.tzset()`, `pytest.raises(RuntimeError, match="must be UTC")`; restore in `finally`.

**Success criteria.** Startup under a non-UTC `TZ` raises `RuntimeError`; startup under
`TZ=UTC` proceeds.

**Verify.**
`uv run pytest tests/app_test/unit/test_utc_startup_assertion.py -q` exits 0 and prints `2 passed`.

### Task 1.8 — Enable ruff `DTZ` and clear every finding

**Goal.** Naive datetime construction is a lint error in `src` and `tests`.

**Target files and symbols.**
- `pyproject.toml` -> `[tool.ruff.lint] select` (currently `["E", "F", "I", "N", "W", "UP", "TID"]`).
- `engine/backtest/backtest_strategy_loader.py` -> line 37 `date.today()` (DTZ011).
- `engine/market_data/app_services/cascade_aggregator.py` -> line 81 `datetime.min` (DTZ901).
- 29 findings across `tests/` (see step 4 for the exact handling rule).
- `.github/workflows/cicd.yml` -> the `tests` job.

**Steps.**
1. In `pyproject.toml`, change the select list to
   `select = ["E", "F", "I", "N", "W", "UP", "TID", "DTZ"]`.
2. In `engine/backtest/backtest_strategy_loader.py` line 37, replace `today = date.today()`
   with `today = datetime.now(UTC).date()`. Ensure `UTC` and `datetime` are imported and remove
   the `date` import if it becomes unused (it is still used for type hints — check before
   removing).
3. In `engine/market_data/app_services/cascade_aggregator.py` line 81, replace
   `key=lambda b: b.datetime or datetime.min` with
   `key=lambda b: b.datetime or datetime.min.replace(tzinfo=UTC)`.
4. Run `uv run ruff check --select DTZ --output-format concise src tests` to list the remaining
   findings. For EACH finding in `tests/`, apply this rule in order:
   a. Add `tzinfo=UTC` to the `datetime(...)` call (import `UTC` if needed).
   b. Run that single test file with `uv run pytest <file> -q`. If it passes, keep the edit.
   c. If it fails, revert that one edit and instead append
      `  # noqa: DTZ001 - naive datetime is the subject under test`
      to the offending line.
   For `tests/core_test/unit/domain/test_mongo_datetime_normalization.py` (4 findings at lines
   17, 18, 35, 36) skip straight to (c): naivety is exactly what that file asserts.
   For `tests/app_test/market_data/test_cascade_aggregator.py` lines 313 and 317 (DTZ901),
   replace `datetime.min` with `datetime.min.replace(tzinfo=UTC)`.
5. `scripts/` is OUT of scope for this task: the project lints `src tests` only. Do not edit
   `scripts/backfill/test_binance_bars.py`.
6. In `.github/workflows/cicd.yml`, in the `tests` job, insert a new step between
   `Check import contracts (layered architecture)` and `Run pytest (full suite)`:
   ```yaml
      - name: Lint (ruff, incl. DTZ naive-datetime rules)
        run: uv run ruff check src tests
   ```

**Success criteria.** `ruff check src tests` reports no findings with `DTZ` active, and no test
was deleted or skipped.

**Verify.**
`uv run ruff check src tests` exits 0 and prints `All checks passed!`, AND
`uv run pytest tests/ -q` exits 0 with a final line containing `passed` and not containing
`failed` or `error`.

### Task 1.9 — Add a cross-timezone test recipe and wire it into CI

**Goal.** The unit suite is proven host-zone independent on every push.

**Target files and symbols.**
- `justfile` -> new recipe `test-tz`.
- `.github/workflows/cicd.yml` -> the `tests` job.

**Steps.**
1. In `justfile`, after the existing `test:` recipe, add:
   ```
   # Prove the suite is host-timezone independent. The `export TZ := "UTC"` at the top
   # of this file is overridden per-invocation here on purpose.
   test-tz:
       TZ=Asia/Saigon {{python}} -m pytest tests/ -q
       TZ=America/Chicago {{python}} -m pytest tests/ -q
   ```
2. In `.github/workflows/cicd.yml`, in the `tests` job, after the `Run pytest (full suite)`
   step, add:
   ```yaml
      - name: Run pytest under Asia/Saigon
        run: uv run pytest tests/ -q
        env:
          TZ: Asia/Saigon

      - name: Run pytest under America/Chicago
        run: uv run pytest tests/ -q
        env:
          TZ: America/Chicago
   ```

**Success criteria.** The suite passes identically under all three zones.

**Verify.**
`TZ=Asia/Saigon uv run pytest tests/ -q` exits 0 AND `TZ=America/Chicago uv run pytest tests/ -q`
exits 0, both with a final line containing `passed` and not containing `failed`.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `tz_aware=True` lands without the integrity fix and triggers a full resync of every symbol | Medium | High | Task 1.4 is one commit; the Verify step runs the bar-repository and integrity tests together |
| Adding `tzinfo=UTC` to a test fixture silently changes an assertion | Medium | Medium | Task 1.8 step 4 runs each edited test file immediately and reverts to `noqa` on failure |
| The startup assertion blocks a developer whose machine is not UTC | High | Low | `export TZ := "UTC"` in the justfile makes `just be` pass without touching the machine |
| `python:3.14-rc-slim` lacks an OS tz database and `ZoneInfo` raises in prod | Medium | High | Task 1.1 adds `tzdata` as an explicit, unconditional dependency |

## Rollback

Every task is an independent commit except Task 1.4, which is deliberately atomic. Revert order
is the reverse of task order. Reverting Task 1.4 requires reverting all four of its files
together. No data migration runs in this phase, so no stored document changes shape and nothing
needs backfilling on rollback.

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
title: "Trading-calendar port and asset-class domain model"
status: pending
priority: P1
effort: "2.5d"
dependencies: [1]
---

## Context

`Symbol.asset_type` is a free string (`core/domain/symbol/entities.py:38`). There is no
`multiplier`, `contract_size`, `tick_size` or `point_value` anywhere in `src/` (grep verified).
`COMPOSITE_SYMBOL_RE` at `core/domain/symbol/entities.py:19` is `^[A-Z0-9_-]+:[A-Z0-9_-]+$` and
rejects `!`; `COMPOSITE_SYMBOL_PATTERN` at line 24 is the stricter API-edge variant used by
`app/common/symbol_validation.py:10`, `engine/market_data/tracked_symbols_service.py:12` and
`engine/market_data/tracked_symbols_backfill.py:20`.

This phase introduces the vocabulary only. It creates the `AssetClass` enum, the `ContractSpec`
value object, the `ITradingCalendarPort` domain port and its two implementations, persists
`asset_class` / `calendar_id` / `contract_spec` on `Symbol` and `session_date` / `calendar_id`
on `Bar`, widens both regexes, and migrates existing symbol records. **Nothing in the sync,
cascade, integrity, freshness or annualization path changes in this phase** — that is Phase 3.

Design decisions locked here, to be followed literally:
- The calendar is a **port** in `core/domain/market_data/`; both implementations are **adapters**
  in `core/infra/calendars/`. The domain-purity test
  (`tests/core_test/unit/domain/test_domain_purity.py`) forbids `pocketquant.core.infra` imports
  inside `core/domain`, so the 24/7 implementation also lives in infra and is passed in as a
  parameter typed by the port.
- The calendar **rules** live in code, not Mongo. The symbol record carries only a
  `calendar_id` string. Holidays and early closes change yearly and are shared by many symbols;
  a Mongo copy would have to be hand-synced with CME notices.
- The port exposes `expected_bar_starts(interval, start, end)` rather than the
  `trading_minutes` / `sessions` pair the audit sketched. It is the single member the integrity
  grid and the cascade expected-count both need, so one member replaces two (DRY). `sessions`
  is kept separately because the daily-bar path enumerates session dates, not instants.

## Tasks

### Task 2.1 — Add `pandas_market_calendars` and verify the CME alias

**Goal.** The CME Globex equity schedule is available from a maintained library, behind the
import-linter boundary.

**Target files and symbols.**
- `pyproject.toml` -> `[project] dependencies`.
- `uv.lock` (regenerated).

**Steps.**
1. In `pyproject.toml`, add `"pandas-market-calendars>=5.4.0",` to the `[project] dependencies`
   array, directly after the `"pandas>=2.1.0",` entry. Add the comment above it:
   `# CME Globex equity session + holiday/early-close rules. Used ONLY inside core/infra/calendars; engine and app see the ITradingCalendarPort.`
2. Run `uv sync`.

**Success criteria.** The library resolves the `"CME Globex Equity"` alias and reports
`America/Chicago`.

**Verify.**
`uv run python -c "import pandas_market_calendars as mcal; c = mcal.get_calendar('CME Globex Equity'); print(c.tz)"`
exits 0 and prints `America/Chicago`.
If it prints anything else, or raises, STOP and follow the Failure Protocol — the alias is the
load-bearing assumption of this whole phase.

### Task 2.2 — Add the `AssetClass` enum, `CalendarId` constants and the `ContractSpec` value object

**Goal.** The domain has a closed vocabulary for asset classes, calendars and contract maths.

**Target files and symbols.**
- `core/domain/shared/enums.py` -> new `AssetClass(str, Enum)`.
- New file `core/domain/symbol/value_objects.py` -> `CalendarId`, `ContractSpec`, `LINEAR_SPEC`,
  `CONTRACT_SPECS`.
- `core/domain/symbol/__init__.py` -> re-export the new names.
- New test file `tests/core_test/unit/domain/symbol/test_contract_spec.py`.

**Steps.**
1. In `core/domain/shared/enums.py`, append:
   ```python
   class AssetClass(str, Enum):
       """What kind of instrument a symbol is.

       Binds the annualization basis and the contract-spec shape. A new asset class
       is a new member here plus a new calendar_id and contract spec - never a new
       branch in the sync, cascade, integrity or freshness code.
       """

       CRYPTO_SPOT = "crypto_spot"
       CRYPTO_PERP = "crypto_perp"
       INDEX_FUTURE = "index_future"
   ```
   Do NOT touch `Interval.periods_per_year` in this phase; Phase 3 moves it.
2. Create `core/domain/symbol/value_objects.py`:
   ```python
   """Symbol-level value objects: calendar identity and contract maths."""

   from __future__ import annotations

   from dataclasses import dataclass
   from typing import Final

   from pocketquant.core.domain.shared.enums import AssetClass


   class CalendarId:
       """String ids referencing a trading calendar implementation.

       Persisted on the symbol record; resolved to an ITradingCalendarPort at runtime.
       """

       CRYPTO_24_7: Final = "CRYPTO_24_7"
       CME_GLOBEX_EQUITY: Final = "CME_GLOBEX_EQUITY"


   @dataclass(frozen=True)
   class ContractSpec:
       """Unit conversion between price points and account currency.

       multiplier: account-currency value of one full index/price point.
       tick_size:  smallest price increment the venue quotes.
       lot_step:   quantity granularity; None means fractional sizes are allowed.
       currency:   settlement currency.
       commission_kind: "percentage" | "per_contract".
       """

       multiplier: float = 1.0
       tick_size: float = 0.01
       lot_step: float | None = None
       currency: str = "USD"
       commission_kind: str = "percentage"


   # Crypto and anything else that settles in price x quantity.
   LINEAR_SPEC: Final = ContractSpec()

   # Per-symbol CME/CBOT E-mini values. Keyed by composite symbol so a second
   # contract on the same exchange is one dict entry, not a new branch.
   CONTRACT_SPECS: Final[dict[str, ContractSpec]] = {
       "ES1!:CME_MINI": ContractSpec(
           multiplier=50.0, tick_size=0.25, lot_step=1.0, commission_kind="per_contract"
       ),
       "NQ1!:CME_MINI": ContractSpec(
           multiplier=20.0, tick_size=0.25, lot_step=1.0, commission_kind="per_contract"
       ),
       "YM1!:CBOT_MINI": ContractSpec(
           multiplier=5.0, tick_size=1.0, lot_step=1.0, commission_kind="per_contract"
       ),
   }


   DEFAULT_CALENDAR_BY_ASSET_CLASS: Final[dict[AssetClass, str]] = {
       AssetClass.CRYPTO_SPOT: CalendarId.CRYPTO_24_7,
       AssetClass.CRYPTO_PERP: CalendarId.CRYPTO_24_7,
       AssetClass.INDEX_FUTURE: CalendarId.CME_GLOBEX_EQUITY,
   }
   ```
3. In `core/domain/symbol/__init__.py`, add `ContractSpec`, `CalendarId`, `LINEAR_SPEC`,
   `CONTRACT_SPECS` and `DEFAULT_CALENDAR_BY_ASSET_CLASS` to the imports and `__all__`.
4. Create `tests/core_test/unit/domain/symbol/test_contract_spec.py` with exactly three test
   functions:
   - `test_linear_spec_is_identity` — `LINEAR_SPEC.multiplier == 1.0` and
     `LINEAR_SPEC.lot_step is None`.
   - `test_es_nq_ym_multipliers` — assert `CONTRACT_SPECS["ES1!:CME_MINI"].multiplier == 50.0`,
     `CONTRACT_SPECS["NQ1!:CME_MINI"].multiplier == 20.0`,
     `CONTRACT_SPECS["YM1!:CBOT_MINI"].multiplier == 5.0`.
   - `test_contract_spec_is_frozen` — `pytest.raises(...)` when assigning to `.multiplier`.

**Success criteria.** The enum and value objects import cleanly from the domain with no infra
import.

**Verify.**
`uv run pytest tests/core_test/unit/domain/symbol/test_contract_spec.py tests/core_test/unit/domain/test_domain_purity.py -q`
exits 0 and prints `4 passed`.

### Task 2.3 — Define `ITradingCalendarPort`

**Goal.** One interface every session-dependent behaviour will be parameterized by.

**Target files and symbols.**
- New file `core/domain/market_data/trading_calendar_port.py` -> `ITradingCalendarPort`.
- `core/domain/market_data/__init__.py` -> re-export.

**Steps.**
1. Create `core/domain/market_data/trading_calendar_port.py`:
   ```python
   """Trading-calendar port - the single parameter that makes session behaviour pluggable.

   One port per file, per docs/code-standards.md "Infra Port (Interface)".
   Implementations live in core/infra/calendars/ so core/domain stays I/O-free.
   Every returned datetime is timezone-aware UTC. Every accepted datetime must be
   timezone-aware; implementations raise ValueError on naive input.
   """

   from __future__ import annotations

   from abc import ABC, abstractmethod
   from datetime import date, datetime
   from zoneinfo import ZoneInfo

   from pocketquant.core.domain.shared.enums import Interval


   class ITradingCalendarPort(ABC):
       @property
       @abstractmethod
       def calendar_id(self) -> str:
           """Stable id persisted on symbol and bar records."""

       @property
       @abstractmethod
       def tz(self) -> ZoneInfo:
           """Exchange-local IANA zone used to build session boundaries."""

       @abstractmethod
       def is_open(self, instant: datetime) -> bool:
           """True when the venue is trading at this UTC instant."""

       @abstractmethod
       def session_date(self, instant: datetime) -> date:
           """Exchange session day this UTC instant belongs to."""

       @abstractmethod
       def session_open(self, session_date: date) -> datetime:
           """UTC instant the given session opens."""

       @abstractmethod
       def session_close(self, session_date: date) -> datetime:
           """UTC instant the given session closes."""

       @abstractmethod
       def previous_close(self, instant: datetime) -> datetime:
           """UTC instant of the most recent session close at or before `instant`."""

       @abstractmethod
       def bar_start(self, instant: datetime, interval: Interval) -> datetime:
           """UTC open instant of the bar of `interval` containing `instant`."""

       @abstractmethod
       def expected_bar_starts(
           self, interval: Interval, start: datetime, end: datetime
       ) -> set[datetime]:
           """Every bar-open instant of `interval` the venue should have produced in
           [start, end). Drives the integrity grid and the cascade expected count."""

       @abstractmethod
       def sessions(self, start: datetime, end: datetime) -> list[date]:
           """Session dates whose session overlaps [start, end)."""

       @abstractmethod
       def periods_per_year(self, interval: Interval) -> float:
           """Bars of `interval` in one trading year; annualizes Sharpe/Sortino."""
   ```
2. In `core/domain/market_data/__init__.py`, re-export `ITradingCalendarPort` following the
   existing re-export style in that file.

**Success criteria.** The port imports with no infra dependency and the layering contracts hold.

**Verify.**
`uv run lint-imports` exits 0, AND
`uv run pytest tests/core_test/unit/domain/test_domain_purity.py tests/core_test/test_core_layout_contract.py -q`
exits 0 with a final line containing `passed` and not containing `failed`.

### Task 2.4 — Implement `Continuous24x7CalendarAdapter`

**Goal.** A calendar whose every output byte-for-byte reproduces today's crypto behaviour.

**Target files and symbols.**
- New file `core/infra/calendars/continuous_24x7_calendar_adapter.py` ->
  `Continuous24x7CalendarAdapter`.
- New file `core/infra/calendars/__init__.py`.
- New test file `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py`.

**Steps.**
1. Create `core/infra/calendars/__init__.py` re-exporting the adapter class.
2. Create `core/infra/calendars/continuous_24x7_calendar_adapter.py` implementing
   `ITradingCalendarPort` with:
   - `calendar_id` -> `CalendarId.CRYPTO_24_7`; `tz` -> `ZoneInfo("UTC")`.
   - `is_open(instant)` -> always `True` (raise `ValueError` if `instant.tzinfo is None`).
   - `session_date(instant)` -> `instant.astimezone(UTC).date()`.
   - `session_open(d)` -> `datetime(d.year, d.month, d.day, tzinfo=UTC)`.
   - `session_close(d)` -> `session_open(d) + timedelta(days=1)`.
   - `previous_close(instant)` -> `instant.astimezone(UTC)` (a 24/7 venue never closed, so the
     most recent close is now). Add the comment:
     `# A continuous venue has no close; returning `now` makes freshness age measure now - last_bar, exactly as sync_status_service._is_stuck does today.`
   - `bar_start(instant, interval)` -> move the CURRENT body of
     `core/domain/bar/services/bar_builder_domain_service.get_bar_start` here verbatim: 1d is
     `replace(hour=0, minute=0, second=0, microsecond=0)`; 1w is that midnight minus
     `timedelta(days=midnight.weekday())` with the existing Monday/Thursday-epoch explanation
     comment; everything else is epoch floor with `epoch = datetime(1970, 1, 1, tzinfo=UTC)`.
     Raise `ValueError` on naive input.
   - `expected_bar_starts(interval, start, end)` ->
     `{bar_start(start, interval) + i * step for i in range(...)}` where
     `step = timedelta(seconds=INTERVAL_SECONDS[interval])`, producing the dense grid over
     `[start, end)` exactly as `integrity_jobs.py:63` does today.
   - `sessions(start, end)` -> every UTC date from `start.date()` to `end.date()` inclusive of
     the start date and exclusive of `end` when `end` lands exactly on midnight.
   - `periods_per_year(interval)` -> return the value from the existing
     `_PERIODS_PER_YEAR` table in `core/domain/shared/enums.py`; import that table rather than
     re-typing the numbers (DRY), so crypto annualization cannot drift.
3. Create `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py` with exactly six
   test functions:
   - `test_is_always_open`
   - `test_bar_start_matches_legacy_daily` — `bar_start(datetime(2026,5,6,13,7,tzinfo=UTC), DAY_1) == datetime(2026,5,6,tzinfo=UTC)`
   - `test_bar_start_matches_legacy_weekly` — a Sunday and a Tuesday both map to
     `datetime(2026,5,4,tzinfo=UTC)` (the Monday)
   - `test_bar_start_matches_legacy_intraday` — 4h floors to `00/04/08/12/16/20` UTC
   - `test_expected_bar_starts_is_dense` — 1m over a 60-minute window yields 60 instants
   - `test_periods_per_year_matches_interval_table` — for every `Interval` member,
     `calendar.periods_per_year(iv) == Interval.periods_per_year_for(iv.value)`

**Success criteria.** Every 24/7 calendar output equals the legacy computation.

**Verify.**
`uv run pytest tests/core_test/infra/calendars/test_continuous_24x7_calendar.py -q` exits 0 and
prints `6 passed`.

### Task 2.5 — Implement `CmeGlobexEquityCalendarAdapter`

**Goal.** ES/NQ/YM session boundaries computed from the library, DST-correct, in UTC.

**Target files and symbols.**
- New file `core/infra/calendars/cme_globex_equity_calendar_adapter.py` ->
  `CmeGlobexEquityCalendarAdapter`.
- New test file `tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py`.

**Steps.**
1. Create the adapter implementing `ITradingCalendarPort`:
   - Module docstring: `"""CME Globex equity session (ES/NQ/YM) via pandas_market_calendars. Sun 17:00 CT open to Fri 16:00 CT close, with a 16:00-17:00 CT daily maintenance halt. Session boundaries are built as exchange-local wall time via zoneinfo and converted per instant, never by adding a fixed offset, so DST is handled by construction."""`
   - `__init__` caches `mcal.get_calendar("CME Globex Equity")` on the instance. The instance is
     stateless apart from that immutable handle and a memoised schedule frame keyed by
     `(start_date, end_date)`; it is safe as a process-level singleton.
   - `calendar_id` -> `CalendarId.CME_GLOBEX_EQUITY`; `tz` -> `ZoneInfo("America/Chicago")`.
   - `session_open(d)` / `session_close(d)` -> read the library's `schedule(d, d)` frame,
     take `market_open` / `market_close`, and return `.to_pydatetime().astimezone(UTC)`.
     Raise `LookupError` when `d` is not a trading session.
   - `session_date(instant)` -> the session date `d` for which
     `session_open(d) <= instant < session_close(d)`; when `instant` falls in a halt or a
     weekend, return the session date of the NEXT open (that is the session the following bars
     belong to). Document this choice in a comment.
   - `is_open(instant)` -> `session_open(d) <= instant < session_close(d)` for the candidate
     session date.
   - `previous_close(instant)` -> the largest `session_close(d)` that is `<= instant`; when
     `instant` is inside a live session, return `instant` itself so freshness measures
     `now - last_bar` during trading hours and freezes at the close otherwise.
   - `bar_start(instant, interval)`:
     - `DAY_1` -> `session_open(session_date(instant))`
     - `WEEK_1` -> `session_open(first session date of that session's trading week)`
     - otherwise -> `open_ + floor((instant - open_) / tf) * tf` where
       `open_ = session_open(session_date(instant))`.
   - `expected_bar_starts(interval, start, end)` -> for `DAY_1` and `WEEK_1` the set of
     `bar_start` values over the sessions in range; otherwise, per session, the instants
     `session_open + k * tf` strictly less than `session_close`, intersected with
     `[start, end)`.
   - `sessions(start, end)` -> the library's `valid_days` converted to `date` objects.
   - `periods_per_year(interval)` -> a module-level table with a WHY comment:
     ```python
     # ES/NQ/YM trade ~252 sessions a year, ~23h (1380 minutes) each. Derived from the
     # session definition rather than sampled from a rolling window, so the number is
     # deterministic and a Sharpe computed today equals one computed next month.
     _CME_SESSIONS_PER_YEAR = 252
     _CME_MINUTES_PER_SESSION = 1380
     ```
     giving `1m: 347_760`, `5m: 69_552`, `15m: 23_184`, `1h: 5_796`, `4h: 1_449`,
     `1d: 252`, `1w: 52`.
2. Create `tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py` with exactly
   eight test functions:
   - `test_spring_forward_session_open` — `session_open(date(2026, 3, 9)) == datetime(2026, 3, 8, 22, 0, tzinfo=UTC)`
   - `test_fall_back_session_open` — `session_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)`
   - `test_sunday_reopen_is_open` — an instant just after the Sunday 17:00 CT open is open; one
     just before is closed
   - `test_weekend_is_closed` — Saturday noon UTC is closed
   - `test_daily_halt_is_closed` — 16:30 CT on a weekday is closed
   - `test_juneteenth_early_close` — the 2026 Juneteenth observance session closes earlier than
     16:00 CT (assert `session_close(...)` is strictly before the normal close for that date)
   - `test_session_spans_utc_midnight` — `session_date` of `00:30 UTC` on a weekday equals the
     PREVIOUS calendar date plus one, i.e. the session that opened the evening before
   - `test_periods_per_year_is_session_based` — `periods_per_year(Interval.HOUR_1) == 5796`
   Every test builds its expected instants as hard-coded `datetime(..., tzinfo=UTC)` literals.

**Success criteria.** All eight scenarios pass, including both DST transitions with exactly the
UTC instants stated.

**Verify.**
`uv run pytest tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py -q` exits 0 and
prints `8 passed`.

### Task 2.6 — Add the calendar registry and the per-symbol resolver

**Goal.** Any caller can obtain the right calendar for a composite symbol without a Mongo round
trip per bar.

**Target files and symbols.**
- New file `core/infra/calendars/trading_calendar_registry.py` -> `TRADING_CALENDARS`,
  `get_calendar(calendar_id)`.
- New file `engine/market_data/trading_calendar_resolver_app_service.py` ->
  `TradingCalendarResolverAppService`.
- `core/infra/persistence/repositories/symbol_repository.py` -> new method `find_by_symbol`.
- `app/di/market_data.py` -> provide `TradingCalendarResolverAppService` at `Scope.APP`.
- New test file `tests/engine_test/market_data/test_trading_calendar_resolver.py`.

**Steps.**
1. Create `core/infra/calendars/trading_calendar_registry.py`:
   ```python
   """Process-wide calendar instances, keyed by the id persisted on symbol records.

   Both implementations are immutable and stateless apart from an internal schedule
   cache, so sharing one instance across every request and job is safe: there is no
   per-request or per-session state to leak.
   """
   TRADING_CALENDARS: dict[str, ITradingCalendarPort] = {
       CalendarId.CRYPTO_24_7: Continuous24x7CalendarAdapter(),
       CalendarId.CME_GLOBEX_EQUITY: CmeGlobexEquityCalendarAdapter(),
   }


   def get_calendar(calendar_id: str | None) -> ITradingCalendarPort:
       """Resolve a calendar id. Unknown or missing id falls back to 24/7 with a WARNING."""
   ```
   The fallback logs `logger.warning("calendar.unknown_id", calendar_id=calendar_id)` once per
   call and returns the 24/7 calendar, so an unmigrated symbol degrades to today's behaviour
   instead of crashing the cron.
2. In `core/infra/persistence/repositories/symbol_repository.py`, add:
   ```python
   async def find_by_symbol(self, symbol: str) -> Symbol | None:
       """Look up one symbol record by composite identifier."""
       doc = await self._collection().find_one({"symbol": symbol.upper()})
       return Symbol.from_mongo(doc) if doc else None
   ```
3. Create `engine/market_data/trading_calendar_resolver_app_service.py`:
   ```python
   class TradingCalendarResolverAppService:
       """Composite symbol -> ITradingCalendarPort, with a bounded in-process cache.

       The cache maps symbol -> calendar_id only. It is APP-scoped and shared, which is
       safe because the mapping is global (not per-request or per-user) and changes only
       when an admin edits a symbol record.
       """

       def __init__(self, symbol_repository: SymbolRepository, ttl_seconds: int = 300) -> None:
           ...

       async def resolve(self, symbol: str) -> ITradingCalendarPort:
           """Return the calendar for `symbol`; falls back to 24/7 when unknown."""

       def invalidate(self, symbol: str | None = None) -> None:
           """Drop one or all cached entries (called after a symbol upsert)."""
   ```
   Use `cachetools.TTLCache(maxsize=512, ttl=ttl_seconds)` — `cachetools` is already a project
   dependency.
4. In `app/di/market_data.py`, add a `@provide(scope=Scope.APP)` method
   `get_trading_calendar_resolver(self, symbol_repository: SymbolRepository) -> TradingCalendarResolverAppService`.
   Import `SymbolRepository` from `core.infra.persistence.repositories.symbol_repository`.
5. Create `tests/engine_test/market_data/test_trading_calendar_resolver.py` with exactly four
   test functions, using a stub repository object (no Mongo):
   - `test_resolves_crypto_symbol_to_24_7`
   - `test_resolves_futures_symbol_to_cme`
   - `test_unknown_symbol_falls_back_to_24_7`
   - `test_second_resolve_hits_the_cache` — assert the stub repository's call counter is 1 after
     two `resolve` calls for the same symbol

**Success criteria.** Resolution works for both known calendars and degrades safely for unknown
ones.

**Verify.**
`uv run pytest tests/engine_test/market_data/test_trading_calendar_resolver.py -q` exits 0 and
prints `4 passed`, AND `uv run lint-imports` exits 0.

### Task 2.7 — Extend the `Symbol` entity and widen both composite-symbol regexes

**Goal.** A symbol record carries its asset class, calendar id and contract spec, and `!` is a
legal character in a composite symbol.

**Target files and symbols.**
- `core/domain/symbol/entities.py` -> `COMPOSITE_SYMBOL_RE` (line 19),
  `COMPOSITE_SYMBOL_PATTERN` (line 24), `Symbol` fields (lines 35-40), `Symbol.create`
  (lines 62-70), `Symbol.to_mongo` (lines 78-87), `Symbol.from_mongo` (lines 89-100).
- Regex consumers, all of which import from the file above and need NO edit:
  `app/common/symbol_validation.py:10`, `engine/market_data/tracked_symbols_service.py:12`,
  `engine/market_data/tracked_symbols_backfill.py:20`.
- New test file `tests/core_test/unit/domain/symbol/test_symbol_asset_class.py`.

**Steps.**
1. Change `COMPOSITE_SYMBOL_RE` to `re.compile(r"^[A-Z0-9!_-]+:[A-Z0-9!_-]+$")` and
   `COMPOSITE_SYMBOL_PATTERN` to `re.compile(r"^[A-Z0-9.!_-]{1,32}:[A-Z0-9.!_-]{1,32}$")`. Add
   a comment above them: `# '!' admits TradingView continuous-contract codes (ES1!, NQ1!, YM1!).`
2. Add three fields to `Symbol`, after `asset_type` (keep `asset_type` in place for backwards
   compatibility with unmigrated documents; the migration in Task 2.9 stops writing to it):
   ```python
   asset_class: AssetClass = AssetClass.CRYPTO_SPOT
   calendar_id: str = CalendarId.CRYPTO_24_7
   contract_spec: ContractSpec = LINEAR_SPEC
   ```
   Add the comment: `# asset_type is the legacy free string. New code reads asset_class; the field stays so an unmigrated document still loads.`
3. Extend `Symbol.create` with `asset_class`, `calendar_id` and `contract_spec` keyword
   parameters defaulting to the same values.
4. In `to_mongo`, serialize `"asset_class": self.asset_class.value`, `"calendar_id": self.calendar_id`
   and `"contract_spec": asdict(self.contract_spec)`.
5. In `from_mongo`, read them back with defaults:
   `asset_class=AssetClass(doc.get("asset_class", AssetClass.CRYPTO_SPOT.value))`,
   `calendar_id=doc.get("calendar_id", CalendarId.CRYPTO_24_7)`,
   `contract_spec=ContractSpec(**doc["contract_spec"]) if doc.get("contract_spec") else LINEAR_SPEC`.
6. Create `tests/core_test/unit/domain/symbol/test_symbol_asset_class.py` with exactly five test
   functions:
   - `test_bang_is_accepted_in_composite_symbol` — `Symbol.create("ES1!:CME_MINI")` succeeds
   - `test_legacy_symbol_still_valid` — `Symbol.create("BTCUSDT:BINANCE")` succeeds
   - `test_invalid_symbol_still_rejected` — `pytest.raises(ValueError)` on `"ES1!"` (no colon)
   - `test_defaults_are_crypto_linear` — a bare `Symbol.create("BTCUSDT:BINANCE")` has
     `asset_class == AssetClass.CRYPTO_SPOT`, `calendar_id == CalendarId.CRYPTO_24_7`,
     `contract_spec == LINEAR_SPEC`
   - `test_mongo_roundtrip_preserves_contract_spec` — `Symbol.from_mongo(s.to_mongo())` returns
     an equal `contract_spec` for an ES symbol

**Success criteria.** `!` is accepted end to end; unmigrated documents still load with crypto
defaults.

**Verify.**
`uv run pytest tests/core_test/unit/domain/symbol/ -q` exits 0 and prints `8 passed` (3 from
Task 2.2 plus 5 here).

### Task 2.8 — Persist `session_date` and `calendar_id` on bars and index them

**Goal.** Daily and weekly bars carry a stable session-day key that does not move with DST.

**Target files and symbols.**
- `core/domain/bar/entities.py` -> `Bar` fields, `to_mongo` (line 60), `from_mongo` (line 76),
  `to_dict` (line 99).
- `core/infra/persistence/repositories/bar_repository.py` -> `ensure_indexes` (line 284).
- New test file `tests/core_test/unit/domain/bar/test_bar_session_fields.py`.

**Steps.**
1. Add two optional fields to `Bar`, after `tick_count`:
   ```python
   # Derived day key for session-based instruments. `datetime` keeps moving with DST;
   # `session_date` does not, so consumers group on a stable key. None for 24/7 symbols
   # and for intraday intervals, where the UTC instant already is the key.
   session_date: date | None = None
   calendar_id: str | None = None
   ```
   Import `date` from `datetime`.
2. Serialize both in `to_mongo` (store `session_date` as an ISO `"YYYY-MM-DD"` string, not a
   BSON date, so it can never acquire a spurious time component) and read them back in
   `from_mongo` with `date.fromisoformat(...)` when present.
3. Include both in `to_dict` (`"session_date": self.session_date.isoformat() if self.session_date else None`).
4. In `BarRepository.ensure_indexes`, append a second index after the existing unique one:
   ```python
   # Session-day lookups for calendar-based instruments. Sparse: 24/7 bars never set it.
   await collection.create_index(
       [("symbol", 1), ("interval", 1), ("session_date", 1)],
       name="ix_ohlcv_symbol_interval_session_date",
       sparse=True,
   )
   ```
5. Do NOT populate `session_date` anywhere yet. Phase 3 sets it in the alignment path and
   Phase 5 sets it in the TradingView mapper.
6. Create `tests/core_test/unit/domain/bar/test_bar_session_fields.py` with exactly three test
   functions:
   - `test_session_fields_default_to_none`
   - `test_session_date_roundtrips_as_iso_string` — `to_mongo()["session_date"] == "2026-03-09"`
     and `from_mongo` returns `date(2026, 3, 9)`
   - `test_to_dict_exposes_session_date`

**Success criteria.** The fields round-trip; the existing unique index is unchanged.

**Verify.**
`uv run pytest tests/core_test/unit/domain/bar/ -q` exits 0 with a final line containing
`passed` and not containing `failed`.

### Task 2.9 — Migrate existing symbol records

**Goal.** Every existing `symbols` document carries `asset_class`, `calendar_id` and a linear
`contract_spec`.

**Target files and symbols.**
- New file `scripts/migrate_symbol_asset_class.py`.
- `scripts/README.md` -> add one bullet describing it.

**Steps.**
1. Create `scripts/migrate_symbol_asset_class.py` following the conventions in
   `scripts/README.md`: read `MONGODB_URL` and `MONGODB_DATABASE` from the environment (never
   CLI flags), default to a dry run, and require `--apply` for writes.
2. The script updates every document in the `symbols` collection that lacks `asset_class`:
   ```
   {"$set": {"asset_class": "crypto_spot",
             "calendar_id": "CRYPTO_24_7",
             "contract_spec": {"multiplier": 1.0, "tick_size": 0.01,
                               "lot_step": None, "currency": "USD",
                               "commission_kind": "percentage"}}}
   ```
   Filter on `{"asset_class": {"$exists": False}}` so re-running is a no-op.
3. Print a summary line `migrate_symbol_asset_class matched=N modified=M dry_run=<bool>`.
4. Add to `scripts/README.md` under the existing bullet list:
   `- `migrate_symbol_asset_class.py` — one-off. Stamps pre-asset-class `symbols` documents with `asset_class=crypto_spot`, `calendar_id=CRYPTO_24_7` and a linear `contract_spec`. Idempotent; `--apply` required to write.`

**Success criteria.** A dry run reports the count of unmigrated documents; an `--apply` run
leaves zero documents without `asset_class`; a second `--apply` run reports `modified=0`.

**Verify.**
Against the local stack (`just up` first):
`uv run python scripts/migrate_symbol_asset_class.py --apply` exits 0, then
`uv run python scripts/migrate_symbol_asset_class.py` exits 0 and prints a line containing
`matched=0`.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The `"CME Globex Equity"` alias or its session times differ from the audit's reading | Low | High | Task 2.1 verifies the alias and tz before any adapter is written; Task 2.5's eight tests assert exact UTC instants |
| `pandas_market_calendars` pulls `exchange_calendars` and inflates the image | High | Low | Accepted; it is confined to `core/infra/calendars` behind the port and checked by `lint-imports` |
| Widening the regex admits a malformed symbol | Low | Medium | `COMPOSITE_SYMBOL_PATTERN` keeps the 32-character segment bound; Task 2.7 asserts a no-colon input still raises |
| A shared calendar instance accumulates per-symbol state | Low | High | Both adapters are stateless apart from an immutable library handle; Task 2.6's docstring records the lifetime argument |
| The migration runs against production by accident | Low | High | Dry run is the default; `--apply` is required; the script reads the URL from the environment only |

## Rollback

Tasks 2.1 through 2.8 are additive: nothing existing reads the new fields yet, so reverting the
commits is sufficient and no data is orphaned. Task 2.9 writes three new keys onto existing
documents; to roll back, run
`db.symbols.updateMany({}, {$unset: {asset_class: "", calendar_id: "", contract_spec: ""}})`.
`from_mongo` defaults make an un-stamped document load identically either way.

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

=== FILE: phase-03-thread-calendar-through-pipeline.md ===
---
phase: 3
title: "Thread the calendar through the pipeline (24/7 only)"
status: pending
priority: P1
effort: "2d"
dependencies: [2]
---

## Context

Five verified sites break on day one of a session-scheduled asset class. This phase
parameterizes all five by `ITradingCalendarPort`, **using only the 24/7 calendar**, so the
crypto path proves the refactor before any futures symbol exists. Nothing routes to the CME
calendar in this phase.

The five sites, with evidence:
1. **Alignment.** `core/domain/bar/services/bar_builder_domain_service.py:10-32` defines 1d as
   `replace(hour=0)` and 1w as Monday 00:00; `engine/market_data/sync_internals/bar_filters.py:72-82`
   drops everything else on every sync, called from `engine/market_data/sync_service.py:79-81`;
   `SYNC_INTERVALS` at `engine/market_data/app_services/sync_jobs.py:54-62` includes 1d and 1w.
2. **Cascade.** `engine/market_data/app_services/cascade_aggregator.py:98-137` floors to a fixed
   UTC epoch grid; `_TF_EXPECTED_BARS[DAY_1] = 1440` at line 46.
3. **Integrity.** `engine/market_data/app_services/integrity_jobs.py:62-63` builds a dense
   arithmetic grid; `repair_integrity` at lines 79-116 resyncs 5000 bars per symbol per interval.
4. **Freshness.** `engine/market_data/sync_status_service.py:62-69`,
   `engine/market_data/sync_internals/anomaly_log.py:35-40,52-59`, and
   `web/src/lib/datetime.ts:88-97` all measure `now - last_bar`.
5. **Annualization.** `core/domain/shared/enums.py:5-13` and
   `core/domain/trading/performance_calculator_domain_service.py:13-14,108-109,166-167` hardcode
   365 x 24.

Complete caller inventory for the alignment functions (grep verified, 9 sites, all listed):
- `get_bar_start`: `integrity_jobs.py:51`, `bar_app_service.py:88`,
  `bar_builder_domain_service.py:125` (inside `create_for_tick`),
  `bar_builder_domain_service.py:32` (inside `is_bar_aligned`).
- `is_bar_aligned`: `integrity_jobs.py:57`, `bar_alignment.py:7`,
  `bar_builder_domain_service.py:38` (inside `filter_aligned_bars`).
- `filter_aligned_bars`: `bar_filters.py:74`.
- `has_aligned_bar`: `provider_fetch.py:61`.
Plus after Phase 1 Task 1.6: `core/infra/binance/binance_adapter.py` calls `get_bar_start`.

## Tasks

### Task 3.1 — Capture the golden file BEFORE any behaviour changes

**Goal.** A recorded baseline of crypto bar alignment, cascade boundaries and annualization
that later tasks must reproduce exactly.

**Target files and symbols.**
- New file `tests/engine_test/market_data/golden/crypto_calendar_baseline.json` (data).
- New file `tests/engine_test/market_data/test_crypto_golden_baseline.py`.

**Steps.**
1. Create `tests/engine_test/market_data/test_crypto_golden_baseline.py` containing one test
   function `test_crypto_outputs_match_golden_file` and one module-level helper
   `build_baseline()` that returns a plain dict with three sections, computed from a FIXED
   input window `2026-03-06T00:00:00Z` to `2026-03-11T00:00:00Z` (chosen to span the 2026
   US DST transition so the file would catch an accidental local-time dependency):
   - `"bar_starts"`: for every `Interval` member and for each of 24 hard-coded probe instants
     across the window, the ISO string of the bar start.
   - `"cascade_boundaries"`: for each interval in `CASCADE_TFS`, the list of ISO strings from
     `compute_boundaries(tf, window_start, window_end)`.
   - `"periods_per_year"`: `{iv.value: Interval.periods_per_year_for(iv.value) for iv in Interval}`.
2. Run the helper once and write its JSON output to
   `tests/engine_test/market_data/golden/crypto_calendar_baseline.json` with
   `json.dumps(..., indent=2, sort_keys=True)`.
3. The test loads the JSON file and asserts `build_baseline() == json.load(f)`.
4. Add a comment at the top of the test file:
   `# Golden baseline recorded BEFORE the calendar refactor (plan phase 3, task 1). Any diff here means crypto behaviour changed. Regenerating this file is only correct when the change is deliberate and reviewed.`
5. Later tasks in this phase update `build_baseline()` to pass the 24/7 calendar through the
   new signatures, but MUST NOT regenerate the JSON.

**Success criteria.** The golden file exists and the test passes against current behaviour.

**Verify.**
`uv run pytest tests/engine_test/market_data/test_crypto_golden_baseline.py -q` exits 0 and
prints `1 passed`, AND
`test -f tests/engine_test/market_data/golden/crypto_calendar_baseline.json` exits 0.

### Task 3.2 — Make alignment calendar-driven

**Goal.** Bar alignment is computed by the symbol's calendar, with the 24/7 calendar producing
today's numbers.

**Target files and symbols.**
- `core/domain/bar/services/bar_builder_domain_service.py` -> `get_bar_start`, `is_bar_aligned`,
  `filter_aligned_bars`, `BarBuilderDomainService.create_for_tick`.
- `core/domain/bar/services/__init__.py` -> `__all__`.
- Callers (all of them, no others exist): `engine/market_data/app_services/integrity_jobs.py:51,57`;
  `engine/market_data/app_services/bar_app_service.py:88`;
  `engine/market_data/sync_internals/bar_alignment.py:7`;
  `engine/market_data/sync_internals/bar_filters.py:74`;
  `engine/market_data/sync_internals/provider_fetch.py:61`;
  `core/infra/binance/binance_adapter.py` (added in Phase 1 Task 1.6).
- `tests/core_test/unit/domain/bar/services/test_bar_builder.py` (existing, 10 tests).

**Steps.**
1. Change the three module-level functions to take the calendar as a required final positional
   parameter:
   ```python
   def get_bar_start(timestamp: datetime, interval: Interval, calendar: ITradingCalendarPort) -> datetime:
       """Delegate to the calendar. Kept as a free function so the 9 call sites need no
       object plumbing; the calendar is the only parameter that varies by asset class."""
       return calendar.bar_start(timestamp, interval)


   def is_bar_aligned(timestamp: datetime, interval: Interval, calendar: ITradingCalendarPort) -> bool:
       return timestamp == calendar.bar_start(timestamp, interval)


   def filter_aligned_bars(
       bars: list[Bar], interval: Interval, calendar: ITradingCalendarPort
   ) -> tuple[list[Bar], list[Bar]]:
       ...
   ```
   Delete the old inline 1d/1w/epoch bodies — they now live in
   `Continuous24x7CalendarAdapter.bar_start` (moved there in Phase 2 Task 2.4). Do NOT give
   `calendar` a default value: a default is exactly how "UTC by convention" happened.
2. `filter_aligned_bars` additionally stamps `bar.session_date = calendar.session_date(bar.datetime)`
   and `bar.calendar_id = calendar.calendar_id` on each ALIGNED bar when
   `interval in (Interval.DAY_1, Interval.WEEK_1)`. Add the comment:
   `# Only daily/weekly get a session key; for intraday the UTC instant already is the key.`
3. Add `calendar: ITradingCalendarPort` as a parameter to
   `BarBuilderDomainService.create_for_tick` and pass it through to `get_bar_start`.
4. Update `engine/market_data/sync_internals/bar_alignment.py:6-7`:
   `def has_aligned_bar(records, interval, calendar) -> bool`.
5. Update `engine/market_data/sync_internals/bar_filters.py:72-82`:
   `def drop_misaligned_bars(records, interval, calendar) -> list[Bar]`, forwarding to
   `filter_aligned_bars`. Add `calendar_id=calendar.calendar_id` to the
   `market_data.sync.misaligned_bars_dropped` warning payload.
6. Update `engine/market_data/sync_internals/provider_fetch.py:61` to forward a `calendar`
   parameter added to the enclosing `fetch_with_retry` signature.
7. Update `engine/market_data/sync_service.py`: inject
   `trading_calendar_resolver: TradingCalendarResolverAppService` as a new constructor
   parameter, resolve `calendar = await self._calendar_resolver.resolve(symbol)` once at the
   top of `sync_one`, and pass it to `fetch_with_retry` (line 66) and `drop_misaligned_bars`
   (line 80). Update the `SyncService` provider in `app/di/market_data.py` — it is declared as
   `sync_service = provide(SyncService, scope=Scope.APP)`, so Dishka auto-wires the new
   parameter once the resolver is provided (added in Phase 2 Task 2.6); no explicit edit is
   needed there, but verify with `lint-imports` and the DI test.
8. Update `engine/market_data/app_services/bar_app_service.py:88` — `BarAppService` must
   receive the resolver too. Add `trading_calendar_resolver` to its constructor and to the
   `get_bar_manager` provider in `app/di/market_data.py:28-32`.
9. Update `core/infra/binance/binance_adapter.py` to construct a
   `Continuous24x7CalendarAdapter()` once in `__init__` and pass it to `get_bar_start`. Add the
   comment: `# Binance is always 24/7; the adapter owns its own calendar rather than taking a resolver, because a REST adapter must not depend on the symbol registry.`
10. Update `tests/core_test/unit/domain/bar/services/test_bar_builder.py` to pass
    `Continuous24x7CalendarAdapter()` to every call. Do not change a single expected value.
11. Update `build_baseline()` in the golden test to pass the 24/7 calendar. Do NOT regenerate
    the JSON.

**Success criteria.** Every alignment call site names its calendar explicitly, and the golden
file still matches.

**Verify.**
`uv run pytest tests/engine_test/market_data/test_crypto_golden_baseline.py tests/core_test/unit/domain/bar/services/test_bar_builder.py tests/app_test/unit/handlers/sync/ -q`
exits 0 with a final line containing `passed` and not containing `failed`.

### Task 3.3 — Make the cascade session-anchored

**Goal.** Cascade bucket boundaries and expected counts come from the calendar.

**Target files and symbols.**
- `engine/market_data/app_services/cascade_aggregator.py` -> `compute_boundaries` (lines 98-137),
  `_TF_EXPECTED_BARS` (lines 41-47), `cascade_for_symbol` (lines 140-236).
- `engine/market_data/app_services/sync_jobs.py` -> the `cascade_for_symbol(...)` call sites.
- `engine/market_data/tracked_symbols_backfill.py` -> its `cascade_for_symbol(...)` call site.
- `tests/app_test/market_data/test_cascade_aggregator.py` (existing, 18 tests).

**Steps.**
1. Change the signature to
   `def compute_boundaries(tf, range_start, range_end, calendar: ITradingCalendarPort) -> list[datetime]`.
   Replace the epoch-floor body with:
   ```python
   first = calendar.bar_start(range_start, tf)
   boundaries = []
   current = first
   while current < range_end:
       boundaries.append(current)
       current = calendar.bar_start(current + timedelta(seconds=secs), tf)
   ```
   Add the comment: `# Step by asking the calendar again rather than adding tf_seconds blindly: a session-based calendar must skip the overnight halt and the weekend, and a 24/7 calendar returns exactly current + tf.`
   Keep the existing overlap docstring, replacing the hard-coded "Alignment (UTC)" list with a
   sentence saying alignment is the calendar's.
2. Delete `_TF_EXPECTED_BARS` entirely. In `cascade_for_symbol`, replace
   `expected_count = _TF_EXPECTED_BARS.get(tf, 0)` with
   `expected_count = len(calendar.expected_bar_starts(Interval.MINUTE_1, boundary, bucket_end))`
   computed inside the per-boundary loop (it must move below `bucket_end`). Keep the
   `limit=expected_count + 5` headroom on the `bar_repo.find` call.
3. Add `calendar: ITradingCalendarPort` as a required parameter to `cascade_for_symbol`, after
   `lookback_minutes`. Add `calendar_id=calendar.calendar_id` to the
   `cascade.partial_aggregate` warning payload and to `cascade.completed_tf`.
4. When `tf in (Interval.DAY_1,)`, set `session_date=calendar.session_date(boundary)` and
   `calendar_id=calendar.calendar_id` on the constructed `Bar` (line ~201).
5. Update every `cascade_for_symbol` call site to resolve and pass the calendar. Find them with
   `grep -rn "cascade_for_symbol" src/` and edit each; at time of writing they are in
   `engine/market_data/app_services/sync_jobs.py` and
   `engine/market_data/tracked_symbols_backfill.py`.
6. Update `tests/app_test/market_data/test_cascade_aggregator.py` to pass
   `Continuous24x7CalendarAdapter()`. Do not change a single expected boundary value.

**Success criteria.** Every cascade boundary and expected count for a 24/7 symbol is unchanged.

**Verify.**
`uv run pytest tests/app_test/market_data/test_cascade_aggregator.py tests/engine_test/market_data/test_crypto_golden_baseline.py -q`
exits 0 and prints `19 passed`.

### Task 3.4 — Make the integrity grid calendar-driven

**Goal.** Weekends, halts and holidays stop reading as gaps.

**Target files and symbols.**
- `engine/market_data/app_services/integrity_jobs.py` -> `check_integrity` (lines 36-76),
  `repair_integrity` (lines 79-...).
- `engine/market_data/app_services/sync_jobs.py` -> `_run_integrity` and the `sync_repair`
  entry point (the `check_integrity` / `repair_integrity` call sites).

**Steps.**
1. Add `calendar: ITradingCalendarPort` as a required parameter to `check_integrity` (after
   `bar_repo`) and to `repair_integrity`.
2. In `check_integrity`, replace line 51 `end = get_bar_start(now, interval)` with
   `end = calendar.bar_start(now, interval)`, and line 57
   `if is_bar_aligned(d["datetime"], interval)` with
   `if d["datetime"] == calendar.bar_start(d["datetime"], interval)`.
3. Replace lines 62-63 with:
   ```python
   step = timedelta(seconds=INTERVAL_SECONDS[interval])
   expected = calendar.expected_bar_starts(interval, start, end)
   ```
   `step` is still needed by `_group_gaps`.
4. Replace the docstring note at lines 46-47 with:
   `The expected grid comes from the symbol's calendar, so a venue with sessions reports gaps only inside trading time.`
5. In `repair_integrity`, add a guard at the top:
   ```python
   if interval is Interval.WEEK_1 and calendar.calendar_id != CalendarId.CRYPTO_24_7:
       # No weekly convention exists for session venues yet; resyncing 5000 bars
       # every 12h against a grid we cannot validate is pure churn.
       logger.info("integrity.repair_skipped", symbol=symbol, interval=interval.value,
                   reason="weekly_unsupported_for_calendar", calendar_id=calendar.calendar_id)
       return {"symbol": symbol.upper(), "interval": interval.value, "skipped": True}
   ```
   Match the shape of the dict `repair_integrity` already returns; read its current return
   statement first and add a `"skipped": False` key to the normal path so callers see a
   consistent shape.
6. Update the `check_integrity` and `repair_integrity` call sites in
   `engine/market_data/app_services/sync_jobs.py` to resolve and pass the calendar. Locate them
   with `grep -n "check_integrity\|repair_integrity" src/pocketquant/engine/market_data/app_services/sync_jobs.py`.

**Success criteria.** For a 24/7 symbol the reported `missing_count` is identical to before;
the weekly-repair guard is inert for crypto.

**Verify.**
`uv run pytest tests/app_test/integration/test_sync_backfill_gap_fill.py -q` exits 0 with a
final line containing `passed` and not containing `failed`. (This integration test requires
Docker for testcontainers; if Docker is unavailable, STOP and follow the Failure Protocol
rather than skipping the test.)

### Task 3.5 — Make freshness and anomaly gating session-aware

**Goal.** A closed venue reads as "closed", not "stuck", and emits no per-minute warnings.

**Target files and symbols.**
- `engine/market_data/sync_status_service.py` -> `_is_stuck` (lines 62-69), `SyncStatusResult`
  (lines 46-59), `SyncStatusQueryService.get_sync_status` (line 96 onwards) and the per-symbol
  query method.
- `engine/market_data/sync_internals/anomaly_log.py` -> `emit_no_progress` (lines 20-61).
- `engine/market_data/sync_service.py` -> the `emit_no_progress(...)` call at lines 102-111.
- `tests/app_test/unit/handlers/status/test_sync_status_service.py` (existing, 12 tests).
- `tests/app_test/unit/handlers/sync/test_no_progress_tracking.py` (existing, 5 tests).

**Steps.**
1. Change `_is_stuck` to
   `def _is_stuck(latest_bar_dt: datetime | None, interval: str, calendar: ITradingCalendarPort) -> bool`
   and compute
   ```python
   reference = calendar.previous_close(datetime.now(UTC))
   age = (reference - latest_bar_dt).total_seconds()
   return age > _STUCK_MULTIPLIER * cadence
   ```
   Add the comment: `# Measure against the last expected bar close, not wall-clock now: a venue that is legitimately shut is not stuck. The 24/7 calendar returns `now`, so crypto behaviour is unchanged.`
2. Add `is_market_open: bool = True` to `SyncStatusResult` and populate it from
   `calendar.is_open(datetime.now(UTC))` in both query paths. Add a comment naming the SPA as
   the consumer.
3. In `emit_no_progress`, add a required `calendar: ITradingCalendarPort` parameter and, as the
   first statement:
   ```python
   now = datetime.now(UTC)
   if not calendar.is_open(now):
       logger.debug("market_data.sync.no_progress_closed", symbol=symbol,
                    interval=interval.value, calendar_id=calendar.calendar_id)
       return
   ```
   Add the comment: `# DEBUG, not WARNING: this fires once per interval per symbol for the whole weekend (~2,900 times per 1m futures symbol), and CLAUDE.md forbids a per-iteration event above DEBUG.`
   Compute `age_s` against `calendar.previous_close(now)` instead of `now`.
4. Update the call in `engine/market_data/sync_service.py:102` to pass the resolved calendar.
5. Update both existing test files to pass `Continuous24x7CalendarAdapter()`; expected values
   must not change.

**Success criteria.** Crypto freshness output is identical; the DTO now carries
`is_market_open`.

**Verify.**
`uv run pytest tests/app_test/unit/handlers/status/test_sync_status_service.py tests/app_test/unit/handlers/sync/test_no_progress_tracking.py -q`
exits 0 and prints `17 passed`.

### Task 3.6 — Move annualization off the `Interval` enum

**Goal.** Periods-per-year is the calendar's, not the interval's.

**Target files and symbols.**
- `core/domain/shared/enums.py` -> `Interval.periods_per_year` (lines 25-31),
  `Interval.periods_per_year_for` (lines 33-40), `_PERIODS_PER_YEAR` (lines 5-13).
- `core/domain/trading/performance_calculator_domain_service.py` -> `TRADING_DAYS_PER_YEAR`
  (line 14) and its use at line 52.
- `engine/backtest/backtest_report_app_service.py` -> line 368.
- `engine/live/live_metrics_query_service.py` -> line 64 (passes `periods_per_year=None`; leave
  it alone, and add a comment saying live metrics are deliberately un-annualized).
- `tests/core_test/unit/domain/shared/test_interval.py` (existing, 7 tests).
- `tests/backtest_test/domain/test_performance_calculator_annualization.py` (existing, 9 tests).

**Steps.**
1. Keep `_PERIODS_PER_YEAR` in `enums.py` as the crypto table — `Continuous24x7CalendarAdapter`
   imports it (Phase 2 Task 2.4). Mark both `Interval.periods_per_year` and
   `Interval.periods_per_year_for` deprecated in their docstrings with:
   `Deprecated: use ITradingCalendarPort.periods_per_year(interval). Kept only as the data source for Continuous24x7CalendarAdapter and for the existing enum tests.`
   Do NOT delete them — `test_interval.py` asserts on them and G5 requires crypto numbers to
   stay at 525,600 for 1m.
2. In `engine/backtest/backtest_report_app_service.py` line 368, replace
   `periods_per_year = Interval.periods_per_year_for(self._config.interval)` with a lookup
   through the calendar:
   ```python
   calendar = await self._calendar_resolver.resolve(self._config.symbol)
   try:
       periods_per_year = calendar.periods_per_year(Interval(self._config.interval))
   except (ValueError, KeyError):
       periods_per_year = None
   ```
   keeping the existing `if periods_per_year is None:` warning branch verbatim.
3. Add `trading_calendar_resolver` to the constructor of the class that owns
   `backtest_report_app_service.py`'s reporting path and wire it in `app/di/backtest_worker.py`
   (inspect that file first; if the report service is constructed inside
   `engine/backtest/backtest_dispatch.py` rather than through DI, thread the resolver through
   the same call chain the `bar_repo` already follows).
4. In `core/domain/trading/performance_calculator_domain_service.py`, change line 14 to
   `TRADING_DAYS_PER_YEAR = 365  # calendar days; used ONLY to convert a wall-clock span to years for CAGR. Bar-count annualization comes from ITradingCalendarPort.periods_per_year.`
   Do not change line 52 — CAGR over a wall-clock span is correctly calendar-day based.
5. In `engine/live/live_metrics_query_service.py` line 64, add the comment
   `# Deliberately un-annualized: live metrics cover a partial window of unknown length.`

**Success criteria.** Crypto annualization values are unchanged; the backtest report reads the
calendar.

**Verify.**
`uv run pytest tests/core_test/unit/domain/shared/test_interval.py tests/backtest_test/domain/test_performance_calculator_annualization.py -q`
exits 0 and prints `16 passed`.

### Task 3.7 — Gate the sync cron on the calendar

**Goal.** While a venue is closed, the cron records a skip and never calls the provider.

**Target files and symbols.**
- `engine/market_data/app_services/sync_jobs.py` -> `_sync_by_intervals` (lines 130-...),
  specifically the `for symbol in symbols:` loop at line 164.
- New test file `tests/app_test/unit/market_data/test_sync_gating_on_calendar.py`.

**Steps.**
1. In `_sync_by_intervals`, add a `calendar_resolver: TradingCalendarResolverAppService`
   parameter and, immediately inside the `for symbol in symbols:` loop and before the inner
   `for interval in intervals:` loop:
   ```python
   calendar = await calendar_resolver.resolve(symbol)
   now = datetime.now(UTC)
   grace = timedelta(seconds=INTERVAL_SECONDS[Interval.MINUTE_1])
   if not calendar.is_open(now) and now - calendar.previous_close(now) > grace:
       # One interval of grace so the bar that closed exactly at the bell is still
       # fetched. Beyond that, calling the provider for a shut venue is pure cost.
       logger.debug(f"market_data.{job_name}.skipped_closed", symbol=symbol,
                    calendar_id=calendar.calendar_id)
       if doc_id:
           await history_repo.record_detail(
               doc_id, symbol=symbol, interval="*", bars_fetched=0, bars_inserted=0,
               filtered_existing=0, filtered_misaligned=0, status="skipped_closed",
               error=None,
           )
       continue
   ```
   Import `INTERVAL_SECONDS` from `core.domain.shared.value_objects` (it is keyed by `Interval`,
   not by string, in that module).
2. Update every caller of `_sync_by_intervals` (grep shows two: line 253 and line 398) to
   resolve the resolver from the container and pass it.
3. Create `tests/app_test/unit/market_data/test_sync_gating_on_calendar.py` with exactly two
   test functions using stub repositories and a stub resolver:
   - `test_open_market_symbol_is_synced` — a 24/7 calendar always syncs.
   - `test_closed_market_symbol_is_skipped` — a stub calendar whose `is_open` returns False and
     whose `previous_close` is two hours ago causes `sync_service.sync_one` to be called zero
     times and a `status="skipped_closed"` detail to be recorded.

**Success criteria.** Crypto symbols are never skipped; a closed stub calendar skips before the
provider call.

**Verify.**
`uv run pytest tests/app_test/unit/market_data/test_sync_gating_on_calendar.py -q` exits 0 and
prints `2 passed`.

### Task 3.8 — Prove the crypto path is unchanged end to end

**Goal.** Phase 3 is provably behaviour-preserving for crypto.

**Target files and symbols.**
- The whole test suite; no source edits unless a regression is found.

**Steps.**
1. Run the full suite. Fix any regression by changing the new code, never by loosening a test.
2. Run the suite under both non-UTC zones to confirm the Phase 1 guarantee still holds.
3. Run `lint-imports` and `ruff`.
4. Deploy to the VPS and observe one full `sync_1m` cron cycle. Record, before and after, for
   `BTCUSDT:BINANCE`: `synced_count` from `job_history`, the latest 1m bar `datetime`, and the
   latest 1d bar OHLCV. Store the two readings in
   `plans/260921-1436-asset-class-index-futures/reports/phase-03-cron-parity.md`.

**Success criteria.** Identical suite result, identical cron output.

**Verify.**
All four of the following exit 0:
`uv run pytest tests/ -q` (final line contains `passed`, not `failed`),
`TZ=Asia/Saigon uv run pytest tests/ -q`,
`uv run ruff check src tests` (prints `All checks passed!`),
`uv run lint-imports`.
AND `test -f plans/260921-1436-asset-class-index-futures/reports/phase-03-cron-parity.md` exits 0
and the file records identical before/after values for the three recorded quantities.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A subtle change to 24/7 bucket maths silently shifts crypto bars | Medium | High | Task 3.1 records the golden file first and every later task re-runs it without regenerating it |
| Threading the resolver breaks a DI wiring | Medium | Medium | `lint-imports` plus the full suite run at Task 3.8; the resolver is `Scope.APP`, matching every consumer |
| `compute_boundaries` loops forever if a calendar returns a non-advancing `bar_start` | Low | High | The 24/7 `bar_start` is a pure floor, so `current + tf` always advances; add an assertion `assert next_ > current` inside the loop |
| Making `calendar` a required parameter breaks a caller that was missed | Low | High | The caller inventory is enumerated in Context (9 sites); Python raises `TypeError` at import/call rather than silently defaulting |
| Removing the per-minute `no_progress` WARNING hides a genuine crypto outage | Low | Medium | The 24/7 calendar is always open, so the new short-circuit never fires for crypto |

## Rollback

Each task is a separate commit that changes signatures only. Reverting the phase restores the
previous signatures wholesale. No stored document changes shape except the new optional
`session_date` / `calendar_id` on daily bars, which older code ignores. The golden file stays
in the repository after a rollback and keeps protecting the crypto path.

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
title: "Provider routing adapters and settings"
status: pending
priority: P1
effort: "1d"
dependencies: [3]
---

## Context

DI binds exactly one implementation of each market-data port:
`app/di/infrastructure.py:29-31` returns `BinanceAdapter` for `IDataProviderPort`, and
`app/di/market_data.py:34-36` returns `BinanceWebSocketAdapter` for
`IRealtimeQuoteProviderPort`. Every consumer (`SyncService`, `fetch_with_retry`,
`WsSubscriptionAppService`, `QuoteAppService`) depends on the port, not the adapter.

This phase inserts a routing adapter in front of each port that resolves the concrete provider
per symbol from configuration. It ships with Binance as the ONLY registered provider, so the
crypto path must be byte-for-byte unchanged. That is what makes the next phase's regressions
attributable to TradingView rather than to routing. Delivering this before any futures code is
exactly requirement G4: a third provider becomes one adapter plus one config entry, with zero
caller edits.

Design decision locked here: **realtime is never routed through a fallback chain.** Two WS
providers streaming the same symbol would double-count ticks in `BarBuilderDomainService`.
Fallback is REST-history only.

## Tasks

### Task 4.1 — Add provider configuration to `Settings`

**Goal.** Provider selection is data, read from the environment.

**Target files and symbols.**
- `core/config.py` -> `Settings`, new fields after `reconcile_interval_seconds` (line 74).
- New file `core/domain/market_data/provider_id.py` -> `ProviderId`.
- `README.md` -> the settings list.
- New test file `tests/core_test/unit/test_provider_settings_parsing.py`.

**Steps.**
1. Create `core/domain/market_data/provider_id.py`:
   ```python
   """Stable provider identifiers used in configuration and the routing registry."""

   from typing import Final


   class ProviderId:
       BINANCE: Final = "binance"
       TRADINGVIEW: Final = "tradingview"
   ```
2. In `core/config.py`, add after line 74:
   ```python
   # Market-data provider routing. JSON strings in the environment so a new provider
   # is a config edit, never a code edit.
   #   MARKET_DATA_PROVIDERS='{"crypto_spot":["binance"],"index_future":["tradingview"]}'
   #   SYMBOL_PROVIDER_OVERRIDES='{"ES1!:CME_MINI":["tradingview"]}'
   market_data_providers: dict[str, list[str]] = {
       "crypto_spot": ["binance"],
       "crypto_perp": ["binance"],
   }
   symbol_provider_overrides: dict[str, list[str]] = {}
   ```
   `pydantic-settings` parses a JSON string into a `dict[str, list[str]]` automatically for
   complex types, so no custom validator is needed. Key by the `AssetClass` **value** string,
   not the enum, so the env file stays readable and `core/config.py` keeps its current import
   set.
3. In `README.md`, in the environment-variable section, add a line naming
   `MARKET_DATA_PROVIDERS` and `SYMBOL_PROVIDER_OVERRIDES` with the example JSON above.
   Put no credentials or values beyond these structural examples.
4. Create `tests/core_test/unit/test_provider_settings_parsing.py` with exactly three test
   functions that build `Settings` with `monkeypatch.setenv` over the conftest defaults:
   - `test_defaults_route_crypto_to_binance`
   - `test_json_env_overrides_provider_map`
   - `test_symbol_override_parses`

**Success criteria.** Both settings parse from JSON environment strings and default to
Binance-only crypto routing.

**Verify.**
`uv run pytest tests/core_test/unit/test_provider_settings_parsing.py -q` exits 0 and prints
`3 passed`.

### Task 4.2 — Implement the provider resolver

**Goal.** One place turns a composite symbol into an ordered list of provider ids.

**Target files and symbols.**
- New file `engine/market_data/provider_resolver_app_service.py` ->
  `ProviderResolverAppService`.
- New test file `tests/engine_test/market_data/test_provider_resolver.py`.

**Steps.**
1. Create the service:
   ```python
   class ProviderResolverAppService:
       """Composite symbol -> ordered provider ids (primary first, then fallbacks).

       Resolution order: per-symbol override, then the symbol's asset class, then the
       CRYPTO_SPOT default. Uses the same TTL cache lifetime argument as
       TradingCalendarResolverAppService: the mapping is global, not per request.
       """

       def __init__(
           self,
           settings: Settings,
           symbol_repository: SymbolRepository,
           ttl_seconds: int = 300,
       ) -> None: ...

       async def resolve(self, symbol: str) -> list[str]: ...

       def invalidate(self, symbol: str | None = None) -> None: ...
   ```
2. `resolve` upper-cases the symbol, checks `settings.symbol_provider_overrides`, then loads the
   `Symbol` record via `symbol_repository.find_by_symbol` (added in Phase 2 Task 2.6), then
   looks up `settings.market_data_providers[symbol_record.asset_class.value]`. If nothing
   matches, log `logger.warning("provider.unresolved", symbol=symbol)` once and return
   `[ProviderId.BINANCE]`.
3. Register it in `app/di/market_data.py` at `Scope.APP`.
4. Create `tests/engine_test/market_data/test_provider_resolver.py` with exactly five test
   functions against a stub repository:
   - `test_crypto_symbol_resolves_to_binance`
   - `test_index_future_resolves_to_tradingview`
   - `test_symbol_override_wins_over_asset_class`
   - `test_unknown_symbol_falls_back_to_binance`
   - `test_resolution_is_cached`

**Success criteria.** Override beats asset class; unknown symbols degrade to Binance.

**Verify.**
`uv run pytest tests/engine_test/market_data/test_provider_resolver.py -q` exits 0 and prints
`5 passed`.

### Task 4.3 — Implement `RoutingDataProviderAdapter`

**Goal.** `IDataProviderPort` consumers get per-symbol routing with REST fallback, unchanged.

**Target files and symbols.**
- New file `core/infra/market_data/routing_data_provider_adapter.py` ->
  `RoutingDataProviderAdapter`.
- New file `core/infra/market_data/__init__.py`.
- New test file `tests/core_test/infra/market_data/test_routing_data_provider.py`.

**Steps.**
1. Create the adapter implementing `IDataProviderPort`:
   ```python
   class RoutingDataProviderAdapter(IDataProviderPort):
       """Dispatch fetch_ohlcv / search_symbols to the provider configured for the symbol.

       Because it implements the same port, SyncService, fetch_with_retry and the
       backfill service need no edits. That is requirement G4.
       """

       def __init__(
           self,
           providers: dict[str, IDataProviderPort],
           resolver: ProviderResolverAppService,
       ) -> None: ...
   ```
2. `fetch_ohlcv(symbol, interval, n_bars)`: resolve the ordered ids, then for each id in order,
   look up the adapter and `await` it. On an exception OR an empty list, log
   `logger.warning("provider.fallback", symbol=symbol, provider=pid, reason=...)` and try the
   next. If every provider fails, re-raise the first exception; if all returned empty, return
   `[]`. Log `logger.debug("provider.routed", symbol=symbol, provider=pid, bars=len(bars))`
   on success — DEBUG because it is per-symbol-per-interval-per-cron-tick.
3. `search_symbols(query)`: fan out to every registered provider concurrently with
   `asyncio.gather(..., return_exceptions=True)` and concatenate the successful results. Add
   the comment: `# Search has no symbol to route on, so ask everyone; a failing provider must not blank the result set.`
4. `close()`: `await` every registered provider's `close()`.
5. Create `tests/core_test/infra/market_data/test_routing_data_provider.py` with exactly five
   test functions using in-memory stub providers:
   - `test_routes_to_primary_provider`
   - `test_falls_back_on_exception`
   - `test_falls_back_on_empty_result`
   - `test_raises_first_exception_when_all_fail`
   - `test_search_fans_out_and_tolerates_a_failure`

**Success criteria.** Routing and fallback behave exactly as specified.

**Verify.**
`uv run pytest tests/core_test/infra/market_data/test_routing_data_provider.py -q` exits 0 and
prints `5 passed`.

### Task 4.4 — Implement `RoutingRealtimeQuoteProviderAdapter`

**Goal.** WS subscriptions go to the right provider, with no fallback and no double-counting.

**Target files and symbols.**
- New file `core/infra/market_data/routing_realtime_quote_provider_adapter.py` ->
  `RoutingRealtimeQuoteProviderAdapter`.
- New test file `tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py`.

**Steps.**
1. Implement all nine members of the `IRealtimeQuoteProviderPort` Protocol
   (`core/domain/market_data/realtime_quote_provider_port.py:26-58`):
   `last_tick_at`, `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`,
   `is_connected`, `subscription_count`, `subscriptions`.
2. Behaviour:
   - `connect` / `disconnect`: fan out to every child with
     `asyncio.gather(..., return_exceptions=True)`.
   - `subscribe(symbol, callback)`: resolve the provider list and delegate to the FIRST id only.
     Add the comment: `# First provider only. Two WS feeds on one symbol would double-count ticks in BarBuilderDomainService, so realtime never uses the fallback chain.`
     Record `symbol -> provider_id` in an instance dict so `unsubscribe` finds the owner.
   - `unsubscribe(symbol)`: delegate to the recorded owner and drop the mapping.
   - `run_forever`: `await asyncio.gather(*(p.run_forever() for p in children))`.
   - `is_connected`: True when at least one child with an active subscription is connected.
   - `subscription_count`: sum of children's counts. `subscriptions`: merged dict.
   - `last_tick_at`: the maximum non-None `last_tick_at` across children.
3. Create `tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py` with
   exactly five test functions:
   - `test_satisfies_protocol` — `isinstance(adapter, IRealtimeQuoteProviderPort)` is True
     (the Protocol is `@runtime_checkable`)
   - `test_subscribe_goes_to_first_provider_only`
   - `test_unsubscribe_reaches_the_owning_provider`
   - `test_subscription_count_is_the_sum`
   - `test_last_tick_at_is_the_max`

**Success criteria.** The routing adapter satisfies the runtime-checkable Protocol and never
double-subscribes.

**Verify.**
`uv run pytest tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py -q`
exits 0 and prints `5 passed`.

### Task 4.5 — Bind the routing adapters in DI with Binance as the only provider

**Goal.** The container hands out the routing adapters, registering exactly one provider.

**Target files and symbols.**
- `app/di/infrastructure.py` -> `InfrastructureProvider.get_data_provider` (lines 29-31).
- `app/di/market_data.py` -> `MarketDataProvider.get_realtime_quote_provider` (lines 34-36).

**Steps.**
1. In `app/di/infrastructure.py`, change `get_data_provider` to:
   ```python
   @provide(scope=Scope.APP)
   def get_data_provider(
       self, settings: Settings, resolver: ProviderResolverAppService
   ) -> IDataProviderPort:
       # Binance is the only registered provider at this phase. Adding TradingView is
       # one entry in this dict plus one entry in MARKET_DATA_PROVIDERS - no caller edit.
       return RoutingDataProviderAdapter(
           providers={ProviderId.BINANCE: BinanceAdapter(settings=settings)},
           resolver=resolver,
       )
   ```
2. In `app/di/market_data.py`, change `get_realtime_quote_provider` the same way, registering
   `{ProviderId.BINANCE: BinanceWebSocketAdapter()}` and keeping the existing
   `# type: ignore[return-value]  # Protocol satisfied structurally` comment.
3. Do NOT touch `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService` or
   `QuoteAppService`. If any of them needs an edit, STOP — that means the routing adapter does
   not actually satisfy the port and the Failure Protocol applies.

**Success criteria.** The container resolves both ports to the routing adapters, and no
consumer file changed.

**Verify.**
`git diff --stat HEAD~1 -- src/pocketquant/engine src/pocketquant/app/routes` prints no lines
(the routing change touched neither the engine consumers nor the routes), AND
`uv run pytest tests/ -q` exits 0 with a final line containing `passed` and not containing
`failed`.

### Task 4.6 — Prove G4 with a config-only third provider, and confirm prod parity

**Goal.** A new provider is demonstrably one adapter plus one config entry.

**Target files and symbols.**
- New test file `tests/engine_test/market_data/test_g4_config_only_provider.py`.
- `plans/260921-1436-asset-class-index-futures/reports/phase-04-cron-parity.md` (new).

**Steps.**
1. Create `tests/engine_test/market_data/test_g4_config_only_provider.py` with exactly two test
   functions:
   - `test_config_only_provider_receives_the_fetch` — define a `_StubProvider(IDataProviderPort)`
     inside the test file, build a `RoutingDataProviderAdapter` registering both Binance-stub
     and the new stub, build a `Settings` whose `symbol_provider_overrides` lists the new stub
     first for `"XYZ:TEST"`, and assert the new stub received the `fetch_ohlcv` call while the
     Binance stub received zero calls.
   - `test_adding_the_provider_touched_no_consumer` — assert that
     `pocketquant.engine.market_data.sync_service` and
     `pocketquant.engine.market_data.app_services.ws_subscription_app_service` contain no
     occurrence of the string `"tradingview"` or `"_StubProvider"`, by reading their source with
     `inspect.getsource`.
2. Deploy to the VPS and observe one full `sync_1m` cycle. Record `synced_count` and the latest
   1m bar `datetime` for `BTCUSDT:BINANCE` before and after, in
   `plans/260921-1436-asset-class-index-futures/reports/phase-04-cron-parity.md`.

**Success criteria.** The stub provider is reachable by configuration alone; production cron
output is unchanged.

**Verify.**
`uv run pytest tests/engine_test/market_data/test_g4_config_only_provider.py -q` exits 0 and
prints `2 passed`, AND
`test -f plans/260921-1436-asset-class-index-futures/reports/phase-04-cron-parity.md` exits 0
with identical before/after values recorded.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The routing realtime adapter misses a Protocol member and DI resolution fails at runtime | Medium | High | Task 4.4 asserts `isinstance(..., IRealtimeQuoteProviderPort)` against the `@runtime_checkable` Protocol |
| Fallback masks a real primary-provider outage | Medium | Medium | Every fallback logs `provider.fallback` at WARNING with the reason; Phase 7 surfaces it on `/health` |
| An empty-result fallback re-fetches from a second provider during a legitimate quiet period | Medium | Low | Accepted: an empty result is cheap; the alternative (treating empty as success) hides a dead primary |
| `symbol_provider_overrides` holds a stale symbol after a rename | Low | Low | `resolve` falls through to the asset-class map and logs `provider.unresolved` |

## Rollback

Revert Task 4.5 alone to restore the direct Binance bindings; the routing adapters and the
resolver then become dead code that harms nothing. No configuration is required for rollback
because the defaults already point crypto at Binance.

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
title: "TradingView history adapter, seed and backfill"
status: pending
priority: P1
effort: "2d"
dependencies: [4]
---

## Context

With the calendar and the routing layer proven on crypto, the scraper can be added behind the
existing `IDataProviderPort`. Two constraints shape the code:

- **The scraper's own timestamps are unusable.** `tvdatafeed` builds bar timestamps with naive
  LOCAL time at `tvDatafeed/main.py:143`. The mapper MUST build every timestamp from the raw
  epoch field with `datetime.fromtimestamp(ts, tz=UTC)`. Combined with the Phase 1 `TZ=UTC`
  pin, both paths then yield the same instant, but relying on the pin alone is the exact trap
  the audit calls out.
- **Entitlement is configuration, never a branch.** Bar cap, delay flag and credentials are
  `Settings` fields. There is no `if plan == "premium"` anywhere.

`core/common/constants.py` already carries `LIMIT_TVDATAFEED_MAX_BARS = 5000`, a fossil from a
previous migration away from this library. Reuse it as the default rather than inventing a
second constant.

Secrets rule: no TradingView username, password or auth token may appear in this repository,
in tests, in docs or in any committed env file. Values live only in
`../pocketquant-config/vps/*.env` (production) and `../pocketquant-config/local/all-local.env`
(development).

## Tasks

### Task 5.1 — Add TradingView settings (field names only)

**Goal.** Credentials, bar cap, poll cadence and the delay flag are configuration.

**Target files and symbols.**
- `core/config.py` -> `Settings`, new fields after the provider-routing fields added in
  Phase 4 Task 4.1.
- `README.md` -> the environment-variable section.
- New test file `tests/core_test/unit/test_tradingview_settings.py`.

**Steps.**
1. In `core/config.py`, add:
   ```python
   # TradingView data provider. Values live ONLY in ../pocketquant-config; this repo
   # carries field names and structural defaults. Entitlement is config, never a code
   # branch: raising the bar cap or buying the CME non-professional add-on is an env
   # edit.
   tradingview_username: str | None = None
   tradingview_password: SecretStr | None = None
   tradingview_auth_token: SecretStr | None = None
   tradingview_max_bars: int = LIMIT_TVDATAFEED_MAX_BARS
   tradingview_poll_seconds: int = 60
   tradingview_delayed_data: bool = True
   ```
   Import `LIMIT_TVDATAFEED_MAX_BARS` from `pocketquant.core.common.constants`. `SecretStr` is
   already imported at `core/config.py:6`.
   Note the poll default is **60**, not 10: with CME data delayed by 10 minutes on every
   TradingView plan until the non-professional add-on is bought, polling faster only raises
   ban risk. Record that reason in the comment.
2. In `README.md`, list the six variable names (`TRADINGVIEW_USERNAME`, `TRADINGVIEW_PASSWORD`,
   `TRADINGVIEW_AUTH_TOKEN`, `TRADINGVIEW_MAX_BARS`, `TRADINGVIEW_POLL_SECONDS`,
   `TRADINGVIEW_DELAYED_DATA`) and state that values live in `../pocketquant-config`. Write no
   value for any credential field.
3. Create `tests/core_test/unit/test_tradingview_settings.py` with exactly three test functions:
   - `test_credentials_default_to_none`
   - `test_max_bars_defaults_to_the_shared_constant`
   - `test_password_is_a_secret_str` — assert `"hunter" not in str(settings.tradingview_password)`
     after setting it via `monkeypatch.setenv`, so a log line can never leak it.

**Success criteria.** Settings load with no TradingView value present; the secret fields never
render.

**Verify.**
`uv run pytest tests/core_test/unit/test_tradingview_settings.py -q` exits 0 and prints
`3 passed`, AND `git grep -i "tradingview_.*=" -- ':!*.md'` prints only field declarations in
`src/pocketquant/core/config.py` and assignments in test files that use placeholder values.

### Task 5.2 — Define the internal TradingView client seam

**Goal.** The scraper library is swappable behind one interface.

**Target files and symbols.**
- New file `core/infra/tradingview/tradingview_client_port.py` -> `RawBar`,
  `ITradingViewClientPort`.
- New file `core/infra/tradingview/__init__.py`.

**Steps.**
1. Create the port file:
   ```python
   """Internal seam between the TradingView adapters and whichever scraper backs them.

   One port per file, per docs/code-standards.md. This port lives in core/infra rather
   than core/domain because it is an implementation detail of the TradingView adapter
   pair, not a domain concept: the domain boundary is IDataProviderPort.
   """

   from __future__ import annotations

   from abc import ABC, abstractmethod
   from dataclasses import dataclass


   @dataclass(frozen=True)
   class RawBar:
       """One provider row, before any domain mapping.

       `epoch_seconds` is the bar OPEN time as a UNIX timestamp. It is the only
       timestamp this codebase trusts from the scraper: tvdatafeed builds its
       DataFrame index with naive LOCAL time (tvDatafeed/main.py:143).
       """

       epoch_seconds: float
       open: float
       high: float
       low: float
       close: float
       volume: float


   class ITradingViewClientPort(ABC):
       @abstractmethod
       async def fetch_bars(
           self,
           code: str,
           exchange: str,
           interval: str,
           n_bars: int,
           fut_contract: int | None = None,
       ) -> list[RawBar]: ...

       @abstractmethod
       def is_authenticated(self) -> bool: ...

       @abstractmethod
       async def close(self) -> None: ...
   ```

**Success criteria.** The port imports and the layering contracts still hold.

**Verify.**
`uv run python -c "from pocketquant.core.infra.tradingview.tradingview_client_port import ITradingViewClientPort, RawBar; print(RawBar(1.0,1,1,1,1,1).epoch_seconds)"`
exits 0 and prints `1.0`, AND `uv run lint-imports` exits 0.

### Task 5.3 — Implement the `tvdatafeed`-backed client

**Goal.** A synchronous scraper library is usable from the async runtime without blocking the
event loop, and a login failure degrades instead of crashing.

**Target files and symbols.**
- `pyproject.toml` -> `[project] dependencies`.
- New file `core/infra/tradingview/tvdatafeed_client_adapter.py` ->
  `TvDatafeedClientAdapter`.
- New test file `tests/core_test/infra/tradingview/test_tvdatafeed_client_adapter.py`.

**Steps.**
1. Add the scraper to `[project] dependencies`. Use the maintained fork referenced by the
   advice:
   `"tvdatafeed @ git+https://github.com/rongardF/tvdatafeed.git",`
   with the comment:
   `# Unofficial TradingView scraper. Isolated behind ITradingViewClientPort so a break is one adapter swap, not a rewrite. See plan phase 5 trade-offs.`
   Run `uv sync`. **[UNVERIFIED]** — this git URL was not resolved from this environment. If
   `uv sync` fails, STOP and follow the Failure Protocol rather than substituting a different
   package.
2. Create `TvDatafeedClientAdapter(ITradingViewClientPort)`:
   - `__init__(self, settings: Settings)` stores the settings and lazily constructs the
     library's `TvDatafeed` object on first use.
   - Login: when `settings.tradingview_username` and `tradingview_password` are both present,
     attempt an authenticated construction inside `asyncio.to_thread`. On any exception, log
     `logger.warning("provider.tradingview.auth_degraded", reason=str(exc))`, fall back to the
     library's anonymous mode, and set `self._authenticated = False`. Never re-raise: a login
     failure must not crash the process.
   - `fetch_bars(...)`: wrap the library's `get_hist(...)` call in `asyncio.to_thread` (the
     library is synchronous and thread-based). Read the returned DataFrame's INDEX as epoch
     seconds via `int(ts.timestamp())` only if the index is tz-aware; otherwise read the raw
     epoch column the library exposes. Add the comment:
     `# Never trust the DataFrame's datetime index: tvDatafeed/main.py:143 builds it with naive local time. Build RawBar.epoch_seconds from the epoch value and let the mapper attach UTC.`
     Return `list[RawBar]`.
   - `is_authenticated()` returns `self._authenticated`.
   - `close()` is a no-op coroutine (the library opens a socket per call).
3. Create `tests/core_test/infra/tradingview/test_tvdatafeed_client_adapter.py` with exactly
   three test functions, all offline (monkeypatch the library symbol, never hit the network):
   - `test_login_failure_degrades_without_raising`
   - `test_fetch_bars_runs_off_the_event_loop` — assert the patched `get_hist` was called from
     a thread other than the one running the test's event loop
   - `test_fetch_bars_returns_raw_bars_with_epoch_seconds`

**Success criteria.** The client never blocks the loop and never raises on a login failure.

**Verify.**
`uv run pytest tests/core_test/infra/tradingview/test_tvdatafeed_client_adapter.py -q` exits 0
and prints `3 passed`.

### Task 5.4 — Write the TradingView mappers

**Goal.** Symbol, interval and bar translation are pure functions with offline tests.

**Target files and symbols.**
- New file `core/infra/tradingview/tradingview_mappers.py` -> `INTERVAL_TO_TRADINGVIEW`,
  `split_composite_symbol`, `raw_bar_to_bar`.
- New fixture file `tests/core_test/infra/tradingview/fixtures/es1_1h_raw.json`.
- New test file `tests/core_test/infra/tradingview/test_tradingview_mappers.py`.

**Steps.**
1. Create `tradingview_mappers.py`:
   ```python
   INTERVAL_TO_TRADINGVIEW: dict[Interval, str] = {
       Interval.MINUTE_1: "1",
       Interval.MINUTE_5: "5",
       Interval.MINUTE_15: "15",
       Interval.HOUR_1: "60",
       Interval.HOUR_4: "240",
       Interval.DAY_1: "1D",
       Interval.WEEK_1: "1W",
   }


   def split_composite_symbol(symbol: str) -> tuple[str, str, int | None]:
       """'ES1!:CME_MINI' -> ('ES', 'CME_MINI', 1).

       A trailing '<n>!' marks a TradingView continuous contract; the digit is the
       fut_contract argument and is stripped from the code. Anything else returns
       (code, exchange, None).
       """


   def raw_bar_to_bar(
       raw: RawBar, symbol: str, interval: Interval, calendar: ITradingCalendarPort
   ) -> Bar:
       """Map one provider row to a domain Bar.

       The timestamp is built from raw.epoch_seconds with tz=UTC. The scraper's own
       datetime index is naive local time and must never be used.
       For DAY_1 and WEEK_1 the session_date and calendar_id fields are stamped.
       """
   ```
2. `raw_bar_to_bar` builds `datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)` and, when
   `interval in (Interval.DAY_1, Interval.WEEK_1)`, sets
   `session_date=calendar.session_date(ts)` and `calendar_id=calendar.calendar_id`.
3. Create the offline fixture `tests/core_test/infra/tradingview/fixtures/es1_1h_raw.json`
   containing a JSON array of at least eight rows, each an object with keys
   `epoch_seconds, open, high, low, close, volume`. Choose epochs that span the 2026-03-08
   spring-forward, including the 22:00 UTC session open of `2026-03-09`. Write the values by
   hand; do not fetch them from the network.
4. Create `tests/core_test/infra/tradingview/test_tradingview_mappers.py` with exactly six test
   functions:
   - `test_splits_continuous_contract_symbol` — `split_composite_symbol("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)`
   - `test_splits_plain_symbol` — `split_composite_symbol("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)`
   - `test_interval_map_covers_every_interval` — every `Interval` member is a key
   - `test_raw_bar_timestamp_is_utc_from_epoch` — the mapped `Bar.datetime.tzinfo` is UTC and
     equals the hand-computed instant
   - `test_daily_bar_gets_session_date` — a fixture row at the 2026-03-09 session open maps to
     `session_date == date(2026, 3, 9)` and `calendar_id == "CME_GLOBEX_EQUITY"`
   - `test_mapper_never_emits_naive_datetime` — every mapped bar from the fixture is aware

**Success criteria.** Mapping is deterministic, offline, and UTC by construction.

**Verify.**
`uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q` exits 0 and
prints `6 passed`.

### Task 5.5 — Implement `TradingViewAdapter` (the history port)

**Goal.** `IDataProviderPort` is satisfied by TradingView, with the bar cap and the in-progress
bar handled.

**Target files and symbols.**
- New file `core/infra/tradingview/tradingview_adapter.py` -> `TradingViewAdapter`.
- New test file `tests/core_test/infra/tradingview/test_tradingview_adapter.py`.

**Steps.**
1. Implement `TradingViewAdapter(IDataProviderPort)` with
   `__init__(self, client: ITradingViewClientPort, settings: Settings, calendar: ITradingCalendarPort)`.
   Add the comment: `# The calendar is injected, not resolved per symbol: every symbol routed to this adapter is an INDEX_FUTURE, and a REST adapter must not depend on the symbol registry (same reasoning as BinanceAdapter).`
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - `code, exchange, fut_contract = split_composite_symbol(symbol)`
   - `capped = min(n_bars, self._settings.tradingview_max_bars)`; when `capped < n_bars`, log
     `logger.info("tradingview.n_bars_clamped", requested=n_bars, capped=capped)` — INFO
     because it is one line per backfill, not per bar.
   - call `self._client.fetch_bars(code, exchange, INTERVAL_TO_TRADINGVIEW[interval], capped, fut_contract)`
   - map each row with `raw_bar_to_bar`
   - drop the in-progress bar: `cutoff = self._calendar.bar_start(datetime.now(UTC), interval)`
     then keep only bars with `b.datetime < cutoff`. Log the dropped count at DEBUG, mirroring
     `binance_adapter.py:108-114`.
   - return in ascending `datetime` order.
3. `search_symbols(query)`: return `[]` with a one-line docstring saying TradingView symbol
   search is not exposed by the scraper seam and is intentionally a no-op so the routing
   adapter's fan-out stays harmless.
4. `close()`: `await self._client.close()`.
5. Create `tests/core_test/infra/tradingview/test_tradingview_adapter.py` with exactly five
   test functions against a stub client fed from the Task 5.4 fixture:
   - `test_clamps_n_bars_to_the_configured_cap`
   - `test_drops_the_in_progress_bar`
   - `test_returns_ascending_order`
   - `test_every_returned_bar_is_tz_aware_utc`
   - `test_search_symbols_returns_empty_list`

**Success criteria.** The adapter satisfies the port and never emits a naive or in-progress bar.

**Verify.**
`uv run pytest tests/core_test/infra/tradingview/ -q` exits 0 and prints `14 passed` (3 + 6 + 5).

### Task 5.6 — Register TradingView in DI and configuration

**Goal.** `INDEX_FUTURE` symbols route to TradingView by configuration alone.

**Target files and symbols.**
- `app/di/infrastructure.py` -> `get_data_provider` (edited in Phase 4 Task 4.5).
- `../pocketquant-config/local/all-local.env` and `../pocketquant-config/vps/*.env` (OUTSIDE
  this repository).

**Steps.**
1. In `app/di/infrastructure.py`, add `ProviderId.TRADINGVIEW` to the `providers` dict:
   ```python
   providers={
       ProviderId.BINANCE: BinanceAdapter(settings=settings),
       ProviderId.TRADINGVIEW: TradingViewAdapter(
           client=TvDatafeedClientAdapter(settings=settings),
           settings=settings,
           calendar=get_calendar(CalendarId.CME_GLOBEX_EQUITY),
       ),
   },
   ```
2. In the config repository (NOT this one), add to both the local and the VPS env files:
   ```
   MARKET_DATA_PROVIDERS={"crypto_spot":["binance"],"crypto_perp":["binance"],"index_future":["tradingview"]}
   TRADINGVIEW_USERNAME=...
   TRADINGVIEW_PASSWORD=...
   TRADINGVIEW_MAX_BARS=5000
   TRADINGVIEW_POLL_SECONDS=60
   TRADINGVIEW_DELAYED_DATA=true
   ```
   Fill the credential values from the user's TradingView account. Never write them into this
   repository.

**Success criteria.** With `MARKET_DATA_PROVIDERS` set, an `INDEX_FUTURE` symbol resolves to
`["tradingview"]`; crypto still resolves to `["binance"]`.

**Verify.**
`uv run pytest tests/ -q` exits 0 with a final line containing `passed` and not containing
`failed`, AND `git status --porcelain ../pocketquant-config` is not run from this repository
(the config repo is separate) — instead confirm with
`git grep -n "TRADINGVIEW_PASSWORD" -- . ':!*.md'` exiting 1 (no match in this repo).

### Task 5.7 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist in `symbols` and
`tracked_symbols` with the correct asset class, calendar and contract spec.

**Target files and symbols.**
- New file `scripts/seed_index_future_symbols.py`.
- `scripts/README.md` -> one bullet.

**Steps.**
1. Create `scripts/seed_index_future_symbols.py` following `scripts/README.md` conventions:
   reads `MONGODB_URL` / `MONGODB_DATABASE` from the environment, dry run by default,
   `--apply` to write.
2. For each of the three composite symbols it upserts a `symbols` document built from
   `Symbol.create(symbol, name=..., asset_class=AssetClass.INDEX_FUTURE, calendar_id=CalendarId.CME_GLOBEX_EQUITY, contract_spec=CONTRACT_SPECS[symbol])`
   and a `tracked_symbols` document with `seeded_from="admin"`.
   Names: `"E-mini S&P 500 continuous"`, `"E-mini Nasdaq-100 continuous"`,
   `"E-mini Dow continuous"`.
3. Print `seed_index_future_symbols symbols=N tracked=M dry_run=<bool>`.
4. Add a bullet to `scripts/README.md`.

**Success criteria.** All three symbols are present in both collections with
`asset_class="index_future"` and `calendar_id="CME_GLOBEX_EQUITY"`.

**Verify.**
`uv run python scripts/seed_index_future_symbols.py --apply` exits 0, then
`curl -s "http://localhost:41921/api/v1/tracked-symbols" | grep -c "ES1!:CME_MINI"` prints `1`
(with the app running via `just be`).

### Task 5.8 — Run the initial backfill and confirm G1

**Goal.** Historical bars exist up to the configured cap and the cron accumulates forward.

**Target files and symbols.**
- The existing admin route `POST /api/v1/tracked-symbols/{symbol}/backfill`
  (`app/routes/tracked_symbols.py:83-94`).
- `plans/260921-1436-asset-class-index-futures/reports/phase-05-backfill.md` (new).

**Steps.**
1. For each of the three symbols and each of the seven intervals (`1m`, `5m`, `15m`, `1h`,
   `4h`, `1d`, `1w`), call the backfill route with `mode=direct` and `n` equal to
   `TRADINGVIEW_MAX_BARS`. Use `mode=direct` for every interval, not `cascade`: cascading
   futures daily bars from 1m across UTC midnight would produce daily bars that never match the
   TradingView chart, and the calendar-aware alignment from Phase 3 keeps natively fetched 1d
   and 1w bars.
2. Record, per symbol and interval, the resulting bar count and the earliest and latest
   `datetime`, in `plans/260921-1436-asset-class-index-futures/reports/phase-05-backfill.md`.
3. During a live CME session, confirm G1.
4. Let the cron run for one full week including a weekend, then grep the application log for
   the five anomaly events.

**Success criteria.** G1 holds during a session; the anomaly count for ES over a full week
including a weekend is zero; the cascade oracle reports no divergence.

**Verify.**
All three of the following:
(a) During a session,
`curl -s "http://localhost:41921/api/v1/market-data/ohlcv/ES1%21%3ACME_MINI/1m?limit=1"`
returns a body whose `datetime` is within 12 minutes of now (the 12-minute allowance covers
`TRADINGVIEW_DELAYED_DATA=true`).
(b) After one full week,
`grep -cE "misaligned_bars_dropped|integrity.issues_found|no_progress|stuck_threshold_crossed|partial_aggregate" <app log> | grep "ES1!:CME_MINI"`
yields `0`.
(c) `sync_verify_cascade` run against `ES1!:CME_MINI` reports `divergent_fraction` equal to
`0.0` in its log line.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The `tvdatafeed` git dependency does not resolve or breaks on login | High | High | `ITradingViewClientPort` isolates it; login failure degrades to anonymous with a WARNING; Task 5.3 step 1 is tagged `[UNVERIFIED]` and stops on failure |
| The library returns a naive local-time index and a bar lands one zone off | High if unguarded | High | `RawBar.epoch_seconds` is the only accepted timestamp; `test_mapper_never_emits_naive_datetime` enforces it; `Bar.datetime` is `AwareDatetime` from Phase 1 |
| CME data is 10 minutes delayed and G1's 2-minute target cannot be met | High | Low | The verification allows 12 minutes while `TRADINGVIEW_DELAYED_DATA=true`; tightening it is an account purchase, not a code change |
| The 5,000-bar cap yields only ~4 trading days of 1m history | Certain | Medium | Accepted user trade-off; the cron accumulates forward and higher timeframes are usable immediately |
| A credential leaks into the repository | Low | High | Task 5.1 and Task 5.6 both verify with `git grep`; values live only in `../pocketquant-config` |
| Polling or backfilling too aggressively triggers a TradingView ban | Medium | High | `tradingview_poll_seconds` defaults to 60; backfill is a one-off manual run |

## Rollback

Remove `"index_future"` from `MARKET_DATA_PROVIDERS` — the routing adapter then has no
TradingView route and the three symbols simply stop updating; nothing else changes. To roll
back fully, delete the three `tracked_symbols` documents (stopping the cron from touching them)
and revert the DI registration in Task 5.6. Bars already stored remain valid because the domain
model is provider-neutral; a future provider writing the same `(symbol, interval, datetime)`
key upserts over them.

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

=== FILE: phase-06-quotes-and-contract-aware-trading.md ===
---
phase: 6
title: "Polling quotes and contract-aware broker and backtest"
status: pending
priority: P1
effort: "1.5d"
dependencies: [5]
---

## Context

Two independent pieces complete the trading path.

**Realtime.** `IRealtimeQuoteProviderPort` is a nine-member Protocol
(`core/domain/market_data/realtime_quote_provider_port.py:26-58`). TradingView offers no
public WebSocket through the scraper seam, so the first implementation polls the history
endpoint and emits on bar-close change. `last_tick_at` semantics therefore differ from a real
tick feed and the staleness watchdog needs a looser threshold for this provider.

**Contract maths.** `PaperBrokerAdapter` already uses futures/margin accounting (1x leverage,
only close and reduce touch the balance) from plan `260628-2013`; see
`docs/journals/2026-06-28-paper-broker-futures-accounting.md`. That is MARGIN accounting, not
contract specs. It stays exactly as it is. What is missing is the unit conversion: PnL must be
`(exit - entry) x multiplier x contracts`, not `(exit - entry) x quantity`.

The single correct insertion point is `PositionAggregate`
(`core/domain/position/entities.py`), because both realized PnL (`reduce_quantity`, line 149)
and unrealized PnL (`unrealized_pnl` property, line 227) route through
`_calculate_pnl_per_unit` (line 217). Adding the multiplier there covers both with one change
(DRY) and automatically flows into `PaperBrokerAdapter._reduce_and_credit`
(`core/infra/brokers/paper/paper_broker_adapter.py:601-614`) and the equity snapshot at
line 420.

## Tasks

### Task 6.1 — Implement the polling quote adapter

**Goal.** Futures symbols produce quote ticks during session hours, and none while closed.

**Target files and symbols.**
- New file `core/infra/tradingview/tradingview_quote_adapter.py` ->
  `TradingViewQuoteAdapter`.
- New test file `tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py`.

**Steps.**
1. Implement all nine Protocol members. Constructor:
   `__init__(self, client: ITradingViewClientPort, settings: Settings, calendar: ITradingCalendarPort)`.
2. `subscribe(symbol, callback)` records the callback and starts one `asyncio.Task` per symbol.
   Return the composite symbol as the subscription key, matching
   `BinanceWebSocketAdapter.subscribe` (`core/infra/binance/binance_websocket_adapter.py:76-88`).
3. Each polling task loops with `await asyncio.sleep(settings.tradingview_poll_seconds)` and, on
   each wake:
   - skip entirely when `not calendar.is_open(datetime.now(UTC))`, logging nothing (a
     per-poll log for a closed venue is exactly the flood CLAUDE.md forbids);
   - otherwise fetch the latest two 1m bars through the client, and when the latest CLOSED
     bar's `close` differs from the last emitted value, build the existing quote dict contract
     and invoke the callback. Read the exact dict shape from
     `core/infra/binance/binance_mappers.py` (`aggtrade_to_quote_dict`) and reproduce every key.
   - set `self.last_tick_at = datetime.now(UTC)` on every successful poll, whether or not the
     price changed. Add the comment:
     `# Refresh on every successful poll, not only on a price change: the 30s staleness watchdog reads this field, and a genuinely flat market must not look like a dead feed.`
4. `is_connected()` returns `self._client.is_authenticated() and self._polling`.
5. `unsubscribe(symbol)` cancels and awaits that symbol's task.
6. `tick_count` in each emitted quote is `1`; document in the module docstring that per-tick
   volume deltas are unavailable from a polled bar feed.
7. Create `tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py` with exactly
   five test functions, all offline:
   - `test_satisfies_realtime_protocol` — `isinstance(adapter, IRealtimeQuoteProviderPort)`
   - `test_no_poll_while_market_closed`
   - `test_emits_on_close_change`
   - `test_does_not_emit_when_close_unchanged`
   - `test_last_tick_at_updates_on_every_successful_poll`

**Success criteria.** The adapter satisfies the Protocol, stays silent while closed, and emits
only on a change.

**Verify.**
`uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q` exits 0
and prints `5 passed`.

### Task 6.2 — Widen the staleness threshold for polling providers and register the adapter

**Goal.** A 60-second poll cadence does not trip a 30-second watchdog.

**Target files and symbols.**
- `core/infra/binance/binance_websocket_adapter.py` -> the stale-connection watchdog (search
  for `_stale_connection_watchdog`, referenced at line 118). **Do not change Binance's own
  threshold.**
- `engine/market_data/app_services/quote_app_service.py` -> wherever it compares
  `last_tick_at` against a fixed staleness window (grep for `last_tick_at` in that file).
- `app/di/market_data.py` -> `get_realtime_quote_provider`.

**Steps.**
1. Grep for the staleness constant with
   `grep -rn "last_tick_at" src/pocketquant/engine src/pocketquant/app`. For every comparison
   found outside the Binance adapter, replace the hard-coded window with
   `max(<existing window>, 3 * settings.tradingview_poll_seconds)` ONLY when the provider for
   that symbol is TradingView; otherwise leave the existing window. If the comparison has no
   access to the provider id, add a `staleness_window_seconds` property to
   `IRealtimeQuoteProviderPort`'s concrete adapters and read it from the routing adapter's
   owner map instead of branching on a provider name string.
2. In `app/di/market_data.py`, register `ProviderId.TRADINGVIEW: TradingViewQuoteAdapter(...)`
   in the `providers` dict of the `RoutingRealtimeQuoteProviderAdapter`.

**Success criteria.** A TradingView-backed symbol at a 60-second cadence never reports a stale
feed while the session is open; Binance thresholds are untouched.

**Verify.**
`uv run pytest tests/app_test/unit/market_data/test_quote_app_service.py tests/core_test/infra/binance/test_binance_websocket_client.py -q`
exits 0 with a final line containing `passed` and not containing `failed`.

### Task 6.3 — Add the per-contract commission model

**Goal.** Futures commission is charged per contract, not as a percentage of notional.

**Target files and symbols.**
- `core/domain/trading/commission_model.py` -> new `PerContractCommissionModel` next to
  `PercentageCommissionModel` (lines 8-13).
- `core/domain/trading/__init__.py` -> export it.
- `tests/core_test/unit/domain/trading/test_commission_model.py` (existing).

**Steps.**
1. Append to `commission_model.py`:
   ```python
   class PerContractCommissionModel:
       """Flat fee per contract, the standard futures convention.

       Satisfies the same CommissionModel Protocol (compute(price, quantity)); price is
       ignored because the fee does not scale with notional.
       """

       def __init__(self, usd_per_contract: float) -> None:
           self._usd_per_contract = usd_per_contract

       def compute(self, price: float, quantity: float) -> float:  # noqa: ARG002
           return abs(quantity) * self._usd_per_contract
   ```
2. Export it from `core/domain/trading/__init__.py` alongside `PercentageCommissionModel`.
3. Append two test functions to the existing
   `tests/core_test/unit/domain/trading/test_commission_model.py`:
   - `test_per_contract_ignores_price`
   - `test_per_contract_scales_with_quantity` — `compute(4500.0, 2) == 2 * fee`

**Success criteria.** The new model satisfies the existing Protocol.

**Verify.**
`uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q` exits 0 with a
final line containing `passed` and not containing `failed`.

### Task 6.4 — Thread the contract multiplier through positions and the paper broker

**Goal.** ES PnL is `(exit - entry) x 50 x contracts`, while crypto stays at `x 1`.

**Target files and symbols.**
- `core/domain/position/entities.py` -> `PositionAggregate` fields (lines 28-45),
  `PositionAggregate.open` (line 47), `_calculate_pnl_per_unit` (line 217),
  `unrealized_pnl` (line 224), `market_value` (line 235), `cost_basis` (line 239),
  `to_mongo` (line 246), `from_mongo` (line 265).
- `core/infra/brokers/paper/paper_broker_adapter.py` -> `__init__` (lines 108-142),
  `_commission` (line 484), the affordability check at line 499, and the
  `PositionAggregate.open(...)` construction (search for `PositionAggregate.open`).
- `core/domain/risk/services/position_calculator_domain_service.py` -> `calculate` (line 18).
- `tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py` (existing, 10 tests).
- New test file `tests/core_test/infra/brokers/test_paper_broker_contract_spec.py`.

**Steps.**
1. Add one field to `PositionAggregate`, after `entry_commission`:
   ```python
   # Account-currency value of one price point. 1.0 for crypto and equities; 50.0 for
   # ES, 20.0 for NQ, 5.0 for YM. Placed on the aggregate because both realized
   # (reduce_quantity) and unrealized PnL route through _calculate_pnl_per_unit.
   multiplier: float = 1.0
   ```
2. Multiply by it in exactly three places:
   - `_calculate_pnl_per_unit` (line 217) -> multiply the returned difference by
     `self.multiplier`.
   - `market_value` (line 235) -> `self.quantity * self.current_price * self.multiplier`.
   - `cost_basis` (line 239) -> `self.quantity * self.entry_price * self.multiplier`.
   Do NOT touch `add_quantity`'s average-price arithmetic (lines 110-112): average entry price
   is a price, not a currency amount.
3. Add `multiplier: float = 1.0` as a keyword parameter to `PositionAggregate.open` and pass it
   through; serialize it in `to_mongo` and read it in `from_mongo` with a default of `1.0` so
   existing documents load unchanged.
4. In `PaperBrokerAdapter.__init__`, add `contract_spec: ContractSpec = LINEAR_SPEC` as the last
   keyword parameter and store it. Pass `multiplier=self._contract_spec.multiplier` at every
   `PositionAggregate.open(...)` call site inside the adapter.
5. In the affordability check at line 499
   (`return fill_price * order.quantity + commission <= self._balance`), multiply the notional
   by `self._contract_spec.multiplier`. Add the comment:
   `# Notional is points x multiplier x contracts. Margin accounting itself (1x leverage, only close/reduce touch the balance, plan 260628-2013) is unchanged.`
6. In `PositionCalculatorDomainService.calculate`, add
   `contract_spec: ContractSpec | None = None` as the last keyword parameter. When present:
   divide the computed `size` by `contract_spec.multiplier` before capping, and round the final
   size down to `contract_spec.lot_step` with
   `size = math.floor(size / lot_step) * lot_step` when `lot_step` is not None. Compute
   `notional = size * entry_price * multiplier`. Leave the crypto path (spec `None`)
   byte-identical.
7. Create `tests/core_test/infra/brokers/test_paper_broker_contract_spec.py` with exactly four
   test functions:
   - `test_es_round_trip_pnl_is_twenty_five_dollars` — the worked example from the advice:
     2 contracts, entry `4500.00`, exit `4500.25`, `multiplier=50` gives realized PnL
     `25.00`, before commission
   - `test_crypto_pnl_unchanged_with_default_spec`
   - `test_position_sizing_rounds_to_integer_contracts` — `lot_step=1.0` yields a whole number
   - `test_position_roundtrips_multiplier_through_mongo`

**Success criteria.** The ES worked example yields exactly `25.00`; the ten existing
futures-accounting tests still pass unchanged.

**Verify.**
`uv run pytest tests/core_test/infra/brokers/ tests/core_test/unit/domain/position/ -q` exits 0
with a final line containing `passed` and not containing `failed`, AND
`uv run pytest tests/core_test/infra/brokers/test_paper_broker_contract_spec.py -q` prints
`4 passed`.

### Task 6.5 — Thread the contract spec through the backtest configuration

**Goal.** A 1h ES backtest reports dollar PnL and a session-based Sharpe.

**Target files and symbols.**
- `core/domain/backtest/config.py` -> `BacktestConfig` (lines 26-36).
- `engine/backtest/backtest_dispatch.py` -> `_config_from_dict` (lines 42-54) and the
  `sandbox.create_broker(...)` call (lines 92-96).
- `engine/backtest/backtest_sandbox_app_service.py` -> `create_broker` (lines 112-131).
- `engine/backtest/backtest_report_app_service.py` -> the `config_snapshot` dict (line 392
  onwards).
- New test file `tests/backtest_test/engine/test_backtest_contract_spec.py`.

**Steps.**
1. Add to `BacktestConfig`, after `commission_bps`:
   ```python
   # Unit conversion for this instrument. Defaults to LINEAR_SPEC so every existing
   # crypto run is byte-identical.
   contract_spec: ContractSpec = field(default_factory=lambda: LINEAR_SPEC)
   ```
   and document it in the class docstring's attribute list.
2. In `_config_from_dict`, read it from the payload:
   `contract_spec=ContractSpec(**payload["contract_spec"]) if payload.get("contract_spec") else LINEAR_SPEC`.
3. In `run_single`, before building the sandbox, look up the spec for the configured symbol:
   ```python
   if config.contract_spec == LINEAR_SPEC:
       # Route-supplied spec wins; otherwise fall back to the per-symbol table so a
       # backtest launched from the UI gets ES maths without the caller knowing.
       config.contract_spec = CONTRACT_SPECS.get(config.symbol, LINEAR_SPEC)
   ```
4. Add `contract_spec: ContractSpec = LINEAR_SPEC` to
   `BacktestSandboxAppService.create_broker` and forward it to `PaperBrokerAdapter`. When
   `contract_spec.commission_kind == "per_contract"`, build a
   `PerContractCommissionModel(usd_per_contract=config.commission_bps)` instead of
   `PercentageCommissionModel(bps=commission_bps)`. Add the comment:
   `# commission_bps carries dollars-per-contract when the spec says per_contract. One field, two units, chosen by the spec - no second API surface and no plan-tier branch.`
5. Add `"contract_spec": asdict(self._config.contract_spec),` to the `config_snapshot` dict in
   `backtest_report_app_service.py` so a stored run records the maths it used.
6. Create `tests/backtest_test/engine/test_backtest_contract_spec.py` with exactly three test
   functions:
   - `test_default_config_is_linear`
   - `test_es_symbol_picks_up_the_es_spec`
   - `test_per_contract_commission_selected_for_futures`

**Success criteria.** A crypto backtest is unchanged; an ES backtest uses the ES multiplier and
per-contract commission.

**Verify.**
`uv run pytest tests/backtest_test/ -q` exits 0 with a final line containing `passed` and not
containing `failed`, AND
`uv run pytest tests/backtest_test/engine/test_backtest_contract_spec.py -q` prints `3 passed`.

### Task 6.6 — Confirm G2 and G3 on real data

**Goal.** The two trading goals are demonstrated, not assumed.

**Target files and symbols.**
- `plans/260921-1436-asset-class-index-futures/reports/phase-06-g2-g3.md` (new).

**Steps.**
1. **G2.** Run a paper strategy on `ES1!:CME_MINI` for a full CME session. Execute one round
   trip of 2 contracts. Record entry price, exit price, realized PnL, commission, and the
   equity curve around the fill.
2. **G3.** Run a 1h backtest on `ES1!:CME_MINI` over the available window. Record the reported
   Sharpe, the `periods_per_year` in the stored `config_snapshot`, and total dollar PnL.
3. Write both results into `plans/.../reports/phase-06-g2-g3.md`.

**Success criteria.** G2: realized PnL equals `(exit - entry) x 50 x 2` minus per-contract
commission, and the equity curve shows no jump at fill time other than the commission. G3: the
run reports `periods_per_year = 5796` for 1h (252 sessions x 23 hours) rather than 8,760, and
dollar PnL equals `points x 50 x contracts`.

**Verify.**
`test -f plans/260921-1436-asset-class-index-futures/reports/phase-06-g2-g3.md` exits 0, AND
the file contains the literal string `periods_per_year = 5796`, AND the recorded G2 realized
PnL equals the hand-computed `(exit - entry) * 50 * 2` minus commission to the cent.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Adding `multiplier` to `PositionAggregate` changes crypto PnL | Medium | High | Default is `1.0`; the 10 existing futures-accounting tests run unchanged in Task 6.4's Verify |
| `market_value` and `cost_basis` are consumed somewhere that assumed raw notional | Medium | Medium | Grep both properties before editing and list every consumer; both are already notional-shaped, so the multiplier is the correct fix everywhere |
| Overloading `commission_bps` as dollars-per-contract confuses a caller | Medium | Medium | The spec's `commission_kind` selects the unit and is recorded in the stored `config_snapshot`; the alternative is a second field on every DTO |
| The polling quote adapter's cadence makes fills fictional on sub-15m bars | High while data is delayed | Medium | Documented trade-off; the UI badge in Phase 7 surfaces `tradingview_delayed_data` |
| Old position documents lack `multiplier` and load as `None` | Low | High | `from_mongo` defaults to `1.0`; Task 6.4 asserts the round trip |

## Rollback

Task 6.4 is the only task that changes stored document shape, and it adds one defaulted field,
so a revert leaves existing documents readable. Reverting Tasks 6.1 and 6.2 removes the
TradingView quote registration; futures charts then show only closed bars from the cron, which
is degraded but correct. Tasks 6.3 and 6.5 are additive and revert cleanly.

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
title: "UI, docs and success-metric run-through"
status: pending
priority: P2
effort: "1d"
dependencies: [6]
---

## Context

The backend is complete; the SPA still speaks Binance. Verified placeholder and default sites:
`web/src/components/strategy/add-symbol-dialog.tsx:23,24,72`,
`web/src/components/backtest/backtest-form.tsx:44,72`,
`web/src/routes/__root.tsx:17`, `web/src/routes/index.tsx:21`. The exchange badge already works
generically: `web/src/lib/symbol-format.ts` splits on the first `:` with no character
restriction, and neither dialog applies a character regex (both only check `includes(':')`), so
`ES1!:CME_MINI` needs no frontend validation change.

Freshness display: `web/src/lib/datetime.ts:88-97` (`ageColorClass`) measures
`Date.now() - lastBarAt`, so a futures symbol reads stale all weekend. The
`is_market_open` field added to the sync-status DTO in Phase 3 Task 3.5 is the fix;
`web/src/types/market-data.ts:88` declares `is_stuck` and is where the new field belongs.
Consumers are `web/src/components/monitor/data-health-row.tsx:50,55,72` and
`web/src/components/monitor/format-helpers.ts:19`.

## Tasks

### Task 7.1 — Make the SPA placeholders and defaults provider-neutral

**Goal.** No user-facing string implies Binance is the only venue.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx` -> the error strings at lines 23 and 24
  and the `placeholder` at line 72.
- `web/src/components/backtest/backtest-form.tsx` -> the `useState` default at line 44 and the
  error string at line 72.
- `web/src/components/chart/trading-chart.tsx:38`, `web/src/components/ticker-widget/ticker-widget.tsx:6`,
  `web/src/components/controls/symbol-selector.tsx:6`, `web/src/types/quote.ts:3`,
  `web/src/types/market-data.ts:20`, `web/src/lib/symbol-format.ts:2` -> doc comments only.

**Steps.**
1. In `add-symbol-dialog.tsx`, change the three strings so the example is generic:
   `'Symbol is required (e.g. BTCUSDT:BINANCE or ES1!:CME_MINI)'`,
   `'Use composite format: CODE:EXCHANGE (e.g. BTCUSDT:BINANCE or ES1!:CME_MINI)'`, and
   `placeholder="e.g. BTCUSDT:BINANCE"` becomes `placeholder="e.g. BTCUSDT:BINANCE, ES1!:CME_MINI"`.
2. In `backtest-form.tsx` line 72, change the error string the same way. Leave the `useState`
   default at line 44 as `'BTCUSDT:BINANCE'` — it is a working default, not a claim about
   supported venues.
3. Leave `web/src/routes/__root.tsx:17` and `web/src/routes/index.tsx:21` unchanged for the
   same reason: they are the landing symbol, not a restriction.
4. In the six doc-comment sites listed above, change
   `"{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE"` to
   `"{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" or "ES1!:CME_MINI"`.
5. Confirm all three futures symbols appear in the symbol selector: it is fed by
   `web/src/api/market-data-api.ts:42` (`Fetch all active symbols as composite strings`), which
   reads from the backend, so the Phase 5 Task 5.7 seed is sufficient. Verify visually.

**Success criteria.** A user can select `ES1!:CME_MINI` in the chart, strategy and backtest
dialogs, and the exchange badge renders `CME_MINI`.

**Verify.**
`cd web && npm run build` exits 0, AND
`grep -rn "ES1!:CME_MINI" web/src | wc -l` prints a number greater than or equal to `6`.

### Task 7.2 — Show "closed" instead of "stuck"

**Goal.** A shut venue reads as closed in the data-health view.

**Target files and symbols.**
- `web/src/types/market-data.ts` -> the sync-status type at line 88.
- `web/src/lib/datetime.ts` -> `ageColorClass` (lines 88-97).
- `web/src/components/monitor/data-health-row.tsx` -> lines 50, 55, 72.
- `web/src/components/monitor/format-helpers.ts` -> line 19.

**Steps.**
1. In `web/src/types/market-data.ts`, add `is_market_open?: boolean` next to `is_stuck?: boolean`
   at line 88.
2. In `datetime.ts`, add a third parameter:
   `export function ageColorClass(lastBarAt: string | null, interval: string, isMarketOpen = true): string`
   and return `'age-neutral'` immediately when `isMarketOpen === false`. Add the comment:
   `// A closed venue is not stale. The backend computes is_market_open from the symbol's trading calendar; the browser must not re-derive it.`
3. In `data-health-row.tsx`, pass `s.is_market_open ?? true` to `ageColorClass`, and at line 50
   and line 55 render the label `'closed'` (and a neutral badge) when
   `s.is_market_open === false`, taking precedence over the stuck branch. At line 72, render
   `<StuckBadge show={!!s.is_stuck && s.is_market_open !== false} />`.
4. In `format-helpers.ts` line 19, return `'neutral'` when `s.is_market_open === false`, before
   the `is_stuck` check.

**Success criteria.** Over a weekend, the three futures rows show a neutral "closed" state and
no stuck badge; crypto rows are unaffected.

**Verify.**
`cd web && npm run build` exits 0, AND
`grep -c "is_market_open" web/src/components/monitor/data-health-row.tsx` prints a number
greater than or equal to `2`.

### Task 7.3 — Surface provider status on `/health`

**Goal.** "Why are there no ES bars" is a glance, not a log hunt.

**Target files and symbols.**
- `app/main_extensions.py` -> `register_health_checks` (line 267) and the `health_check` route
  (line 366).
- `core/infra/market_data/routing_data_provider_adapter.py` -> new
  `RoutingDataProviderAdapter.status()`.

**Steps.**
1. Add to `RoutingDataProviderAdapter`:
   ```python
   def status(self) -> dict[str, dict[str, object]]:
       """Per-provider health for the /health endpoint.

       Reports id, authenticated (when the provider exposes it) and the UTC ISO time
       of its last successful fetch. Ten lines that turn a log hunt into a glance.
       """
   ```
   Track `self._last_success: dict[str, datetime]` inside `fetch_ohlcv`, and read
   `is_authenticated()` reflectively (`getattr(provider, "is_authenticated", None)`) so
   `BinanceAdapter`, which has no such method, reports `None` rather than raising.
   Serialize timestamps with `to_utc_iso`.
2. Register a health check named `market_data_providers` in `register_health_checks` that calls
   `status()`. Follow the shape of the existing registrations in that function — read it before
   editing.
3. Do not include any credential, username or token in the payload.

**Success criteria.** `GET /health` includes a `market_data_providers` section listing both
provider ids with a last-success timestamp and, for TradingView, an authentication flag.

**Verify.**
With the app running, `curl -s http://localhost:41921/health | grep -c "market_data_providers"`
prints `1`, AND
`curl -s http://localhost:41921/health | grep -ci "password\|token\|username"` prints `0`.

### Task 7.4 — Update the documentation

**Goal.** The evergreen docs describe the new architecture accurately.

**Target files and symbols.**
- `docs/system-architecture.md` -> "Where Does X Live?" table (line 479 onwards),
  "Dependency Injection (Dishka)" (line 670), "Configuration" (line 773), "Dependencies"
  (line 777), "Ops Context" external services (line 790 onwards).
- `README.md` -> the environment-variable section.
- `docs/code-standards.md` -> no change expected; verify the naming table (line 358) already
  covers `*_port.py` and `*_adapter.py`, which it does.

**Steps.**
1. In the "Where Does X Live?" table, add four rows:
   - `| Trading-calendar port | core/domain/market_data/trading_calendar_port.py |`
   - `| Calendar implementations (24/7, CME Globex) | core/infra/calendars/ |`
   - `| Provider routing adapters | core/infra/market_data/ |`
   - `| TradingView client, mappers, adapters | core/infra/tradingview/ |`
2. In the "Dependency Injection (Dishka)" section, update the `InfrastructureProvider` and
   `MarketDataProvider` descriptions to say they bind the ROUTING adapters and register concrete
   providers in a dict, and add `TradingCalendarResolverAppService` and
   `ProviderResolverAppService` to the `MarketDataProvider` list.
3. In "Configuration", add `MARKET_DATA_PROVIDERS`, `SYMBOL_PROVIDER_OVERRIDES`, `TZ`, and the
   six `TRADINGVIEW_*` names. Values stay in `../pocketquant-config`.
4. In "Dependencies", add `pandas_market_calendars` (CME session rules), `tzdata` (explicit tz
   database) and `tvdatafeed` (unofficial TradingView scraper, isolated behind
   `ITradingViewClientPort`).
5. In "Ops Context" -> "External Services", add `TradingView (unofficial scraper, REST-style history + polled quotes)`.
6. In "Known Limitations", add three bullets: futures 1m history is capped by the TradingView
   plan and accumulates forward; futures quotes are polled, not streamed, so `tick_count` is 1
   per poll; `ES1!`-style continuous contracts splice unadjusted at expiry, so a position held
   across a roll shows a one-time basis jump.
7. In `README.md`, confirm the settings list from Phase 4 Task 4.1 and Phase 5 Task 5.1 is
   present and consistent.

**Success criteria.** Every new module and setting is discoverable from the docs, and no
credential value appears anywhere.

**Verify.**
`grep -c "core/infra/calendars\|core/infra/tradingview\|core/infra/market_data" docs/system-architecture.md`
prints a number greater than or equal to `3`, AND
`grep -c "MARKET_DATA_PROVIDERS" docs/system-architecture.md README.md` prints a nonzero count
for both files.

### Task 7.5 — Run the success metrics and record them

**Goal.** Every goal is evidenced with a recorded number, not an assertion.

**Target files and symbols.**
- `plans/260921-1436-asset-class-index-futures/reports/completion-metrics.md` (new).

**Steps.**
Run each of the following on the VPS during a live CME session and record the observed value.
1. **G6 startup.** `TZ=Asia/Saigon uv run uvicorn pocketquant.app.main:app` exits non-zero with
   the timezone assertion; `TZ=UTC` starts.
2. **Cron parity.** Every cron job reports the same `next_run_time` under all three zones;
   `sync_backfill` fires at 03:00 UTC.
3. **Binance weekly.** On a Thursday-to-Sunday run, the latest `1w` bar for
   `BTCUSDT:BINANCE` has `datetime` equal to the previous Monday 00:00 UTC.
4. **Futures quiet.** Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
   `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across one week
   including a weekend and, if one falls in the window, an early-close holiday.
5. **Session daily bars.** ES 1d bars open at 17:00 CT and close at 16:00 CT with
   `session_date` populated, on both sides of a DST transition, matching the TradingView chart.
6. **Golden file.** `tests/engine_test/market_data/test_crypto_golden_baseline.py` passes
   unchanged.
7. **Lint and suite.** `uv run ruff check src tests` and `uv run pytest tests/ -q` both pass,
   with the crypto test count equal or higher than before the plan started.
8. **DST suite.** All eight `CmeGlobexEquityCalendarAdapter` scenarios pass, including
   `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
   `session_open(2026-11-02) == 2026-11-01T23:00:00Z`.
9. **G1 freshness.** As in Phase 5 Task 5.8 verification (a).
10. **Closed-session quiet.** Over one weekend, `job_history` shows `sync_1m` runs for the three
    futures symbols with `status="skipped_closed"` and zero `no_progress` entries.
11. **Cascade alignment.** `sync_verify_cascade` on `ES1!:CME_MINI` reports
    `divergent_fraction = 0.0` for 24 consecutive runs, and the 4h bars' `datetime` values are
    session-open anchored (22:00 or 23:00 UTC), never 00:00 or 04:00 UTC.
12. **Backfill depth.** The `bars` count for `ES1!:CME_MINI` at 1m equals
    `min(TRADINGVIEW_MAX_BARS, available)` immediately after backfill and grows by roughly
    1,380 per trading day.
13. **G2 and G3.** Copy the results from Phase 6 Task 6.6.
14. **G4.** `tests/engine_test/market_data/test_g4_config_only_provider.py` passes, and
    `git diff --stat` for that test touches no file under `engine/` or `app/`.
15. **G5.** `sync_1m` for BTC/ETH/SOL produces the same `synced_count` and bar values as before
    the change over one full cron cycle; `periods_per_year` for crypto is still 525,600 at 1m.
16. **Secrets.** `git grep -i "tradingview_.*=" -- ':!*.md'` finds only field declarations.

Write all sixteen observations, with the actual numbers, into
`plans/260921-1436-asset-class-index-futures/reports/completion-metrics.md`.

**Success criteria.** All sixteen metrics are recorded with a concrete observed value and each
meets its stated target.

**Verify.**
`test -f plans/260921-1436-asset-class-index-futures/reports/completion-metrics.md` exits 0, AND
`grep -c "^| *[0-9]" plans/260921-1436-asset-class-index-futures/reports/completion-metrics.md`
prints `16` (one table row per metric), AND
`grep -ci "TODO\|TBD\|not measured" plans/260921-1436-asset-class-index-futures/reports/completion-metrics.md`
prints `0`.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The `!` in a composite symbol breaks a URL path segment in the SPA | Medium | Medium | `web/src/lib/symbol-format.ts` `encodeSymbolForUrl` already wraps `encodeURIComponent`; confirm every route uses it during Task 7.1's visual check |
| `/health` accidentally exposes a credential | Low | High | Task 7.3's Verify greps the response for `password`, `token` and `username` and requires zero hits |
| A success metric cannot be run because no CME session falls in the window | Medium | Low | Metrics 4, 5, 9, 10 and 11 need a live session and a weekend; schedule the run-through across one full week |
| Docs drift from the code again | Medium | Low | Task 7.4 verifies with `grep` against the actual module paths |

## Rollback

Every change in this phase is presentational, documentary or additive-observability. Reverting
any task leaves the backend fully functional; the only loss is that the UI shows "stuck"
instead of "closed" over a weekend and `/health` omits the provider section.

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
