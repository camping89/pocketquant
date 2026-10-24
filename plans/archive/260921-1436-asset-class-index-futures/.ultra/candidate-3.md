=== FILE: plan.md ===
---
title: "Asset-class model + index futures (ES/NQ/YM) via provider routing"
description: "Make UTC a checked invariant, model asset class + trading calendar as data, route providers by asset class, and deliver ES1!/NQ1!/YM1! through the existing pipeline."
status: pending
priority: P1
effort: 13d
branch: develop
tags: [market-data, futures, timezone, providers, calendar, tradingview]
created: 2026-09-21
blockedBy: []
blocks: []
---

# Asset-class model + index futures (ES/NQ/YM) via provider routing

## Overview

PocketQuant is hardwired to one 24/7 crypto venue: DI binds exactly one `IDataProviderPort`
and one `IRealtimeQuoteProviderPort`, and sync, cascade, integrity, freshness, annualization
and paper-broker math all assume continuous trading and price x quantity units. This plan adds
CME/CBOT continuous front-month index futures (`ES1!:CME_MINI`, `NQ1!:CME_MINI`,
`YM1!:CBOT_MINI`) sourced from TradingView, by generalizing the existing pipeline rather than
building a second one: an `AssetClass` enum plus a persisted `calendar_id` drives session,
annualization and contract math, and provider resolution is keyed by asset class and provider id.

Phase numbering: the confirmed advice in
`plans/reports/advise-260921-2001-index-futures-data-provider.md` numbers its route 0-6.
This plan maps advice Phase 0 to plan Phase 1, advice Phase 1 to plan Phase 2, and so on
through advice Phase 6 to plan Phase 7. Read the advice report and the datetime audit at
`plans/reports/kongming-260921-2106-datetime-timezone-audit.md` before starting Phase 1.

Two naming deviations from the advice, applied for `docs/code-standards.md` compliance and
recorded once here: the routing providers are `RoutingDataProviderAdapter` and
`RoutingQuoteProviderAdapter` (the `Adapter` suffix is mandatory for infra implementations),
and `tradingview_poll_seconds` defaults to 60 rather than 10 because the advice also forbids
polling faster than delayed CME data can change.

## Goals

| # | Goal | Priority |
|---|------|----------|
| G1 | Fresh futures bars land within one cron cycle during session hours | P1 |
| G2 | A paper ES strategy runs a full session with correct USD PnL | P1 |
| G3 | A 1h ES backtest reports dollar PnL and Sharpe consistent with the contract spec | P1 |
| G4 | Adding a provider is one adapter plus one config entry, zero caller edits | P1 |
| G5 | BTC/ETH/SOL behaviour and tests are unchanged | P1 |
| G6 | The app refuses to start on a non-UTC host and the DST-boundary suite passes | P1 |

## Phases

| # | Phase | Depends on | Effort | Status |
|---|-------|-----------|--------|--------|
| 1 | [UTC invariant and the two live crypto bugs](./phase-01-utc-invariant-and-crypto-bugfixes.md) | — | 2d | Pending |
| 2 | [Trading calendar port and asset-class domain model](./phase-02-calendar-port-and-asset-class-model.md) | 1 | 2d | Pending |
| 3 | [Thread the calendar through the pipeline on crypto only](./phase-03-calendar-threading-crypto-parity.md) | 2 | 3d | Pending |
| 4 | [Provider routing layer with Binance-only registration](./phase-04-provider-routing-layer.md) | 3 | 1d | Pending |
| 5 | [TradingView history adapter, credentials and futures seed](./phase-05-tradingview-history-and-futures-seed.md) | 4 | 2d | Pending |
| 6 | [Polling quotes, contract-aware broker and backtest](./phase-06-realtime-quotes-and-contract-math.md) | 5 | 2d | Pending |
| 7 | [UI, documentation and success-metric run-through](./phase-07-ui-docs-and-success-metrics.md) | 6 | 1d | Pending |

Phases are strictly sequential: each one is provable on the crypto path before the next adds
surface. Do not start a phase until the previous phase's final gate task has passed.

## Success Criteria

- [ ] `TZ=Asia/Saigon` startup fails with a timezone `RuntimeError`; `TZ=UTC` starts (G6).
- [ ] Every registered cron job reports an identical `next_run_time` under `TZ=UTC`,
      `TZ=Asia/Saigon` and `TZ=America/Chicago`.
- [ ] `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
      `session_open(2026-11-02) == 2026-11-01T23:00:00Z` for the CME calendar.
- [ ] Golden-file test proves crypto bars, cascade output and performance metrics are
      byte-identical before and after the calendar refactor (G5).
- [ ] A mock third provider registered through config alone receives fetches for an
      overridden symbol, and that test's diff touches no file under `engine/` or `app/` (G4).
- [ ] `ES1!:CME_MINI` accumulates 1m bars during a session and emits zero
      `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
      `stuck_threshold_crossed` or `partial_aggregate` events across one full week (G1).
- [ ] A 2-contract ES round trip from 4500.00 to 4500.25 records realized PnL of 25.00 USD
      minus per-contract commission (G2).
- [ ] A 1h ES backtest annualizes on the CME calendar, not on 8760 (G3).
- [ ] `uv run ruff check src tests` passes with `DTZ` enabled, `uv run lint-imports` reports
      8 kept / 0 broken, and `uv run pytest tests/ -q` passes with no added skips.

=== FILE: phase-01-utc-invariant-and-crypto-bugfixes.md ===
---
phase: 1
title: "UTC invariant and the two live crypto bugs"
status: pending
priority: P1
effort: "2d"
dependencies: []
---

# Phase 1: UTC invariant and the two live crypto bugs

Advice Phase 0. This phase changes no futures behaviour. It makes UTC a checked invariant at
four layers (code, container, boot, lint/CI) and fixes two bugs that are wrong for crypto
today. Everything later depends on the guarantee established here: the TradingView scraper
stamps bars with naive *host-local* time, so a non-UTC host would silently corrupt futures
bars.

Read first: `plans/reports/kongming-260921-2106-datetime-timezone-audit.md` sections P0-1,
P1-2, P1-3, P1-4, P2-1, P2-2 and "UTC enforcement mechanism".

## Task 1.1 — Pin `TZ=UTC` in the container and the local dev runner

**Goal.** Every process that runs this application reports UTC as its local timezone.

**Target files and symbols.**
- `deploy/Dockerfile`, runtime stage `ENV` block at lines 44-47.
- `deploy/compose.prod.yml`, the `app:` service, immediately after its `env_file:` block.
- `justfile`, the `be` recipe.
- Do NOT edit `deploy/compose.local.yml`: it defines only `mongodb` and `redis` services and
  has no app service to pin.

**Steps.**
1. In `deploy/Dockerfile`, add `TZ=UTC` to the runtime stage `ENV` list so it reads
   `ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC`.
2. In `deploy/compose.prod.yml` under `app:`, add an `environment:` block with the single
   entry `TZ=UTC`, placed after `env_file:`. Add a one-line comment explaining that this is
   explicit so a missing key in `.env` cannot unpin it.
3. In `justfile`, replace the single `be:` recipe with two attributed variants so the pin
   works on both shells (`just 1.55.1` is installed and supports these attributes):
   ```
   [unix]
   be:
       TZ=UTC {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41921

   [windows]
   be:
       $env:TZ="UTC"; {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41921
   ```
   Keep the existing comment block above the recipes unchanged.

**Success criteria.** `just --list` still lists `be`; the Dockerfile and compose file both
contain a literal `TZ=UTC`.

**Verify.** `just --list` exits 0 and its output contains `be`, AND
`grep -c 'TZ=UTC' deploy/Dockerfile deploy/compose.prod.yml justfile` prints
`deploy/Dockerfile:1`, `deploy/compose.prod.yml:1` and `justfile:2`.

## Task 1.2 — Give both `CronTrigger` constructors an explicit UTC timezone

**Goal.** Cron jobs fire at the documented UTC time regardless of the host timezone.

**Target files and symbols.**
- `src/pocketquant/core/infra/scheduling/scheduler.py`, `JobScheduler.add_cron_job`, the two
  `CronTrigger(...)` constructions at lines 219-233.
- New test file `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.

**Steps.**
1. Add `from datetime import UTC` to the imports of `scheduler.py` if not already present.
2. Pass `timezone=UTC` as an additional keyword argument to BOTH `CronTrigger(...)` calls
   (the `cron_expression` branch and the `hour/minute/second/day_of_week` branch).
3. Add a comment above the first one: APScheduler applies the scheduler's timezone only when
   `add_job` builds the trigger from a string alias; a pre-built trigger otherwise falls back
   to `tzlocal.get_localzone()` and pickles the host zone into the Mongo jobstore.
4. Write `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py` with exactly 2
   tests that construct a `CronTrigger` through the same argument shapes used at lines
   219-233 and assert `str(trigger.timezone) == "UTC"` for both the cron-expression branch
   and the hour/minute branch. Do not start a scheduler or touch Mongo.

**Success criteria.** Both triggers carry UTC; the new tests pass.

**Verify.** `uv run pytest tests/core_test/infra/scheduling/test_cron_trigger_timezone.py -q`
exits 0 and prints `2 passed`.

## Task 1.3 — Fail fast at startup on a non-UTC process timezone

**Goal.** The application refuses to start on a host whose local timezone is not UTC.

**Target files and symbols.**
- `src/pocketquant/core/common/time/__init__.py`: new function `assert_utc_process()`.
- `src/pocketquant/app/main_extensions.py`: new function `assert_utc_runtime(container)`.
- `src/pocketquant/app/main.py`, inside `lifespan`, called before `start_background_jobs`.
- `pyproject.toml` `[project] dependencies`.

**Steps.**
1. Add `"tzlocal>=5.3"` to `[project] dependencies` in `pyproject.toml`. It is already
   installed as an APScheduler transitive dependency (5.3.1); this makes the direct use
   explicit. Run `uv sync` afterwards.
2. In `src/pocketquant/core/common/time/__init__.py` add:
   ```python
   def assert_utc_process() -> None:
       """Raise RuntimeError unless the process local timezone is UTC."""
   ```
   The body must check `time.timezone == 0 and not time.daylight` and
   `tzlocal.get_localzone_name() in {"UTC", "Etc/UTC"}` (APScheduler consults tzlocal, so both
   checks are needed), and raise `RuntimeError` naming the observed `time.tzname` and tzlocal
   name when either fails. Export it from `__all__`.
3. In `src/pocketquant/app/main_extensions.py` add
   `async def assert_utc_runtime(container: AsyncContainer) -> None:` which calls
   `assert_utc_process()`, then logs exactly one INFO event `runtime.timezone` with the
   `TZ` environment value, `time.tzname` and the tzlocal name. Log level INFO is correct here
   because this is a one-shot startup lifecycle event.
4. In `src/pocketquant/app/main.py`, import `assert_utc_runtime` and call
   `await assert_utc_runtime(container)` inside the `try:` block immediately BEFORE
   `await start_background_jobs(container)`.
5. In `main_extensions.start_background_jobs`, after `await register_sync_jobs(...)` returns,
   iterate the scheduler's jobs and raise `RuntimeError` if any `job.trigger` exposes a
   `timezone` attribute whose `str(...)` is not `"UTC"`.

**Success criteria.** The assertion exists, is called before jobs start, and raises on a
non-UTC process.

**Verify.** `uv run python -c "import os,time; os.environ['TZ']='Asia/Saigon'; time.tzset();
from pocketquant.core.common.time import assert_utc_process; assert_utc_process()"` exits
non-zero and prints `RuntimeError`, AND the same command with `TZ='UTC'` exits 0.

## Task 1.4 — Remove the host-dependent `date.today()`

**Goal.** The backtest fallback date window no longer depends on the host calendar date.

**Target files and symbols.**
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py:37`, inside the date-range
  fallback of the function containing `backtest_jobs.date_range_fallback`.

**Steps.**
1. Replace `today = date.today()` with `today = datetime.now(UTC).date()`.
2. Ensure `UTC` and `datetime` are imported from `datetime` in that module; drop the `date`
   import only if nothing else in the file uses it (the `build_backtest_config` signature
   still annotates `date`, so keep it).

**Success criteria.** `date.today()` no longer appears in `src/`.

**Verify.** `grep -rn "date.today()" src/` exits 1 (no matches).

## Task 1.5 — Make the Mongo client tz-aware and fix the one deliberate naive site (ONE commit)

**Goal.** Every datetime read from Mongo is tz-aware UTC, with no false integrity gaps.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/mongodb.py`, the `AsyncMongoClient(...)`
  construction at lines 44-49.
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py:50`, the `now = ...` line
  inside `check_integrity`.
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py:24`, the naive epoch
  branch inside `get_bar_start`.
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py:54-55`, the comment
  "Mongo client is not tz_aware; raw projection returns naive datetimes."

**Steps.**
1. These four edits MUST land in a single commit. Flipping `tz_aware` alone makes
   `expected - aligned_times` in `integrity_jobs.py:63` report every bar missing, which makes
   `sync_repair` resync 5000 bars for every symbol and interval every 12 hours.
2. In `mongodb.py`, add `tz_aware=True` and `tzinfo=UTC` to the `AsyncMongoClient(...)` call.
   Import `UTC` from `datetime`.
3. In `integrity_jobs.py:50`, change `now = datetime.now(UTC).replace(tzinfo=None)` to
   `now = datetime.now(UTC)`. Delete the `.replace(tzinfo=None)` only; keep the surrounding
   comment about the grid ending at the last closed bar.
4. In `bar_builder_domain_service.py`, replace line 24
   `epoch = datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`
   with the unconditional `epoch = datetime(1970, 1, 1, tzinfo=UTC)`.
5. In `bar_filters.py`, update the comment at lines 54-55 to say the Mongo client is tz-aware
   and `coerce_utc` remains as a defensive no-op. Keep the `coerce_utc` calls.
6. Run the existing normalization test and the integrity and bar-repository tests.

**Success criteria.** The Mongo client is tz-aware, no naive datetime is constructed in
`src/`, and existing Mongo datetime tests still pass.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py
tests/core_test/infra/persistence/test_bar_repository.py -q` exits 0 and its summary line
contains `passed` with `0 failed`. This test needs Docker for testcontainers; if Docker is
unavailable, STOP and follow the Failure Protocol.

## Task 1.6 — Enforce aware UTC datetimes at entity and DTO boundaries

**Goal.** No naive datetime crosses an adapter, API or serialization boundary.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py`: `Bar.datetime` field, and the `.isoformat()`
  call in `Bar.to_dict` at line 104.
- `src/pocketquant/engine/market_data/ohlcv_service.py`: `GetOHLCVQuery` (lines 14-24) and the
  `.isoformat()` at line 66.
- `src/pocketquant/engine/backtest/backtest_command_service.py`: `RunBacktestCommand`
  `start_date`/`end_date` (lines 31-32) and the two `.isoformat()` calls at lines 74-75.
- `src/pocketquant/engine/backtest/backtest_report_app_service.py`, the `.isoformat()` calls at
  lines 396-397.
- `src/pocketquant/engine/market_data/sync_status_service.py`, `_iso_z` at lines 72-73.

**Steps.**
1. In `Bar`, type the field as `datetime: AwareDatetime | None = None` using
   `from pydantic import AwareDatetime`, and attach a `field_validator("datetime", mode="before")`
   that converts an aware non-UTC value with `.astimezone(UTC)` and raises `ValueError` for a
   naive input. `Bar.from_mongo` already routes through `coerce_utc`, so reconstruction is
   unaffected.
2. Replace `Bar.to_dict`'s `self.datetime.isoformat()` with `to_utc_iso(self.datetime)` and
   drop the now-redundant `if ... else None`. Do the same for `updated_at`.
3. `GetOHLCVQuery` is a `@dataclass`, not a Pydantic model. Convert it to a Pydantic
   `BaseModel` with `start_date: datetime | None` / `end_date: datetime | None` and a
   `field_validator(..., mode="before")` that attaches UTC to a naive value (backwards
   compatible: naive input keeps being accepted, it is normalised in one place). Update its
   only construction site, `src/pocketquant/app/routes/market_data_ohlcv.py:47-53`.
4. Add the same UTC-normalising `field_validator` for `start_date`/`end_date` on
   `RunBacktestCommand`.
5. Replace the `.isoformat()` calls named above with `to_utc_iso(...)`
   (`from pocketquant.core.common.time import to_utc_iso`), and replace the body of `_iso_z`
   in `sync_status_service.py` with `return to_utc_iso(dt)`.
6. `docs/code-standards.md:777` already mandates `to_utc_iso()`; no doc change is needed.

**Success criteria.** Constructing `Bar(datetime=<naive>)` raises; every listed serialization
site emits a `Z`-suffixed string.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar tests/app_test/market_data -q`
exits 0 with `0 failed`, AND `grep -rn "\.isoformat()" src/pocketquant/core/domain/bar/entities.py
src/pocketquant/engine/market_data/ohlcv_service.py` exits 1 (no matches).

## Task 1.7 — Fix the partial Binance weekly bar

**Goal.** The latest stored `1w` bar for a crypto symbol is never an in-progress week.

**Target files and symbols.**
- `src/pocketquant/core/infra/binance/binance_adapter.py:80-83`, the `now_ms` /
  `last_closed_open_ms` / `cutoff_dt` block inside `fetch_ohlcv`.
- New test file `tests/core_test/infra/binance/test_binance_weekly_cutoff.py`.

**Steps.**
1. `bar_duration_ms` for `1w` is 604800000, and `floor(now_ms / 604800000)` lands on a
   THURSDAY because the Unix epoch was a Thursday. From Thursday to Sunday the cutoff is later
   than the current Monday-open weekly kline, so that partial kline passes the
   `b.datetime < cutoff_dt` guard at line 108 and is persisted.
2. Replace the cutoff derivation with one that uses the same alignment function the filter
   uses: compute `cutoff_dt = get_bar_start(datetime.now(UTC), interval)` via
   `from pocketquant.core.domain.bar.services.bar_builder_domain_service import get_bar_start`,
   then `end_time_ms = int(cutoff_dt.timestamp() * 1000)`. Keep `now_ms` only if still needed.
3. Add a comment explaining that deriving the cutoff from `get_bar_start` keeps the adapter and
   the alignment filter from ever disagreeing.
4. Write `tests/core_test/infra/binance/test_binance_weekly_cutoff.py` with exactly 3 tests
   that freeze `datetime.now` (monkeypatch the module attribute) to a Thursday, a Saturday and
   a Monday in 2026, call the cutoff derivation, and assert the resulting cutoff equals the
   Monday 00:00 UTC of that same week. Do not perform network I/O; test the pure cutoff
   computation by extracting it into a small module-level helper
   `_last_closed_bar_open(now, interval) -> datetime` if that keeps the test offline.

**Success criteria.** The weekly cutoff is Monday-aligned for every day of the week.

**Verify.** `uv run pytest tests/core_test/infra/binance/test_binance_weekly_cutoff.py -q`
exits 0 and prints `3 passed`.

## Task 1.8 — Enable ruff `DTZ` and clear every finding

**Goal.** Naive datetime construction is a lint error.

**Target files and symbols.**
- `pyproject.toml` `[tool.ruff.lint] select` (currently `["E", "F", "I", "N", "W", "UP", "TID"]`).
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:81`
  (`datetime.min` in the `sorted(...)` key of `aggregate_ohlcv`).
- Test and script files that construct naive datetimes on purpose (verified counts as of this
  plan: `tests/core_test/unit/domain/test_mongo_datetime_normalization.py` 4,
  `tests/backtest_test/engine/test_backtest_app_service_persistence.py` 4,
  `scripts/backfill/test_binance_bars.py` 3, `tests/scripts/rubric/test_reconciliation.py` 2,
  `tests/backtest_test/engine/test_result_collector_mark_to_market.py` 2,
  `tests/backtest_test/engine/test_hitnrun2_backtest.py` 2,
  `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py` 2,
  `tests/backtest_test/engine/test_engulfing_backtest.py` 2,
  `tests/app_test/market_data/test_cascade_aggregator.py` 2, plus one each in
  `tests/scripts/rubric/test_trade_path_analysis.py`,
  `tests/engine_test/test_live_metrics_query_service.py`,
  `tests/core_test/infra/persistence/test_trade_repository.py`,
  `tests/core_test/infra/persistence/backtest/test_trade_repository.py`,
  `tests/core_test/infra/persistence/backtest/test_order_repository.py`,
  `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py`,
  `tests/backtest_test/test_backtest_stats_service.py`,
  `tests/backtest_test/domain/test_trade_stats_calculator.py` — 31 findings in total, 3 of
  them in `src/`).

**Steps.**
1. Add `"DTZ"` to `[tool.ruff.lint] select` in `pyproject.toml`.
2. Run `uv run ruff check --select DTZ --output-format concise src` and fix the remaining
   `src` finding: in `cascade_aggregator.py:81`, change
   `key=lambda b: b.datetime or datetime.min` to
   `key=lambda b: b.datetime or datetime.min.replace(tzinfo=UTC)`. The other two `src`
   findings (`bar_builder_domain_service.py:24`, `backtest_strategy_loader.py:37`) were
   already removed by Tasks 1.5 and 1.4.
3. Run `uv run ruff check --select DTZ --output-format concise tests scripts`. For each hit,
   pass `tz=UTC` where the value is a real instant. Where the naive value is the *subject* of
   the test (`tests/core_test/unit/domain/test_mongo_datetime_normalization.py` asserts that
   naive input is coerced), append `# noqa: DTZ001` with a short trailing reason instead of
   changing the assertion. Never weaken a test to satisfy the linter.

**Success criteria.** Ruff passes on the whole repository with `DTZ` selected.

**Verify.** `uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`.

## Task 1.9 — Prove timezone independence in CI

**Goal.** A regression that reintroduces host-timezone dependence fails CI.

**Target files and symbols.**
- `justfile`: new recipe `test-tz`.
- `.github/workflows/cicd.yml`: the `tests` job, after the existing
  `Run pytest (full suite)` step.
- New test file `tests/core_test/infra/scheduling/test_cron_next_run_time_tz_invariance.py`.

**Steps.**
1. Add a `just` recipe (use the same `[unix]` / `[windows]` attribute pattern as Task 1.1):
   ```
   [unix]
   test-tz:
       TZ=Asia/Saigon {{python}} -m pytest tests/core_test tests/app_test/market_data -q
       TZ=America/Chicago {{python}} -m pytest tests/core_test tests/app_test/market_data -q
   ```
   Provide the PowerShell equivalent for `[windows]`.
2. Write `tests/core_test/infra/scheduling/test_cron_next_run_time_tz_invariance.py` with
   exactly 2 tests. Each constructs the five production trigger shapes from
   `sync_jobs.register_sync_jobs` (`"*/1 * * * *"` with `second=2`, `"0 * * * *"`,
   `hour=3, minute=0`, `hour=4, minute=0`, `"0 */12 * * *"`) through
   `JobScheduler.add_cron_job`'s exact `CronTrigger` argument shapes, and asserts
   `trigger.get_next_fire_time(None, <a fixed aware UTC instant>)` is equal across
   `TZ=UTC`, `TZ=Asia/Saigon` and `TZ=America/Chicago` (set via `monkeypatch.setenv` plus
   `time.tzset()` inside the test, restoring afterwards). Do not start a scheduler.
3. Add a CI step named `Run pytest under non-UTC timezones` that runs
   `TZ=Asia/Saigon uv run pytest tests/core_test tests/app_test/market_data -q` and then the
   same with `TZ=America/Chicago`.

**Success criteria.** Both zone runs pass and the invariance test passes.

**Verify.** `uv run pytest tests/core_test/infra/scheduling/test_cron_next_run_time_tz_invariance.py -q`
exits 0 and prints `2 passed`, AND `just test-tz` exits 0.

## Task 1.10 — Phase 1 gate

**Goal.** The repository is green under every quality gate and the UTC invariant is proven.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four project gates in order and fix any failure before continuing.
2. Deploy nothing yet; the VPS check happens once Phase 1 is merged.

**Success criteria.** All four gates pass.

**Verify.** All of the following exit 0: `uv run ruff check src tests scripts`,
`uv run pyright`, `uv run lint-imports` (prints `Contracts: 8 kept, 0 broken.`), and
`uv run pytest tests/ -q` (summary line shows `0 failed` and at least 669 tests collected,
the pre-phase baseline).

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
title: "Trading calendar port and asset-class domain model"
status: pending
priority: P1
effort: "2d"
dependencies: [1]
---

# Phase 2: Trading calendar port and asset-class domain model

Advice Phase 1. This phase adds the vocabulary but wires nothing into the pipeline yet: an
`AssetClass` enum, a `ContractSpec` value object, an `ITradingCalendarPort` with a 24/7 and a
CME implementation, a registry and a per-symbol resolver, the widened composite regexes, and
the persisted `asset_class` / `calendar_id` / `contract_spec` / `session_date` fields. Nothing
in `engine/` changes behaviour in this phase.

## Task 2.1 — Add the `AssetClass` enum

**Goal.** Asset class is a typed domain concept.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py`: new `class AssetClass(str, Enum)`.

**Steps.**
1. Add `AssetClass(str, Enum)` with exactly three members: `CRYPTO_SPOT = "CRYPTO_SPOT"`,
   `CRYPTO_PERP = "CRYPTO_PERP"`, `INDEX_FUTURE = "INDEX_FUTURE"`.
2. Add a module-level mapping `DEFAULT_CALENDAR_ID: dict[AssetClass, str]` with
   `CRYPTO_SPOT` and `CRYPTO_PERP` mapping to `"CRYPTO_24_7"` and `INDEX_FUTURE` mapping to
   `"CME_GLOBEX_EQUITY"`. A future asset class is one enum member plus one entry here and one
   calendar implementation — no new branching anywhere else.
3. Do not touch `Interval` in this task.

**Success criteria.** The enum imports and has three members.

**Verify.** `uv run python -c "from pocketquant.core.domain.shared.enums import AssetClass;
print(len(AssetClass), AssetClass.INDEX_FUTURE.value)"` exits 0 and prints `3 INDEX_FUTURE`.

## Task 2.2 — Add the `ContractSpec` value object

**Goal.** Contract units are data on the symbol, not hardcoded arithmetic.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/symbol/value_objects.py`: frozen dataclass
  `ContractSpec` and the constant `LINEAR_SPEC`.
- `src/pocketquant/core/domain/symbol/__init__.py`: extend `__all__`.

**Steps.**
1. Define `@dataclass(frozen=True) class ContractSpec` with fields
   `multiplier: float = 1.0`, `tick_size: float | None = None`,
   `lot_step: float | None = None`, `currency: str = "USD"`,
   `commission_per_contract: float | None = None`.
2. Add `to_dict()` and `from_dict(doc: dict) -> ContractSpec` so the spec round-trips through a
   Mongo sub-document.
3. Add `LINEAR_SPEC = ContractSpec()` — multiplier 1, no lot step. This is the crypto default
   and reproduces today's `price x quantity` arithmetic exactly.
4. Export `ContractSpec` and `LINEAR_SPEC` from `core/domain/symbol/__init__.py`.
5. The per-symbol values are ES `multiplier=50.0, tick_size=0.25, lot_step=1.0`,
   NQ `multiplier=20.0, tick_size=0.25, lot_step=1.0`,
   YM `multiplier=5.0, tick_size=1.0, lot_step=1.0`. They are seeded in Phase 5, not here.

**Success criteria.** `ContractSpec().multiplier == 1.0` and `from_dict(to_dict())` round-trips.

**Verify.** `uv run python -c "from pocketquant.core.domain.symbol import ContractSpec;
s=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0);
assert ContractSpec.from_dict(s.to_dict()) == s; print('ok')"` exits 0 and prints `ok`.

## Task 2.3 — Define `ITradingCalendarPort`

**Goal.** Session rules are a single injectable contract.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/trading_calendar_port.py`:
  `class ITradingCalendarPort(ABC)`.
- `src/pocketquant/core/domain/market_data/__init__.py`: add to imports and `__all__`.

**Steps.**
1. Define the abstract class with these members, all abstract unless noted:
   - `calendar_id: str` (property)
   - `tz: ZoneInfo` (property)
   - `is_open(self, instant: datetime) -> bool`
   - `session_open(self, session_date: date) -> datetime` — returns a UTC instant
   - `session_close(self, session_date: date) -> datetime` — returns a UTC instant
   - `session_date_of(self, instant: datetime) -> date`
   - `previous_close(self, instant: datetime) -> datetime`
   - `sessions(self, start: datetime, end: datetime) -> list[date]`
   - `trading_minutes(self, start: datetime, end: datetime) -> list[datetime]`
   - `bar_start(self, instant: datetime, interval: Interval) -> datetime`
   - `expected_source_bars(self, interval: Interval, bucket_start: datetime) -> int`
   - `periods_per_year(self, interval: Interval) -> float`
2. Every method that accepts a `datetime` must assert `instant.tzinfo is not None` and convert
   to UTC on entry via `coerce_utc`; document that all returned datetimes are UTC.
3. `core/domain` must not import `core/infra` (import-linter contract "Core domain stays free
   of infra adapters"), so this file imports only stdlib, `Interval` and `core.common.time`.

**Success criteria.** The port imports and cannot be instantiated.

**Verify.** `uv run lint-imports` exits 0 and prints `Contracts: 8 kept, 0 broken.`

## Task 2.4 — Implement `Continuous24x7Calendar` with proven crypto parity

**Goal.** The 24/7 calendar reproduces today's crypto numbers exactly.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/continuous_24x7_calendar.py`:
  `class Continuous24x7Calendar(ITradingCalendarPort)`.
- New test file `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py`.

**Steps.**
1. Implement every port member:
   - `calendar_id` returns `"CRYPTO_24_7"`; `tz` returns `ZoneInfo("UTC")`.
   - `is_open` always returns `True`; `previous_close(instant)` returns `instant`.
   - `session_open(d)` returns `datetime(d.year, d.month, d.day, tzinfo=UTC)`;
     `session_close(d)` returns `session_open(d) + timedelta(days=1)`;
     `session_date_of(instant)` returns `instant.astimezone(UTC).date()`.
   - `bar_start` must be byte-identical to the current
     `bar_builder_domain_service.get_bar_start`: 1d is `replace(hour=0, minute=0, second=0,
     microsecond=0)`; 1w is that midnight minus `timedelta(days=midnight.weekday())` (Monday
     00:00 UTC); everything else is the epoch floor against
     `datetime(1970, 1, 1, tzinfo=UTC)`. Copy the existing Thursday-epoch comment across.
   - `expected_source_bars` returns `INTERVAL_SECONDS[interval] // 60`, which yields
     5 / 15 / 60 / 240 / 1440 — the exact values in `cascade_aggregator._TF_EXPECTED_BARS`.
   - `trading_minutes(start, end)` returns the dense minute grid `[start + i*60s]`, matching
     today's `integrity_jobs` behaviour.
   - `periods_per_year` returns the values currently in `enums._PERIODS_PER_YEAR`
     (1m 525600, 5m 105120, 15m 35040, 1h 8760, 4h 2190, 1d 365, 1w 365/7).
2. Write the test file with exactly 8 tests:
   (1) `bar_start` matches `get_bar_start` for 50 pseudo-random instants across all 7
   intervals (import the legacy function and compare directly);
   (2) 1w anchors to Monday 00:00 UTC for a Sunday and a Tuesday input;
   (3) `is_open` is True for a Saturday instant;
   (4) `previous_close` is the identity;
   (5) `periods_per_year` equals the 7 legacy values;
   (6) `expected_source_bars` equals 5/15/60/240/1440;
   (7) `trading_minutes` over a 3-hour window has 180 entries;
   (8) every method rejects a naive datetime with `ValueError` or `AssertionError`.

**Success criteria.** The 24/7 calendar is a drop-in for every value the pipeline uses today.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py -q`
exits 0 and prints `8 passed`.

## Task 2.5 — Add `pandas_market_calendars` and implement `CmeGlobexEquityCalendar`

**Goal.** CME session rules, holidays and early closes come from a maintained library.

**Target files and symbols.**
- `pyproject.toml` `[project] dependencies`.
- New package `src/pocketquant/core/infra/calendars/` with `__init__.py` and
  `cme_globex_equity_calendar.py` defining `class CmeGlobexEquityCalendar(ITradingCalendarPort)`.
- `tests/core_test/test_core_layout_contract.py`: add `"pocketquant.core.infra.calendars"` to
  `NEW_MODULES`.

**Steps.**
1. Run `uv add pandas-market-calendars`. `pandas>=2.1.0` is already a dependency, so the only
   new top-level package is this one. It must be imported ONLY from `core/infra/calendars/`;
   `engine` and `backtest` see it through the port.
2. Implement the class by wrapping
   `pandas_market_calendars.get_calendar("CME Globex Equity")`. Verify at implementation time,
   by reading the installed package, that this alias resolves to
   `CMEGlobexEquitiesExchangeCalendar` with `tz = ZoneInfo("America/Chicago")`,
   `market_open = time(17)` offset to the previous day, and `market_close = time(16)`.
3. `calendar_id` returns `"CME_GLOBEX_EQUITY"`; `tz` returns `ZoneInfo("America/Chicago")`.
4. Compute every boundary as exchange-local wall time converted per instant:
   `datetime(y, m, d, 17, tzinfo=ZoneInfo("America/Chicago")).astimezone(UTC)`. NEVER add a
   fixed offset, and never do arithmetic on local wall time across a DST transition.
5. `session_open(d)` / `session_close(d)` must read the library's `schedule()` frame for the
   session labelled `d` so holiday and early-close rules apply automatically. `session_date_of`
   returns the session label (the session opening Sunday 17:00 CT is labelled with the
   following Monday's date).
6. `is_open(instant)` is True when the instant lies in `[session_open, session_close)` of the
   session containing it; the 16:00-17:00 CT maintenance halt is simply the gap between one
   session's close and the next session's open, so it falls out for free.
7. `previous_close(instant)` returns the close of the most recent session that closed at or
   before `instant`. `sessions(start, end)` returns the session labels in the window.
   `trading_minutes(start, end)` returns every minute inside a session in the window.
8. `bar_start(instant, interval)`: for `DAY_1` and `WEEK_1` return the session open (weekly =
   the open of the week's first session); for intraday intervals return
   `session_open + floor((instant - session_open) / interval) * interval`, clipped so a bucket
   never crosses a session boundary.
9. `expected_source_bars(interval, bucket_start)` returns the number of trading minutes inside
   `[bucket_start, bucket_start + interval)`, so an early-close day never trips
   `cascade.partial_aggregate`.
10. `periods_per_year(interval)` derives from the library: sessions per year times trading
    minutes per session divided by the interval's minutes. For `DAY_1` this is the session
    count (about 252), for `WEEK_1` about 52.
11. Cache the schedule frame per calendar year in an instance dict so a per-bar call does not
    rebuild it. Log nothing per call; one INFO `calendar.loaded` at construction is enough.

**Success criteria.** The class imports, is constructible, and `lint-imports` still reports 8
kept contracts.

**Verify.** `uv run python -c "from pocketquant.core.infra.calendars.cme_globex_equity_calendar
import CmeGlobexEquityCalendar; c=CmeGlobexEquityCalendar(); print(c.calendar_id, c.tz)"`
exits 0 and prints `CME_GLOBEX_EQUITY America/Chicago`, AND `uv run lint-imports` exits 0
printing `Contracts: 8 kept, 0 broken.`

## Task 2.6 — Calendar edge-case test suite (DST, holidays, Sunday reopen, UTC midnight)

**Goal.** The session boundaries are correct on the days that break naive implementations.

**Target files and symbols.**
- New test file `tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py` (add an
  `__init__.py` in `tests/core_test/infra/calendars/` to match the sibling packages).

**Steps.**
1. Write exactly 10 tests:
   (1) `session_open(date(2026, 3, 9)) == datetime(2026, 3, 8, 22, 0, tzinfo=UTC)`
       (US spring-forward on 2026-03-08 moves the 17:00 CT open to 22:00 UTC);
   (2) `session_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)`
       (fall-back on 2026-11-01 moves it to 23:00 UTC);
   (3) Sunday reopen: `is_open` is False at Sunday 20:00 UTC in March 2026 and True at
       Sunday 23:00 UTC;
   (4) Friday close: `is_open` is False at Friday 22:30 UTC and `previous_close` for Saturday
       noon UTC equals the Friday 16:00 CT close;
   (5) daily maintenance halt: `is_open` is False at 16:30 CT on a mid-week day;
   (6) a full US holiday (Christmas Day 2026) yields no session label from `sessions(...)`;
   (7) the Juneteenth early close (2026-06-19) has `session_close` at 12:00 CT and
       `expected_source_bars(DAY_1, session_open)` is smaller than a normal session's;
   (8) every session in a normal week spans UTC midnight — assert
       `session_open(d).date() != session_close(d).date()` for five consecutive sessions;
   (9) `bar_start(instant, HOUR_4)` for an instant just after the Sunday open equals the
       session open, not 00:00 or 04:00 UTC;
   (10) `periods_per_year(DAY_1)` is between 240 and 260 and `periods_per_year(HOUR_1)` is
       between 5000 and 6200.
2. Use `zoneinfo.ZoneInfo("America/Chicago")` in the test to construct expectations; do not
   hardcode offsets except in the two assertions that the advice specifies literally.

**Success criteria.** All ten edge cases pass.

**Verify.** `uv run pytest tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py -q`
exits 0 and prints `10 passed`.

## Task 2.7 — Calendar registry, per-symbol resolver and DI wiring

**Goal.** Any pipeline component can obtain the right calendar from a composite symbol.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/calendars/trading_calendar_registry.py`:
  `class TradingCalendarRegistry`.
- New file `src/pocketquant/core/infra/calendars/symbol_calendar_resolver.py`:
  `class SymbolCalendarResolver`.
- `src/pocketquant/core/infra/persistence/repositories/symbol_repository.py`: new method
  `find_by_symbol`.
- `src/pocketquant/app/di/infrastructure.py`: two new `@provide(scope=Scope.APP)` methods.

**Steps.**
1. `TradingCalendarRegistry.__init__` builds
   `{"CRYPTO_24_7": Continuous24x7Calendar(), "CME_GLOBEX_EQUITY": CmeGlobexEquityCalendar()}`
   and exposes `get(calendar_id: str) -> ITradingCalendarPort`, falling back to the 24/7
   calendar with one WARNING when an unknown id is requested.
2. Add `async def find_by_symbol(self, symbol: str) -> Symbol | None` to `SymbolRepository`,
   querying `{"symbol": symbol.upper()}` and returning `Symbol.from_mongo(doc)` or `None`.
3. `SymbolCalendarResolver.__init__(self, symbol_repository, registry)` exposes
   `async def for_symbol(self, symbol: str) -> ITradingCalendarPort`. It looks up the `Symbol`
   record, reads `calendar_id`, and returns the registry entry. When the record is absent it
   returns the 24/7 calendar, so a tracked symbol with no `symbols` document keeps today's
   crypto behaviour exactly. Cache the composite-symbol-to-calendar-id map in an instance dict
   with a 60-second TTL so the per-minute cron does not add a Mongo round trip per symbol per
   interval. The resolver is an APP-scoped singleton, and the cached data is not
   request-scoped, so the shared instance is safe.
4. Bind `TradingCalendarRegistry` and `SymbolCalendarResolver` in
   `app/di/infrastructure.py` as `Scope.APP` providers.
5. Both class names deviate from the `*Adapter` suffix rule; Task 2.11 records the exemption.

**Success criteria.** The resolver returns the CME calendar for a symbol whose record carries
`calendar_id="CME_GLOBEX_EQUITY"` and the 24/7 calendar for an unknown symbol.

**Verify.** `uv run pytest tests/core_test/infra/calendars -q` exits 0 with `0 failed` after
you add exactly 3 resolver tests (known CME symbol, known crypto symbol, unknown symbol) to a
new `tests/core_test/infra/calendars/test_symbol_calendar_resolver.py` using a stub repository
object rather than Mongo.

## Task 2.8 — Widen both composite-symbol regexes to accept `!`

**Goal.** `ES1!:CME_MINI` validates everywhere `BTCUSDT:BINANCE` does today.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py`: `COMPOSITE_SYMBOL_RE` (currently
  `^[A-Z0-9_-]+:[A-Z0-9_-]+$`) and `COMPOSITE_SYMBOL_PATTERN` (currently
  `^[A-Z0-9._-]{1,32}:[A-Z0-9._-]{1,32}$`).
- Consumers to re-check, not edit: `app/common/symbol_validation.validate_composite_symbol`,
  `engine/market_data/tracked_symbols_service.AddTrackedSymbolCommand.upper_and_validate`,
  `engine/market_data/tracked_symbols_backfill.BackfillTrackedSymbolCommand.upper_and_validate`.
- New test file `tests/core_test/unit/domain/test_composite_symbol_regex.py`.
- `web/` needs no change: verified that no TypeScript file contains a symbol regex, and
  `web/src/lib/symbol-format.ts` splits on the first `:` only.

**Steps.**
1. Add `!` to the allowed character class of BOTH regexes, giving
   `^[A-Z0-9!_-]+:[A-Z0-9!_-]+$` and `^[A-Z0-9.!_-]{1,32}:[A-Z0-9.!_-]{1,32}$`. Escape nothing:
   `!` is literal inside a character class.
2. Write the test file with exactly 6 tests: `ES1!:CME_MINI`, `NQ1!:CME_MINI` and
   `YM1!:CBOT_MINI` all validate through `Symbol.create(...)` and through
   `validate_composite_symbol`; `BTCUSDT:BINANCE` still validates; `es1!:cme_mini` is
   uppercased; `ES1!` with no colon is rejected.

**Success criteria.** The three futures composites validate; existing crypto validation is
unchanged.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_composite_symbol_regex.py -q`
exits 0 and prints `6 passed`.

## Task 2.9 — Persist `asset_class`, `calendar_id` and `contract_spec` on `Symbol`

**Goal.** The schedule and contract units live alongside the asset class on the symbol record.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py`: `Symbol` fields (`asset_type` at line 38),
  `Symbol.create` (line 63-70), `to_mongo` (line 84), `from_mongo` (line 97).
- `src/pocketquant/engine/market_data/symbols_service.py:20` (`"asset_type": s.asset_type`).
- `web/src/types/market-data.ts:26` (`asset_type: string`).
- New file `scripts/migrate_symbol_asset_class.py`.
- `scripts/README.md`: one bullet for the new script.

**Steps.**
1. Replace the `asset_type: str | None = None` field with:
   `asset_class: AssetClass = AssetClass.CRYPTO_SPOT`,
   `calendar_id: str = "CRYPTO_24_7"`,
   `contract_spec: ContractSpec = LINEAR_SPEC`.
   Use `model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)` if
   Pydantic needs it for the frozen dataclass; otherwise keep `ContractSpec` serialised through
   the explicit `to_mongo`/`from_mongo` conversions below.
2. Update `Symbol.create` to take `asset_class: AssetClass = AssetClass.CRYPTO_SPOT`,
   `calendar_id: str | None = None`, `contract_spec: ContractSpec = LINEAR_SPEC`. When
   `calendar_id` is None, derive it from `DEFAULT_CALENDAR_ID[asset_class]`.
3. `to_mongo` writes `"asset_class": self.asset_class.value`, `"calendar_id": self.calendar_id`
   and `"contract_spec": self.contract_spec.to_dict()`, and stops writing `asset_type`.
4. `from_mongo` reads `asset_class` with a fallback to `AssetClass.CRYPTO_SPOT` when the key is
   absent, `calendar_id` with a fallback to `DEFAULT_CALENDAR_ID[asset_class]`, and
   `contract_spec` through `ContractSpec.from_dict(doc.get("contract_spec") or {})`. This makes
   un-migrated documents load correctly, so the migration is a data cleanup rather than a hard
   cutover.
5. In `symbols_service.list_symbols`, replace the `asset_type` key with `asset_class`,
   `calendar_id` and `contract_spec` (as a dict). In `web/src/types/market-data.ts` rename the
   `asset_type: string` field to `asset_class: string` and add `calendar_id: string`. Grep for
   any TypeScript reader of `asset_type` before renaming; as of this plan there is none
   outside the type declaration.
6. Write `scripts/migrate_symbol_asset_class.py` following the conventions in
   `scripts/README.md` (reads `MONGODB_URL` from the environment, dry-run by default, `--apply`
   required for writes). It stamps every document in `symbols` that lacks `asset_class` with
   `asset_class="CRYPTO_SPOT"`, `calendar_id="CRYPTO_24_7"` and the linear
   `contract_spec`, and `$unset`s `asset_type`. Print the counts of matched and modified
   documents.

**Success criteria.** A `Symbol` round-trips through `to_mongo`/`from_mongo` with the new
fields, and a legacy document without them loads as `CRYPTO_SPOT` / `CRYPTO_24_7` / linear.

**Verify.** `uv run pytest tests/core_test/unit/domain -q` exits 0 with `0 failed` after you
add exactly 3 tests to a new
`tests/core_test/unit/domain/test_symbol_asset_class_roundtrip.py`: new-shape round trip,
legacy-document default, and `Symbol.create` deriving `calendar_id` from `INDEX_FUTURE`.

## Task 2.10 — Add `session_date` and `calendar_id` to bars

**Goal.** Daily and weekly bars carry a stable session day key while `datetime` keeps moving
with DST.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py`: `Bar` fields, `to_mongo`, `from_mongo`,
  `to_dict`.
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py`:
  `ensure_indexes` (line 284-290).

**Steps.**
1. Add `session_date: date | None = None` and `calendar_id: str | None = None` to `Bar`.
2. BSON has no date type. `to_mongo` must write `session_date` as the ISO string
   `self.session_date.isoformat()` (or `None`), and `from_mongo` must parse it back with
   `date.fromisoformat(...)` when the value is a non-empty string. Do not store a `datetime`
   for this field — it would reintroduce a timezone question for a value that has none.
3. Include both fields in `to_dict` (`session_date` as its ISO string).
4. In `ensure_indexes`, add a second, non-unique index
   `[("symbol", 1), ("interval", 1), ("session_date", 1)]` named
   `ix_ohlcv_symbol_interval_session_date`. Leave the existing unique
   `ix_ohlcv_symbol_interval_datetime` index untouched — `datetime` remains the identity.
5. Nothing populates these fields yet; Phase 3 sets them when persisting 1d and 1w bars.

**Success criteria.** A `Bar` with a `session_date` round-trips, and the new index is created.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar tests/core_test/infra/persistence/test_bar_repository.py -q`
exits 0 with `0 failed`.

## Task 2.11 — Record the naming exemption in the code standards

**Goal.** The calendar and resolver class names are a deliberate, documented exemption rather
than a silent violation.

**Target files and symbols.**
- `docs/code-standards.md`, the "Exempt list" table in the section
  "Naming Principles & Exemptions" (around line 400).

**Steps.**
1. Add one row to the exempt-list table: group `Calendar / registry / resolver`, example
   `Continuous24x7Calendar`, `CmeGlobexEquityCalendar`, `TradingCalendarRegistry`,
   `SymbolCalendarResolver`.
2. Add one sentence under the table: these implement `ITradingCalendarPort` or compose it, and
   a `*Adapter` suffix would read as an external-I/O boundary they do not have.
3. Change nothing else in this document.

**Success criteria.** The table contains the new row.

**Verify.** `grep -c "Continuous24x7Calendar" docs/code-standards.md` prints `1`.

## Task 2.12 — Phase 2 gate

**Goal.** The new vocabulary is in place with zero behaviour change.

**Target files and symbols.** None (verification only).

**Steps.**
1. Confirm that no file under `src/pocketquant/engine/` or `src/pocketquant/app/routes/` was
   modified in this phase except `symbols_service.py`.
2. Run all four gates.

**Success criteria.** All gates pass and the existing test count has only grown.

**Verify.** All of the following exit 0: `uv run ruff check src tests scripts`,
`uv run pyright`, `uv run lint-imports` (prints `Contracts: 8 kept, 0 broken.`),
`uv run pytest tests/ -q` (summary shows `0 failed`).

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

=== FILE: phase-03-calendar-threading-crypto-parity.md ===
---
phase: 3
title: "Thread the calendar through the pipeline on crypto only"
status: pending
priority: P1
effort: "3d"
dependencies: [2]
---

# Phase 3: Thread the calendar through the pipeline on crypto only

Advice Phase 2. This is the phase that retires the five day-one P0s while no futures symbol
exists. Every change is parameterized by the calendar and every default resolves to
`Continuous24x7Calendar`, so the crypto path must come out byte-identical. Do NOT create a
futures symbol during this phase.

The five sites, with the audit's file:line evidence:
alignment (`bar_builder_domain_service.py:10-32`, `bar_filters.py:72-82`),
cascade (`cascade_aggregator.py:46,98-137`),
integrity (`integrity_jobs.py:62-63`),
freshness (`sync_status_service.py:62-69`, `anomaly_log.py:35-40,52-59`),
annualization (`enums.py:5-13`, `performance_calculator_domain_service.py:13-14,108-109,166-167`).

## Task 3.1 — Capture golden files for the crypto path BEFORE refactoring

**Goal.** A byte-comparable baseline exists so parity is proven, not asserted.

**Target files and symbols.**
- New test file `tests/app_test/market_data/test_calendar_refactor_golden.py`.
- New fixture directory `tests/app_test/market_data/golden/`.

**Steps.**
1. Write a test module that builds a deterministic in-memory list of 1m `Bar` objects for
   `BTCUSDT:BINANCE` spanning exactly 3 UTC days starting `2026-03-06T00:00:00Z` (so the window
   contains the 2026-03-08 US DST transition, which must NOT affect crypto).
2. Compute and serialize three artefacts to JSON under `tests/app_test/market_data/golden/`:
   (a) the aligned/misaligned split from `filter_aligned_bars` for all 7 intervals;
   (b) the `compute_boundaries` output for all 5 cascade timeframes over that window;
   (c) `PerformanceCalculatorDomainService.build(...)` metrics for a fixed synthetic equity
   curve at intervals 1m, 1h and 1d.
3. Write exactly 3 tests that regenerate each artefact and assert equality with the committed
   JSON. Run them once NOW, against the pre-refactor code, and commit the produced JSON.
4. Do not regenerate the golden files later in this phase. If a later task changes them, the
   refactor changed crypto behaviour and the Failure Protocol applies.

**Success criteria.** The three golden JSON files exist and the tests pass against unmodified
code.

**Verify.** `uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q`
exits 0 and prints `3 passed`, AND
`ls tests/app_test/market_data/golden/` lists exactly 3 `.json` files.

## Task 3.2 — Make bar alignment calendar-aware

**Goal.** Alignment is decided by the symbol's calendar, not by a UTC-midnight rule.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py`: `get_bar_start`
  (line 10), `is_bar_aligned` (line 31), `filter_aligned_bars` (line 35),
  `BarBuilderDomainService.create_for_tick` (line 125).
- All 4 production call sites, verified by grep:
  `engine/market_data/sync_internals/bar_filters.py:74` (`filter_aligned_bars`),
  `engine/market_data/sync_internals/bar_alignment.py:7` (`is_bar_aligned`),
  `engine/market_data/app_services/integrity_jobs.py:51,57`,
  `engine/market_data/app_services/bar_app_service.py:88`.
- `src/pocketquant/core/domain/bar/services/__init__.py` `__all__`.
- `tests/core_test/unit/domain/bar/services/test_bar_builder.py` (lines 13-14, 102-127).

**Steps.**
1. Change the three module-level functions to take the calendar as a required final parameter:
   `get_bar_start(timestamp, interval, calendar)`,
   `is_bar_aligned(timestamp, interval, calendar)`,
   `filter_aligned_bars(bars, interval, calendar)`. Their bodies delegate to
   `calendar.bar_start(timestamp, interval)`. Keep `filter_aligned_bars`'s return shape
   `(aligned, misaligned)`.
2. `BarBuilderDomainService.create_for_tick(symbol, interval, timestamp, calendar)` gains the
   same parameter.
3. Update `drop_misaligned_bars(records, interval, calendar)` in `bar_filters.py` and
   `has_aligned_bar(records, interval, calendar)` in `bar_alignment.py`, then their callers:
   `fetch_with_retry(provider, symbol, interval, n_bars, calendar)` in
   `sync_internals/provider_fetch.py` and `SyncService.sync_one` (which calls both at
   `sync_service.py:79-81`).
4. In `bar_app_service.BarAppService`, add a `calendar_resolver: SymbolCalendarResolver`
   constructor parameter, resolve the calendar ONCE per `add_tick` call
   (`calendar = await self._calendar_resolver.for_symbol(symbol_key)`) and pass it into
   `_process_tick_for_interval`. Update the DI provider `MarketDataProvider.get_bar_manager`
   in `app/di/market_data.py` to inject it.
5. Update `tests/core_test/unit/domain/bar/services/test_bar_builder.py` to pass
   `Continuous24x7Calendar()` at every call site. Do not change any assertion value — the
   Monday-00:00-UTC weekly expectations must still hold.

**Success criteria.** All alignment calls take a calendar; the existing bar-builder assertions
are unchanged and still pass.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar tests/engine_test/market_data/test_sync_service.py -q`
exits 0 with `0 failed`, AND
`grep -rn "get_bar_start(" src/ | grep -v "calendar"` exits 1 (every call site passes one).

## Task 3.3 — Make the cascade session-anchored

**Goal.** Bucket boundaries and expected counts come from the calendar.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`:
  `_TF_EXPECTED_BARS` (line 46), `compute_boundaries` (lines 98-137),
  `cascade_for_symbol` (line 139 onward), the `cascade.partial_aggregate` WARNING (lines
  185-195).
- Caller `engine/market_data/app_services/sync_jobs.py:412` inside `sync_1m`.
- Caller `engine/market_data/tracked_symbols_backfill.py:148` (`_cascade`).
- `tests/app_test/market_data/test_cascade_aggregator.py` (18 tests today).

**Steps.**
1. Change the signature to
   `compute_boundaries(tf, range_start, range_end, calendar)`. Replace the
   `math.floor(epoch / secs) * secs` flooring with `calendar.bar_start(range_start, tf)` for
   the first boundary, then advance with `calendar.bar_start(previous + timedelta(seconds=secs)
   + timedelta(seconds=1), tf)` so that a session-aware calendar never emits a boundary inside
   a closed period. For the 24/7 calendar this reduces to the existing arithmetic grid.
2. Preserve the existing overlap rule verbatim (`B < range_end` and
   `B + tf_seconds > range_start`) and its docstring rationale about 4h/1d buckets freezing
   under a 100-minute lookback.
3. Delete `_TF_EXPECTED_BARS` and call `calendar.expected_source_bars(tf, boundary)` instead,
   both for the `limit=expected_count + 5` query headroom and for the
   `cascade.partial_aggregate` comparison.
4. `cascade_for_symbol(symbol, lookback_minutes, bar_repo, calendar)` gains the parameter.
   Update `sync_jobs.sync_1m` to resolve the calendar per tracked symbol through
   `SymbolCalendarResolver` before calling it, and update
   `TrackedSymbolBackfillService._cascade` the same way (inject the resolver into that service
   and its DI provider).
5. When the persisted timeframe is `DAY_1` or `WEEK_1`, set
   `bar.session_date = calendar.session_date_of(boundary)` and
   `bar.calendar_id = calendar.calendar_id` on the upserted `Bar`, and make
   `BarRepository.upsert_bar` persist those two fields.

**Success criteria.** Crypto cascade output is unchanged; boundaries for a session calendar are
session opens.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_aggregator.py
tests/app_test/market_data/test_calendar_refactor_golden.py -q` exits 0 with `0 failed` and
the golden test still reports `3 passed`.

## Task 3.4 — Make the integrity grid calendar-derived

**Goal.** Weekends, halts and holidays are not reported as gaps.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py`: `check_integrity`
  (line 35), the dense grid at lines 62-63, the docstring caveat at lines 46-47,
  `repair_integrity` (line 79).
- Callers: `engine/market_data/app_services/sync_jobs.py` `_run_integrity` (around line 300)
  and `sync_repair`; `src/pocketquant/app/routes/integrity.py`.

**Steps.**
1. Add a required `calendar: ITradingCalendarPort` parameter to both `check_integrity` and
   `repair_integrity`, placed after `bar_repo`.
2. Replace `expected = {start + i * step for i in range(int((end - start) / step))}` with:
   - for `Interval.MINUTE_1`: `set(calendar.trading_minutes(start, end))`;
   - for `Interval.DAY_1`: `{calendar.session_open(d) for d in calendar.sessions(start, end)}`;
   - for every other intraday interval: the set of `calendar.bar_start(m, interval)` values
     over `calendar.trading_minutes(start, end)`;
   - for `Interval.WEEK_1`: when `calendar.calendar_id != "CRYPTO_24_7"`, return a report with
     `missing_count=0` and `gap_ranges=[]` and log one DEBUG `integrity.weekly_skipped`. A
     weekly convention for session calendars is deliberately out of scope.
3. Delete the "Only reliable for 24/7 markets (crypto)" caveat at lines 46-47 and replace it
   with one sentence naming the calendar parameter as the authority.
4. Update `is_bar_aligned(d["datetime"], interval)` at line 57 and
   `get_bar_start(now, interval)` at line 51 to pass the calendar.
5. Update every caller to resolve the calendar via `SymbolCalendarResolver` before the call.

**Success criteria.** For the 24/7 calendar the expected set is identical to the old arithmetic
grid; for the CME calendar a weekend produces zero missing minutes.

**Verify.** `uv run pytest tests/engine_test/market_data tests/app_test/market_data -q` exits 0
with `0 failed`, AND a new `tests/engine_test/market_data/test_integrity_calendar_grid.py` with
exactly 4 tests (24/7 grid parity with the arithmetic grid; CME weekend has zero missing;
CME daily halt has zero missing; CME 1w returns a zero-gap report) exits 0 printing `4 passed`.

## Task 3.5 — Make freshness and anomaly gating calendar-aware

**Goal.** A closed market is never reported as stuck and never floods the log.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_status_service.py`: `_is_stuck` (lines 62-69),
  `SyncStatusResult` (lines 47-60), `get_sync_status` (line 96 onward),
  `get_symbol_sync_status`.
- `src/pocketquant/engine/market_data/sync_internals/anomaly_log.py`: `emit_no_progress`
  (lines 20-59).
- `src/pocketquant/engine/market_data/sync_service.py:100-110` (the `emit_no_progress` call).
- `src/pocketquant/app/routes/market_data_status.py`: both response dicts.

**Steps.**
1. Change `_is_stuck(latest_bar_dt, interval, calendar)`. Compute
   `now = datetime.now(UTC)`; `reference = now if calendar.is_open(now) else
   calendar.previous_close(now)`; `age = (reference - latest_bar_dt).total_seconds()`. For the
   24/7 calendar `previous_close` is the identity and `is_open` is always True, so the crypto
   result is unchanged.
2. Add `is_market_open: bool = True` to `SyncStatusResult` and populate it from
   `calendar.is_open(datetime.now(UTC))`. Add the key `is_market_open` to BOTH dict literals in
   `app/routes/market_data_status.py`.
3. Inject `SymbolCalendarResolver` into `SyncStatusQueryService.__init__` and resolve the
   calendar per status row inside `get_sync_status` / `get_symbol_sync_status`. Update the DI
   binding for that service.
4. In `emit_no_progress`, add a required `calendar` parameter and return immediately, with no
   log emission at all, when `not calendar.is_open(datetime.now(UTC))`. Without this, a futures
   symbol emits roughly 2,900 WARN records per weekend, which violates the CLAUDE.md rule that
   log level is a function of frequency.
5. Compute `age_s` against the same `reference` as `_is_stuck` so the two never disagree.
6. Update the single call site in `sync_service.py` to pass the calendar it already resolved
   for the alignment filter.

**Success criteria.** A closed-market symbol reports `is_market_open=false`, `is_stuck=false`
and emits no anomaly log.

**Verify.** A new `tests/engine_test/market_data/test_freshness_calendar_gating.py` with
exactly 5 tests (crypto stuck detection unchanged; CME symbol not stuck 10 minutes after
Friday close; CME symbol not stuck over a full weekend; `emit_no_progress` emits nothing while
closed; `emit_no_progress` still emits while open) runs
`uv run pytest tests/engine_test/market_data/test_freshness_calendar_gating.py -q` exiting 0
and printing `5 passed`.

## Task 3.6 — Move annualization onto the calendar

**Goal.** Periods-per-year is owned by the calendar, not by the `Interval` enum.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py`: `_PERIODS_PER_YEAR` (lines 4-13),
  `Interval.periods_per_year` (line 26), `Interval.periods_per_year_for` (line 34).
- `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py`:
  `TRADING_DAYS_PER_YEAR` (line 14) and the two docstring references at lines 81 and 129.
- The single production consumer:
  `src/pocketquant/engine/backtest/backtest_report_app_service.py:368`.
- `tests/core_test/unit/domain/shared/test_interval.py` (12 tests; 9 of them assert
  `periods_per_year`).

**Steps.**
1. Move the `_PERIODS_PER_YEAR` table verbatim into `Continuous24x7Calendar.periods_per_year`
   (Task 2.4 already required the same values). Delete `_PERIODS_PER_YEAR`,
   `Interval.periods_per_year` and `Interval.periods_per_year_for` from `enums.py`.
2. Delete the `TRADING_DAYS_PER_YEAR = 365` constant from the performance calculator; it has no
   remaining reader once the enum property is gone (verified by grep: the only hits are the
   definition and two docstrings). Update the two docstrings to say the value comes from
   `ITradingCalendarPort.periods_per_year(interval)`.
3. In `backtest_report_app_service.py`, replace
   `periods_per_year = Interval.periods_per_year_for(self._config.interval)` with a lookup
   through a `calendar` the service now receives. Add `calendar: ITradingCalendarPort` to
   `BacktestReportAppService.__init__` and thread it from
   `engine/backtest/backtest_app_service.py` and `engine/backtest/backtest_dispatch.py`, which
   resolve it from the run's symbol through `SymbolCalendarResolver`. Keep the existing
   "unknown interval" WARNING path by catching `KeyError` from the calendar and passing `None`.
4. Rewrite `tests/core_test/unit/domain/shared/test_interval.py`: move the 9 annualization
   tests into `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py` as
   calendar assertions with identical expected values (525600, 105120, 35040, 8760, 2190, 365,
   365/7 and the unknown-interval case). Keep the 3 enum-shape tests in place. Do not delete a
   single assertion; relocate them.

**Success criteria.** `Interval` no longer exposes `periods_per_year`; crypto annualization
numbers are unchanged.

**Verify.** `grep -rn "periods_per_year" src/pocketquant/core/domain/shared/enums.py` exits 1,
AND `uv run pytest tests/core_test/unit/domain tests/backtest_test -q` exits 0 with `0 failed`,
AND the golden test still reports `3 passed`.

## Task 3.7 — Gate the sync cron on the calendar

**Goal.** No provider call is made while the market is closed, and closed cycles are visible.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py`: `_sync_by_intervals`
  (line 130), `SYNC_INTERVALS` (lines 54-62), `sync_1m` (line 382),
  `sync_backfill` (line 609).

**Steps.**
1. Add a `calendar_resolver: SymbolCalendarResolver` parameter to `_sync_by_intervals` and
   resolve the calendar once per symbol, before the interval loop.
2. Before building the `SyncSymbolCommand`, skip when the market is closed AND the grace
   window has elapsed: `now = datetime.now(UTC)`; if `not calendar.is_open(now)` and
   `now - calendar.previous_close(now) > timedelta(seconds=INTERVAL_SECONDS[interval])`, then
   increment a `skipped_closed` counter, record a job-history detail with
   `status="skipped_closed"`, and `continue` without calling `sync_service.sync_one`. One
   interval of grace lets the last bar of a session still arrive.
3. `Continuous24x7Calendar.is_open` always returns True, so crypto never takes the skip branch.
4. Include `skipped_closed` in the `sync_1m` summary log, which stays at INFO because it is one
   record per cron run, not per symbol.
5. For `INDEX_FUTURE` symbols, `DAY_1` and `WEEK_1` stay in `SYNC_INTERVALS` and are fetched
   natively from the provider. This is the same precedent the code already documents for
   Binance 1w at lines 51-53, and it is now safe because Task 3.2 made alignment
   calendar-aware.

**Success criteria.** A closed-market symbol produces a `skipped_closed` detail and zero
provider calls; crypto behaviour is unchanged.

**Verify.** A new `tests/engine_test/market_data/test_sync_closed_market_gating.py` with
exactly 4 tests (crypto never skips; CME symbol skips on a Saturday; CME symbol does not skip
within the one-interval grace after close; the skip path never calls the provider — assert with
a stub provider whose `fetch_ohlcv` raises) runs
`uv run pytest tests/engine_test/market_data/test_sync_closed_market_gating.py -q` exiting 0
and printing `4 passed`.

## Task 3.8 — Phase 3 gate and crypto parity proof

**Goal.** The refactor is behaviour-preserving on crypto in test and in production.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run all four gates plus the timezone matrix.
2. Deploy to the VPS and let one full `sync_1m` cycle plus one `sync_verify_cascade` run
   complete for `BTCUSDT:BINANCE`, `ETHUSDT:BINANCE` and `SOLUSDT:BINANCE`. Compare
   `synced_count` and the latest bar values with the values recorded before deployment.
3. Record the before/after numbers in
   `plans/260921-1436-asset-class-index-futures/reports/phase-03-crypto-parity.md`.

**Success criteria.** Golden files unchanged, all gates green, one production cron cycle
identical.

**Verify.** All of the following exit 0: `uv run ruff check src tests scripts`,
`uv run pyright`, `uv run lint-imports` (prints `Contracts: 8 kept, 0 broken.`),
`uv run pytest tests/ -q` (`0 failed`), `just test-tz`, AND
`git status --porcelain tests/app_test/market_data/golden/` produces no output (the golden
files were not modified).

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

=== FILE: phase-04-provider-routing-layer.md ===
---
phase: 4
title: "Provider routing layer with Binance-only registration"
status: pending
priority: P1
effort: "1d"
dependencies: [3]
---

# Phase 4: Provider routing layer with Binance-only registration

Advice Phase 3. Replace the single DI binding for both market-data ports with routing
adapters that resolve providers per symbol from the symbol's asset class. Register Binance as
the only provider and prove the crypto path is unchanged. Because the routing adapters
implement the same ports, `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService` and
`QuoteAppService` need no edits — that is goal G4.

## Task 4.1 — Add provider configuration to `Settings`

**Goal.** Provider selection is configuration, not code.

**Target files and symbols.**
- `src/pocketquant/core/config.py`: `Settings`.
- New file `src/pocketquant/core/domain/market_data/provider_ids.py`.

**Steps.**
1. Create `provider_ids.py` with the module-level constants
   `PROVIDER_BINANCE = "binance"` and `PROVIDER_TRADINGVIEW = "tradingview"`. Keep them plain
   strings so a new provider id is a string in config, not an enum edit.
2. Add to `Settings`:
   - `market_data_providers: dict[AssetClass, list[str]] = {}`
   - `symbol_provider_overrides: dict[str, list[str]] = {}`
   pydantic-settings parses a JSON object from the environment for these complex types, so the
   env values are
   `MARKET_DATA_PROVIDERS={"CRYPTO_SPOT":["binance"],"CRYPTO_PERP":["binance"],"INDEX_FUTURE":["tradingview"]}`
   and `SYMBOL_PROVIDER_OVERRIDES={"ES1!:CME_MINI":["tradingview"]}`.
3. Add a `model_validator` that, for any `AssetClass` absent from `market_data_providers`,
   fills in `[PROVIDER_BINANCE]` for the two crypto classes and `[]` for `INDEX_FUTURE`, so an
   existing `.env` with neither key keeps working unchanged.
4. Do not add any TradingView setting yet; that is Phase 5.
5. Add the two field names (never values) to the settings list in `README.md`.

**Success criteria.** `Settings()` constructs with no new env vars and yields
`{CRYPTO_SPOT: ["binance"], CRYPTO_PERP: ["binance"], INDEX_FUTURE: []}`.

**Verify.** `uv run pytest tests/ -q -k config` exits 0 with `0 failed`, AND
`uv run python -c "from pocketquant.core.config import Settings;
import os; print(Settings().market_data_providers)"` (run with the test env defaults from
`tests/conftest.py` exported) exits 0 and prints a dict containing `binance`.

## Task 4.2 — Pure provider-resolution function

**Goal.** "Which providers, in what order, for this symbol" is one testable pure function.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/provider_resolution.py`: function
  `resolve_provider_ids(symbol, asset_class, providers_by_class, symbol_overrides) -> list[str]`.
- New test file `tests/core_test/unit/domain/market_data/test_provider_resolution.py`.

**Steps.**
1. The function returns `symbol_overrides[symbol.upper()]` when the key exists, otherwise
   `providers_by_class.get(asset_class, [])`. It never raises and never performs I/O.
2. The first element is the primary provider; later elements are fallbacks.
3. Write exactly 5 tests: override wins over class map; class map used when no override;
   unknown asset class returns an empty list; the returned order is preserved; a lowercase
   symbol matches an uppercase override key.

**Success criteria.** Resolution order is deterministic and override-first.

**Verify.** `uv run pytest tests/core_test/unit/domain/market_data/test_provider_resolution.py -q`
exits 0 and prints `5 passed`.

## Task 4.3 — `RoutingDataProviderAdapter`

**Goal.** REST history fetches route to the right provider with fallback.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/market_data/` with `__init__.py` and
  `routing_data_provider_adapter.py` defining
  `class RoutingDataProviderAdapter(IDataProviderPort)`.
- `tests/core_test/test_core_layout_contract.py`: add
  `"pocketquant.core.infra.market_data"` to `NEW_MODULES`.

**Steps.**
1. Constructor takes `adapters: dict[str, IDataProviderPort]`, `settings: Settings` and
   `symbol_repository: SymbolRepository` (to read the symbol's `asset_class`). Cache the
   composite-symbol-to-asset-class map in an instance dict with a 60-second TTL, mirroring
   `SymbolCalendarResolver`; the adapter is an APP-scoped singleton so this cache is process
   wide and not request scoped.
2. `fetch_ohlcv(symbol, interval, n_bars)` resolves the ordered provider ids via
   `resolve_provider_ids(...)`, then tries each in turn. Move to the next provider when the
   current one raises OR returns an empty list. Log one WARNING
   `market_data.provider.fallback` naming the failed and next provider ids — this is
   low-frequency and recoverable, which matches WARNING. Raise the last exception when every
   provider fails; return `[]` when every provider returns empty.
3. When the symbol has no record or resolves to an empty provider list, fall back to
   `PROVIDER_BINANCE` when it is registered, so the existing crypto path cannot break.
4. `search_symbols(query)` delegates to the first registered adapter.
5. `close()` awaits `close()` on every registered adapter.

**Success criteria.** A single-provider registry behaves exactly like the bare adapter; a
failing primary falls through to the secondary.

**Verify.** A new `tests/core_test/infra/market_data/test_routing_data_provider_adapter.py`
with exactly 6 tests (single provider passthrough; primary raises then fallback succeeds;
primary returns empty then fallback succeeds; all fail raises; unknown symbol defaults to
binance; `close()` closes all) runs
`uv run pytest tests/core_test/infra/market_data/test_routing_data_provider_adapter.py -q`
exiting 0 and printing `6 passed`.

## Task 4.4 — `RoutingQuoteProviderAdapter`

**Goal.** Realtime subscriptions route per symbol with NO fallback.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/market_data/routing_quote_provider_adapter.py`:
  `class RoutingQuoteProviderAdapter`.

**Steps.**
1. The class must structurally satisfy the 9-member `IRealtimeQuoteProviderPort` Protocol:
   the `last_tick_at` attribute plus `connect`, `disconnect`, `subscribe`, `unsubscribe`,
   `run_forever`, `is_connected`, and the `subscription_count` and `subscriptions` properties.
2. Constructor takes `adapters: dict[str, IRealtimeQuoteProviderPort]`, `settings` and
   `symbol_repository`, and keeps `_owner: dict[str, str]` mapping composite symbol to the
   provider id that owns its subscription.
3. `subscribe(symbol, callback)` resolves the provider ids and delegates to the FIRST one only.
   Do NOT fall back for realtime: two providers streaming the same symbol would double-count
   ticks in `BarBuilderDomainService`. Record the owner and return the child's key.
4. `unsubscribe(symbol)` delegates to the recorded owner and clears the entry.
5. `connect` / `disconnect` fan out to every child. `run_forever` runs
   `asyncio.gather(*(a.run_forever() for a in adapters.values()))`.
6. `is_connected()` returns True when every child with at least one subscription is connected.
   `subscription_count` sums the children. `subscriptions` returns the merged dict, which is
   what `WsSubscriptionAppService._reconcile` reads at `ws_subscription_app_service.py:68`.
7. `last_tick_at` returns the maximum non-None `last_tick_at` across children.

**Success criteria.** `isinstance(adapter, IRealtimeQuoteProviderPort)` is True and the merged
`subscriptions` dict drives reconciliation correctly.

**Verify.** A new `tests/core_test/infra/market_data/test_routing_quote_provider_adapter.py`
with exactly 5 tests (runtime Protocol isinstance check; subscribe delegates to the first
provider only; unsubscribe reaches the owner; merged `subscriptions` and `subscription_count`;
`run_forever` gathers all children) runs
`uv run pytest tests/core_test/infra/market_data/test_routing_quote_provider_adapter.py -q`
exiting 0 and printing `5 passed`.

## Task 4.5 — Swap the DI bindings to the routing adapters

**Goal.** The container serves routing adapters, with Binance as the only registered provider.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py`: `InfrastructureProvider.get_data_provider`
  (currently `return BinanceAdapter(settings=settings)`).
- `src/pocketquant/app/di/market_data.py`: `MarketDataProvider.get_realtime_quote_provider`
  (currently `return BinanceWebSocketAdapter()`).

**Steps.**
1. In `infrastructure.py`, change `get_data_provider` to build
   `{PROVIDER_BINANCE: BinanceAdapter(settings=settings)}` and return a
   `RoutingDataProviderAdapter(adapters=..., settings=settings, symbol_repository=...)`.
   Add `SymbolRepository` to the provider method signature so Dishka injects it.
2. In `market_data.py`, change `get_realtime_quote_provider` the same way with
   `{PROVIDER_BINANCE: BinanceWebSocketAdapter()}` and `RoutingQuoteProviderAdapter`. Keep the
   existing `# type: ignore[return-value]` comment about structural Protocol satisfaction.
3. Register NO other provider in this phase.
4. Do not touch `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService` or
   `QuoteAppService` — if any of them needs an edit, the routing adapters are not port
   compatible and the Failure Protocol applies.

**Success criteria.** The container resolves both ports to routing adapters and the app boots.

**Verify.** `uv run pytest tests/app_test -q` exits 0 with `0 failed`, AND
`git diff --stat src/pocketquant/engine/ src/pocketquant/app/routes/` produces no output for
this task.

## Task 4.6 — Prove G4 with a config-only third provider

**Goal.** Adding a provider requires one adapter plus one config entry and zero caller edits.

**Target files and symbols.**
- New test file `tests/core_test/infra/market_data/test_provider_registration_g4.py`.

**Steps.**
1. Define a `_FakeProviderAdapter(IDataProviderPort)` INSIDE the test file that records the
   symbols it was asked for.
2. Build a `RoutingDataProviderAdapter` with `{"binance": <stub>, "fake": _FakeProviderAdapter()}`
   and a `Settings`-shaped stub whose `symbol_provider_overrides` maps one composite symbol to
   `["fake"]`.
3. Assert the fake adapter received the fetch and the binance stub did not.
4. Add a second test asserting that this test file's imports reference nothing under
   `pocketquant.engine` or `pocketquant.app`.

**Success criteria.** A third provider is reachable through configuration alone.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_provider_registration_g4.py -q`
exits 0 and prints `2 passed`, AND
`grep -c "pocketquant.engine\|pocketquant.app" tests/core_test/infra/market_data/test_provider_registration_g4.py`
prints `0`.

## Task 4.7 — Phase 4 gate

**Goal.** Routing is in place with the crypto path provably unchanged.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run all four gates and the timezone matrix.
2. Deploy to the VPS and let one full `sync_1m` cycle complete; compare `synced_count` and
   latest bar values with the Phase 3 parity record.
3. Append the numbers to
   `plans/260921-1436-asset-class-index-futures/reports/phase-03-crypto-parity.md`.

**Success criteria.** All gates green; one production cron cycle identical to Phase 3.

**Verify.** All of the following exit 0: `uv run ruff check src tests scripts`,
`uv run pyright`, `uv run lint-imports` (prints `Contracts: 8 kept, 0 broken.`),
`uv run pytest tests/ -q` (`0 failed`), `just test-tz`.

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

=== FILE: phase-05-tradingview-history-and-futures-seed.md ===
---
phase: 5
title: "TradingView history adapter, credentials and futures seed"
status: pending
priority: P1
effort: "2d"
dependencies: [4]
---

# Phase 5: TradingView history adapter, credentials and futures seed

Advice Phase 4. Build the REST-history half of the TradingView provider behind a swappable
internal client, add its settings, seed the three futures symbols and backfill to the
configured cap. The realtime half is Phase 6.

Hard constraint from CLAUDE.md: credentials live ONLY in `../pocketquant-config/`. This
repository carries field names and documented defaults, never values. Nothing in this phase may
put a username, password or auth token in code, tests, docs or a committed env file.

Entitlement is configuration. Do NOT branch on the TradingView plan tier anywhere: the bar cap,
the delayed-data flag and the credentials are settings, so the user upgrades the account without
a code change.

## Task 5.1 — Add the scraper dependency

**Goal.** `tvdatafeed` is installed and locked.

**Target files and symbols.**
- `pyproject.toml` `[project] dependencies`, `uv.lock`.

**Steps.**
1. Run `uv add "tvdatafeed @ git+https://github.com/rongardF/tvdatafeed"`. There is no PyPI
   release; the package is installed from git. `deploy/Dockerfile` already apt-installs `git`
   in its builder stage, so the image build still works.
2. Confirm `uv.lock` records the dependency and that `uv sync --frozen` succeeds.
3. `[UNVERIFIED]` The exact `get_hist` signature and the library's own interval enum could not
   be checked from this repository (the package is not installed and no network read was made
   while planning). Before writing the mapper, read the installed source at
   `.venv/lib/python3.14/site-packages/tvDatafeed/main.py` and build the interval map from the
   enum you find there.

**Success criteria.** The package imports.

**Verify.** `uv run python -c "import tvDatafeed, inspect;
print([m for m in dir(tvDatafeed.Interval) if not m.startswith('_')])"` exits 0 and prints a
non-empty list.

## Task 5.2 — Define the internal TradingView client interface

**Goal.** The scraper library is isolated behind one swappable interface.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/tradingview/` with `__init__.py` and
  `tradingview_client.py` defining `class RawBar` and `class ITradingViewClient(Protocol)`.
- `tests/core_test/test_core_layout_contract.py`: add
  `"pocketquant.core.infra.tradingview"` to `NEW_MODULES`.

**Steps.**
1. `@dataclass(frozen=True) class RawBar` carries `epoch_seconds: float`, `open`, `high`,
   `low`, `close`, `volume` — all floats. It deliberately does NOT carry a `datetime`: the
   mapper owns instant construction.
2. `class ITradingViewClient(Protocol)` declares
   `async def fetch_bars(self, code: str, exchange: str, interval: Interval, n_bars: int,
   fut_contract: int | None) -> list[RawBar]` and
   `def is_authenticated(self) -> bool`.
3. Mark it `@runtime_checkable` so a swap can be asserted in tests. Document in the module
   docstring that a second implementation (a persistent chart session) can be dropped in here
   without touching the adapter.

**Success criteria.** The module imports and `lint-imports` still reports 8 contracts kept.

**Verify.** `uv run lint-imports` exits 0 and prints `Contracts: 8 kept, 0 broken.`

## Task 5.3 — Implement `TvDatafeedClient`

**Goal.** The synchronous scraper is usable from the async pipeline, with UTC-correct epochs.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tvdatafeed_client.py`:
  `class TvDatafeedClient`.

**Steps.**
1. Constructor takes `username: str | None`, `password: SecretStr | None`,
   `auth_token: SecretStr | None`. Construct the library's `TvDatafeed` object lazily on first
   use. On a login failure, log one WARNING `provider.tradingview.auth_degraded` and fall back
   to the library's no-login mode. NEVER let a login failure crash the process, and NEVER log
   the credential values.
2. Call `assert_utc_process()` (added in Phase 1, Task 1.3) in the constructor and let it
   raise. This client's correctness depends on the process timezone being UTC — see step 4.
3. `fetch_bars` wraps the library's synchronous `get_hist(...)` in `asyncio.to_thread`, because
   the library is thread-based and blocking.
4. The library builds its DataFrame index with naive `datetime.fromtimestamp(t)` — naive HOST
   LOCAL time (audit: `tvDatafeed/main.py:143`). Because Phase 1 pins and asserts `TZ=UTC`,
   that naive value IS the UTC wall time, so recover the epoch as
   `epoch_seconds = idx.replace(tzinfo=UTC).timestamp()` for each index entry. Add a comment
   stating this dependency explicitly so nobody removes the UTC pin without noticing.
5. Return `list[RawBar]` in ascending time order. Return `[]` (never raise) when the library
   returns `None` or an empty frame, so the routing adapter's fallback rule can act on it.
6. `is_authenticated()` returns whether the login succeeded.
7. Log per-fetch detail at DEBUG only (this is a per-symbol-per-interval hot path); log at INFO
   only the one-shot login outcome.

**Success criteria.** The client compiles and its epoch recovery is exercised offline.

**Verify.** `uv run pytest tests/core_test/infra/tradingview -q` exits 0 with `0 failed` after
Task 5.4 adds the fixtures; for this task alone,
`uv run python -c "from pocketquant.core.infra.tradingview.tvdatafeed_client import
TvDatafeedClient; print('ok')"` exits 0 and prints `ok`.

## Task 5.4 — TradingView mappers with offline fixtures

**Goal.** Symbol, interval and bar mapping are pure and tested without network access.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_mappers.py`:
  `INTERVAL_TO_TV`, `split_tradingview_symbol`, `raw_bar_to_bar`.
- New fixture directory `tests/core_test/infra/tradingview/fixtures/` and test file
  `tests/core_test/infra/tradingview/test_tradingview_mappers.py`.

**Steps.**
1. `INTERVAL_TO_TV: dict[Interval, <library enum>]` covers all 7 intervals. Build it from the
   enum members you printed in Task 5.1; do not guess the names.
2. `split_tradingview_symbol(composite) -> tuple[str, str, int | None]` splits
   `ES1!:CME_MINI` into `("ES", "CME_MINI", 1)`: strip a trailing `N!` from the code and return
   `N` as `fut_contract`; return `fut_contract=None` when there is no `!` suffix. Tests must
   cover `ES1!:CME_MINI`, `NQ1!:CME_MINI`, `YM1!:CBOT_MINI` and a plain `BTCUSDT:BINANCE`.
3. `raw_bar_to_bar(raw: RawBar, composite: str, interval: Interval) -> Bar` constructs
   `datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)`. It must NEVER construct a naive
   datetime and never read a library DataFrame index directly.
4. Save two JSON fixtures under `tests/core_test/infra/tradingview/fixtures/`: one
   `es_1m_sample.json` of 10 raw rows spanning the 2026-03-08 DST transition, and one
   `es_1d_sample.json` of 5 raw rows whose epochs are CME session opens on both sides of that
   transition. Fixture rows are epoch plus OHLCV only; invent no prices resembling real data
   beyond plausible ES levels.
5. Write exactly 8 tests: 4 symbol-split cases; all 7 intervals map to a distinct library
   value; a 1m row maps to the expected UTC instant; the 1d fixture maps to instants at 22:00
   and 23:00 UTC across the transition; a mapped `Bar.datetime` is always tz-aware.

**Success criteria.** Mapping is correct across the DST boundary with no network access.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q`
exits 0 and prints `8 passed`.

## Task 5.5 — Implement `TradingViewAdapter`

**Goal.** A working `IDataProviderPort` for index futures.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_adapter.py`:
  `class TradingViewAdapter(IDataProviderPort)`.

**Steps.**
1. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_resolver: SymbolCalendarResolver`.
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - clamp `n_bars` to `min(n_bars, settings.tradingview_max_bars)`;
   - split the composite symbol with `split_tradingview_symbol`;
   - call `client.fetch_bars(...)`;
   - map each row with `raw_bar_to_bar`;
   - drop the in-progress bar: resolve the calendar for this symbol and keep only bars whose
     `datetime < calendar.bar_start(datetime.now(UTC), interval)`. This is the same rule the
     Binance adapter uses after Phase 1 Task 1.7, so the two can never disagree;
   - return bars in ascending order.
3. `search_symbols(query)` returns `[]` — TradingView symbol search is out of scope; document
   that in the docstring.
4. `close()` is a no-op coroutine.
5. Never return a naive datetime. Log per-fetch counts at DEBUG.

**Success criteria.** With a stub client the adapter returns aligned, tz-aware, capped bars.

**Verify.** A new `tests/core_test/infra/tradingview/test_tradingview_adapter.py` with exactly
5 tests (bar cap clamping; in-progress bar dropped; all returned datetimes tz-aware; empty
client result returns `[]`; ascending order) runs
`uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q` exiting 0 and
printing `5 passed`.

## Task 5.6 — TradingView settings and credential placement

**Goal.** Entitlement is configuration and secrets stay out of the repository.

**Target files and symbols.**
- `src/pocketquant/core/config.py`: `Settings`.
- `README.md`, the settings list.
- `../pocketquant-config/local/all-local.env` and `../pocketquant-config/vps/default/.env`
  (OUTSIDE this repository).

**Steps.**
1. Add to `Settings`:
   - `tradingview_username: str | None = None`
   - `tradingview_password: SecretStr | None = None`
   - `tradingview_auth_token: SecretStr | None = None`
   - `tradingview_max_bars: int = 5000`
   - `tradingview_poll_seconds: int = 60`
   - `tradingview_delayed_data: bool = True`
   Use `SecretStr` for both credential fields so they cannot leak through logging or
   serialisation.
2. Comment `tradingview_poll_seconds`: 60 is the default because every TradingView plan serves
   CME 10-minute delayed data until the non-professional add-on is bought, so polling faster
   only raises ban risk without producing fresher data. Lower it only after that add-on is
   active.
3. Add the six field NAMES (never values) to the settings list in `README.md`, plus one
   sentence that the values live in `../pocketquant-config/`.
4. Write the actual values into the two config-repo env files. Do not commit them here.

**Success criteria.** `Settings()` constructs without the new variables; no value appears in
this repository.

**Verify.** `git grep -iE "tradingview_(username|password|auth_token)\s*=" -- ':!*.md'` returns
only the field declarations in `src/pocketquant/core/config.py` and nothing that looks like a
value, AND `uv run pytest tests/ -q -k config` exits 0 with `0 failed`.

## Task 5.7 — Register TradingView in the provider registry

**Goal.** `INDEX_FUTURE` symbols route to TradingView; crypto still routes to Binance.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py`: `InfrastructureProvider.get_data_provider`.
- `../pocketquant-config/*/`: `MARKET_DATA_PROVIDERS`.

**Steps.**
1. In `get_data_provider`, add `PROVIDER_TRADINGVIEW: TradingViewAdapter(...)` to the adapter
   dict, constructing the `TvDatafeedClient` from the settings added in Task 5.6.
2. Set `MARKET_DATA_PROVIDERS={"CRYPTO_SPOT":["binance"],"CRYPTO_PERP":["binance"],"INDEX_FUTURE":["tradingview"]}`
   in both env files in the config repository.
3. Do not add a fallback provider for `INDEX_FUTURE`; there is only one source today.
4. This is the whole of the "one adapter plus one config entry" claim in G4: no caller changes.

**Success criteria.** The container resolves and the crypto route is unchanged.

**Verify.** `uv run pytest tests/app_test -q` exits 0 with `0 failed`, AND
`git diff --stat src/pocketquant/engine/ src/pocketquant/app/routes/` produces no output for
this task.

## Task 5.8 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist as symbols and as
tracked symbols with the right calendar and contract spec.

**Target files and symbols.**
- New file `scripts/seed_index_futures_symbols.py`.
- `scripts/README.md`: one bullet.

**Steps.**
1. Follow the `scripts/README.md` conventions: read `MONGODB_URL` from the environment,
   dry-run by default, `--apply` required for writes.
2. Upsert three `Symbol` documents through `SymbolRepository.upsert`:
   - `ES1!:CME_MINI`, name "E-mini S&P 500 continuous", `asset_class=INDEX_FUTURE`,
     `calendar_id="CME_GLOBEX_EQUITY"`, `ContractSpec(multiplier=50.0, tick_size=0.25,
     lot_step=1.0, currency="USD")`;
   - `NQ1!:CME_MINI`, "E-mini Nasdaq-100 continuous", multiplier 20.0, tick 0.25, lot step 1.0;
   - `YM1!:CBOT_MINI`, "E-mini Dow continuous", multiplier 5.0, tick 1.0, lot step 1.0.
3. Upsert three `TrackedSymbol` documents with `seeded_from="index-futures-seed"` through
   `TrackedSymbolRepository.upsert`.
4. Print the three composite symbols and the resulting document counts.

**Success criteria.** Six documents exist after `--apply`.

**Verify.** After running the script with `--apply` against the dev database,
`curl -s ':41921/api/v1/market-data/symbols' | grep -c 'CME_MINI'` prints `2`, AND
`curl -s ':41921/api/v1/market-data/tracked-symbols' | grep -c '1!'` prints `3`.

## Task 5.9 — Backfill to the configured cap

**Goal.** Each futures symbol has history up to the bar cap for all seven intervals.

**Target files and symbols.**
- Existing endpoint `POST /api/v1/market-data/tracked-symbols/{symbol}/backfill`
  (`src/pocketquant/app/routes/tracked_symbols.py`), which already accepts
  `interval`, `n` (max 5000) and `mode`.

**Steps.**
1. For each of the three symbols and each of `1m, 5m, 15m, 1h, 4h, 1d, 1w`, call the backfill
   endpoint with `mode=direct` and `n=<tradingview_max_bars>`. Use `mode=direct`, not
   `cascade`: cascading futures 1d bars from 1m across UTC midnight would produce daily bars
   that never match the chart, and the advice forbids it even temporarily.
2. URL-encode `!` as `%21` and `:` as `%3A` in the path segment.
3. Send `X-Admin-Token` as required by the route.
4. Record the resulting bar counts per symbol and interval in
   `plans/260921-1436-asset-class-index-futures/reports/phase-05-backfill.md`.

**Success criteria.** Every symbol/interval pair has a non-zero bar count, and 1m equals
`min(tradingview_max_bars, available)`.

**Verify.** `curl -s ':41921/api/v1/market-data/sync-status/ES1%211%3ACME_MINI?interval=1m'`
returns JSON whose `bar_count` is greater than 1000 and whose `last_bar_at` ends with `Z`.

## Task 5.10 — Phase 5 gate and one-week observation

**Goal.** Futures history flows through the unchanged pipeline without anomalies.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run all four gates plus the timezone matrix.
2. Deploy, then observe for one full calendar week that includes a weekend.
3. Each day, grep the application log for `misaligned_bars_dropped`,
   `integrity.issues_found`, `no_progress`, `stuck_threshold_crossed` and `partial_aggregate`
   filtered to the three futures symbols.
4. Point the hourly `sync_verify_cascade` job at `ES1!:CME_MINI` for one full day and record
   the divergent fraction.
5. Record all counts in
   `plans/260921-1436-asset-class-index-futures/reports/phase-05-observation.md`.

**Success criteria.** G1 met during a session, zero anomaly events for ES across one week
including a weekend, and `sync_verify_cascade` on ES reports zero divergent bars.

**Verify.** All four gates exit 0 (`uv run ruff check src tests scripts`, `uv run pyright`,
`uv run lint-imports` printing `Contracts: 8 kept, 0 broken.`, `uv run pytest tests/ -q` with
`0 failed`), AND during a CME session
`curl -s ':41921/api/v1/market-data/ohlcv/ES1%211%3ACME_MINI/1m?limit=1'` returns a bar whose
`datetime` is within 2 minutes of now (within 12 minutes while `tradingview_delayed_data=true`),
AND the observation report records `0` for each of the five anomaly event names.

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

=== FILE: phase-06-realtime-quotes-and-contract-math.md ===
---
phase: 6
title: "Polling quotes, contract-aware broker and backtest"
status: pending
priority: P1
effort: "2d"
dependencies: [5]
---

# Phase 6: Polling quotes, contract-aware broker and backtest

Advice Phase 5. Add the realtime half of the TradingView provider and convert PnL from
`price x quantity` to `points x multiplier x contracts`. The futures margin accounting that
shipped in plan `260628-2013` (1x leverage, only close or reduce touches balance; see
`docs/journals/2026-06-28-paper-broker-futures-accounting.md`) stays exactly as it is — this
phase adds ONLY the unit conversion.

## Task 6.1 — Add `PerContractCommissionModel`

**Goal.** Futures commissions are charged per contract, not as a percentage of notional.

**Target files and symbols.**
- `src/pocketquant/core/domain/trading/commission_model.py` (currently holds the
  `CommissionModel` Protocol and `PercentageCommissionModel`).
- `src/pocketquant/core/domain/trading/__init__.py` `__all__`.
- `tests/core_test/unit/domain/trading/test_commission_model.py`.

**Steps.**
1. Add `class PerContractCommissionModel` with `__init__(self, usd_per_contract: float)` and
   `compute(self, price: float, quantity: float) -> float` returning
   `self._usd_per_contract * abs(quantity)`. The `price` argument is ignored; keep it so the
   class satisfies the existing `CommissionModel` Protocol.
2. Export it from `core/domain/trading/__init__.py`.
3. Add exactly 3 tests to the existing test file: 2 contracts at $2.50 equals 5.00; a short
   quantity of -2 also equals 5.00; the price argument does not change the result.

**Success criteria.** The new model satisfies `CommissionModel` structurally.

**Verify.** `uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q`
exits 0 with `0 failed` and a count at least 3 higher than before this task.

## Task 6.2 — Make `PositionAggregate` multiplier-aware

**Goal.** Realized and unrealized PnL are points times multiplier times contracts.

**Target files and symbols.**
- `src/pocketquant/core/domain/position/entities.py`: `PositionAggregate` fields (line 20-45),
  `open` (line 48), `reduce_quantity` (line 127, the `realized = pnl_per_unit * quantity` line
  around line 149), `unrealized_pnl` (line 224), `market_value` (line 234),
  `cost_basis` (line 238), `to_mongo` (line 246), `from_mongo` (line 265).

**Steps.**
1. Add the field `multiplier: float = 1.0` with a docstring line: contract multiplier in
   account currency per index point; 1.0 means linear price x quantity, which is the crypto
   default and preserves every existing number.
2. `_calculate_pnl_per_unit` stays unchanged — it returns POINTS.
3. Multiply by `self.multiplier` in exactly three places:
   `realized = pnl_per_unit * quantity * self.multiplier` in `reduce_quantity`;
   `return self._calculate_pnl_per_unit(self.current_price) * self.quantity * self.multiplier`
   in `unrealized_pnl`; and both `market_value` and `cost_basis`.
4. Add `multiplier` to `PositionAggregate.open(...)` with default `1.0`, to `to_mongo`, and to
   `from_mongo` with `doc.get("multiplier", 1.0)` so existing position documents load
   unchanged.
5. Do not change `entry_commission` proration or the `_close` path beyond what step 3 requires.

**Success criteria.** With `multiplier=1.0` every existing position test still passes; with
`multiplier=50.0` a 0.25-point move on 2 contracts yields 25.00.

**Verify.** `uv run pytest tests/core_test/unit/domain/position -q` exits 0 with `0 failed`,
AND a new `tests/core_test/unit/domain/position/test_position_multiplier.py` with exactly 4
tests (long realized 25.00; short realized 25.00; unrealized with multiplier; legacy document
defaults to 1.0) runs `uv run pytest
tests/core_test/unit/domain/position/test_position_multiplier.py -q` exiting 0 and printing
`4 passed`.

## Task 6.3 — Thread `ContractSpec` through `PaperBrokerAdapter`

**Goal.** Paper fills, affordability and equity use contract units.

**Target files and symbols.**
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`: `__init__` (line 108-143),
  `_can_afford` (line 487-500), `_open_position` (line 561-582), `get_balance` (line 418-426).
- `src/pocketquant/core/infra/brokers/broker_factory.py`: `BrokerFactory.create` paper branch
  (lines 32-43).
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py`: `create_broker`
  (line 111-130).

**Steps.**
1. Add `contract_spec: ContractSpec = LINEAR_SPEC` to `PaperBrokerAdapter.__init__` and store
   it. The default keeps every existing behaviour.
2. In `_can_afford`, change `fill_price * order.quantity + commission <= self._balance` to
   `fill_price * order.quantity * self._contract_spec.multiplier + commission <= self._balance`.
3. In `_open_position`, pass `multiplier=self._contract_spec.multiplier` into
   `PositionAggregate.open(...)`.
4. `get_balance` already sums `p.unrealized_pnl`, which becomes multiplier-aware through Task
   6.2 — do not add a second multiplication there.
5. In `BrokerFactory.create`, read an optional `contract_spec` from the config dict and select
   the commission model: `PerContractCommissionModel(spec.commission_per_contract)` when that
   field is set, otherwise the existing `PercentageCommissionModel(bps=commission_bps)`.
6. In `BacktestSandboxAppService.create_broker`, add a `contract_spec: ContractSpec = LINEAR_SPEC`
   parameter and forward it, applying the same commission-model selection.
7. Change nothing about which events debit the balance. The margin model from plan `260628-2013`
   is out of scope.

**Success criteria.** Existing paper-broker tests pass unchanged; an ES spec yields
multiplier-scaled equity.

**Verify.** `uv run pytest tests/core_test/infra/brokers -q` exits 0 with `0 failed`.

## Task 6.4 — Make position sizing contract-aware

**Goal.** Sizing risks the right dollar amount and returns whole contracts.

**Target files and symbols.**
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py`:
  `PositionCalculatorDomainService.calculate` (lines 17-45).

**Steps.**
1. Add a `contract_spec: ContractSpec = LINEAR_SPEC` keyword parameter after
   `commission_model`.
2. `price_risk` stays in POINTS. Convert to money per contract:
   `risk_per_contract = price_risk * contract_spec.multiplier`.
3. Change `cap = (account_balance * max_exposure) / entry_price` to
   `cap = (account_balance * max_exposure) / (entry_price * contract_spec.multiplier)`.
4. `size = min(risk_amount / risk_per_contract, cap)` as before.
5. When `contract_spec.lot_step` is not None, floor `size` to a whole multiple of it
   (`math.floor(size / lot_step) * lot_step`). This is what makes contracts integral. When it
   is None, leave the fractional size alone, preserving crypto behaviour exactly.
6. `notional = size * entry_price * contract_spec.multiplier`.

**Success criteria.** With `LINEAR_SPEC` every existing sizing number is unchanged; with the ES
spec the size is an integer.

**Verify.** A new `tests/core_test/unit/domain/risk/test_position_calculator_contract_spec.py`
with exactly 4 tests (linear default matches the pre-change result for a fixed input; ES spec
produces an integer size; ES spec caps by multiplier-scaled notional; a sub-one-contract risk
budget produces size 0) runs `uv run pytest
tests/core_test/unit/domain/risk/test_position_calculator_contract_spec.py -q` exiting 0 and
printing `4 passed`, AND `uv run pytest tests/core_test tests/engine_test -q` exits 0 with
`0 failed`.

## Task 6.5 — Thread the contract spec and calendar through backtests

**Goal.** A futures backtest reports dollar PnL and calendar-derived Sharpe.

**Target files and symbols.**
- `src/pocketquant/core/domain/backtest/config.py`: `BacktestConfig` (fields at lines 26-36).
- `src/pocketquant/engine/backtest/backtest_dispatch.py`: `_config_from_dict` (lines 47-55)
  and `run_single`'s `sandbox.create_broker(...)` call (lines 92-96).
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py:106`
  (`sandbox.create_broker(initial_balance=initial_capital)`).
- `src/pocketquant/engine/backtest/backtest_report_app_service.py:368` (already changed in
  Phase 3 Task 3.6 to read the calendar).

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` to `BacktestConfig` and include it in
   `_config_from_dict` (deserialise with `ContractSpec.from_dict` when the payload carries it).
2. In `run_single`, before creating the broker, resolve the symbol's `Symbol` record via
   `SymbolRepository.find_by_symbol` and use its `contract_spec`, falling back to
   `LINEAR_SPEC`. Pass it into `sandbox.create_broker(...)`.
3. Do the same at `backtest_strategy_loader.py:106`.
4. Confirm that `BacktestReportAppService` receives the CME calendar for an ES run and
   therefore annualizes on roughly 252 sessions rather than 365 days.
5. Do not change `BacktestConfig.slippage_percent` or the commission bps fields; a futures run
   simply carries a spec whose `commission_per_contract` is set.

**Success criteria.** An ES backtest reports dollar PnL consistent with the multiplier and a
Sharpe computed from the CME calendar.

**Verify.** A new `tests/backtest_test/engine/test_es_contract_backtest.py` with exactly 3
tests (a 2-contract ES round trip from 4500.00 to 4500.25 reports realized PnL 25.00 minus
commission; `periods_per_year` for a 1h ES run is between 5000 and 6200 and is not 8760; a
BTC run still reports 8760) runs
`uv run pytest tests/backtest_test/engine/test_es_contract_backtest.py -q` exiting 0 and
printing `3 passed`.

## Task 6.6 — Implement the polling `TradingViewQuoteAdapter`

**Goal.** Futures symbols produce realtime quotes through the existing quote contract.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_quote_adapter.py`:
  `class TradingViewQuoteAdapter`.
- `src/pocketquant/app/di/market_data.py`: `MarketDataProvider.get_realtime_quote_provider`.

**Steps.**
1. The class must satisfy the 9-member `IRealtimeQuoteProviderPort` Protocol exactly as
   `BinanceWebSocketAdapter` does: the `last_tick_at` attribute plus `connect`, `disconnect`,
   `subscribe`, `unsubscribe`, `run_forever`, `is_connected`, `subscription_count` and
   `subscriptions`.
2. Constructor takes `client: ITradingViewClient`, `settings: Settings` and
   `calendar_resolver: SymbolCalendarResolver`.
3. `subscribe(symbol, callback)` records `{composite: (code, callback)}` in `_subscriptions`
   and returns the composite key, matching `BinanceWebSocketAdapter.subscribe`.
4. `run_forever` runs one polling task per subscribed symbol at
   `settings.tradingview_poll_seconds`. Each iteration: skip entirely when
   `not calendar.is_open(datetime.now(UTC))`; otherwise fetch the latest 1m bar through the
   client and, when its close differs from the last emitted close, invoke the callback with the
   same quote dict contract Binance uses (`binance_mappers.aggtrade_to_quote_dict` is the
   reference): keys `symbol`, `timestamp` (tz-aware UTC), `last_price`, `volume`, and `bid`,
   `ask`, `change`, `change_percent`, `open_price`, `high_price`, `low_price`, `prev_close` all
   set to `None`. Set `self.last_tick_at = datetime.now(UTC)` on each emission.
5. `volume` must be a per-poll DELTA, not a cumulative session total — `BarBuilderDomainService.add_tick`
   sums whatever it receives. Emit the difference between successive bar volumes for the same
   bar, and the raw bar volume when the bar has just rolled.
6. `is_connected()` returns `client.is_authenticated() and self._polling`.
7. Log per-poll activity at DEBUG only; one INFO on start and stop.
8. Register the adapter in `get_realtime_quote_provider`'s dict under
   `PROVIDER_TRADINGVIEW`. The `RoutingQuoteProviderAdapter` from Phase 4 does the per-symbol
   dispatch; do not add any symbol branching here.
9. Because this provider emits at most once per poll interval, the 30-second staleness
   watchdog thresholds used for the Binance WS feed do not apply. Document that in the class
   docstring and make the watchdog threshold for this provider
   `max(90, 3 * settings.tradingview_poll_seconds)` seconds.

**Success criteria.** The adapter satisfies the Protocol, is session-gated, and emits the
documented quote-dict shape.

**Verify.** A new `tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py` with
exactly 6 tests (runtime Protocol isinstance check; no emission while the calendar is closed;
emission on a close change; no emission when the close is unchanged; the quote dict has exactly
the 12 Binance keys; volume is emitted as a delta) runs
`uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q` exiting
0 and printing `6 passed`.

## Task 6.7 — Phase 6 gate and live session run

**Goal.** G2 and G3 are demonstrated.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run all four gates plus the timezone matrix.
2. Deploy, then run a paper ES strategy for one full CME session.
3. Run a 1h ES backtest over the accumulated window.
4. Record the realized PnL, the equity curve shape at fill time, the reported Sharpe and the
   `periods_per_year` used in
   `plans/260921-1436-asset-class-index-futures/reports/phase-06-g2-g3.md`.

**Success criteria.** G2: a one-round-trip ES paper trade of 2 contracts entering 4500.00 and
exiting 4500.25 records realized PnL of 25.00 USD minus per-contract commission, and the equity
curve has no jump at fill time other than commission. G3: the 1h ES backtest annualizes on the
CME calendar and reports dollar PnL equal to points times 50 times contracts.

**Verify.** All four gates exit 0 (`uv run ruff check src tests scripts`, `uv run pyright`,
`uv run lint-imports` printing `Contracts: 8 kept, 0 broken.`, `uv run pytest tests/ -q` with
`0 failed`), AND the G2/G3 report records a realized PnL of `25.00` before commission and a
`periods_per_year` value that is not `8760`.

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

=== FILE: phase-07-ui-docs-and-success-metrics.md ===
---
phase: 7
title: "UI, documentation and success-metric run-through"
status: pending
priority: P2
effort: "1d"
dependencies: [6]
---

# Phase 7: UI, documentation and success-metric run-through

Advice Phase 6. Make the SPA venue-neutral, surface the closed-market state, expose provider
health, update the documents that describe user-visible behaviour, and record the success
metrics.

## Task 7.1 — Replace Binance-only placeholders in the SPA

**Goal.** The UI no longer implies one venue.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx` lines 21, 23, 24 and the `placeholder`
  at line 72.
- `web/src/components/backtest/backtest-form.tsx` line 44 (`useState('BTCUSDT:BINANCE')`) and
  the error message at line 72.
- `web/src/routes/index.tsx` line 21 and `web/src/routes/__root.tsx` line 17 (the default
  `symbol` search param).
- Doc-comment occurrences in `web/src/components/ticker-widget/ticker-widget.tsx:6`,
  `web/src/lib/symbol-format.ts:2`, `web/src/components/controls/symbol-selector.tsx:6`,
  `web/src/hooks/use-ohlcv.ts:13`, `web/src/api/backtest-api.ts:284`,
  `web/src/components/chart/trading-chart.tsx:38`, `web/src/types/market-data.ts:20`,
  `web/src/hooks/use-available-intervals.ts:29`, `web/src/hooks/use-realtime-quote.ts:49`,
  `web/src/routes/index.tsx:12,57`, `web/src/types/quote.ts:3`,
  `web/src/api/strategy-api.ts:11`, `web/src/api/market-data-api.ts:42`.

**Steps.**
1. In the two user-visible placeholders and the two error messages, replace
   `e.g. BTCUSDT:BINANCE` with `e.g. BTCUSDT:BINANCE or ES1!:CME_MINI`.
2. Leave the default selected symbol in `index.tsx` and `__root.tsx` as `BTCUSDT:BINANCE`;
   changing the landing symbol is not in scope and would surprise existing users.
3. In the doc comments listed above, change the format example to
   `"{CODE}:{EXCHANGE}" e.g. "BTCUSDT:BINANCE" or "ES1!:CME_MINI"`. These are comments only;
   change no logic.
4. No web-side symbol regex exists (verified), and `parseSymbol` already splits on the first
   `:`, so the exchange badge renders `CME_MINI` and `CBOT_MINI` with no change.

**Success criteria.** The build succeeds and the futures example appears in both dialogs.

**Verify.** `cd web && npm run build` exits 0, AND
`grep -rc "ES1!:CME_MINI" web/src/components/strategy/add-symbol-dialog.tsx
web/src/components/backtest/backtest-form.tsx` prints a count of at least 1 for each file.

## Task 7.2 — Show a "closed" state instead of "stuck"

**Goal.** A closed market reads as closed, not as a data failure.

**Target files and symbols.**
- `web/src/types/market-data.ts`, the `SyncStatus` interface (lines 81-91).
- `web/src/lib/datetime.ts`, `ageColorClass` (lines 88-97).
- `web/src/components/monitor/data-health-row.tsx`, `statusLabel` (lines 47-53),
  `statusTitle` (lines 54-56) and the `ageColorClass` call (line 68).
- `web/src/components/monitor/format-helpers.ts`, `statusVariant` (line 19).

**Steps.**
1. Add `is_market_open?: boolean` to the `SyncStatus` interface. The backend already emits it
   (Phase 3, Task 3.5).
2. Change `ageColorClass(lastBarAt, interval, isMarketOpen = true)` to return `'age-neutral'`
   immediately when `isMarketOpen === false`. Update the single call site in
   `data-health-row.tsx:68` to pass `s.is_market_open`.
3. In `data-health-row.tsx`, when `s.is_market_open === false` set `statusLabel` to `'closed'`
   and `statusTitle` to "Market is closed on this symbol's trading calendar. Sync resumes at
   the next session open." Keep the existing stuck labelling for open markets.
4. In `format-helpers.statusVariant`, return the neutral variant when `is_market_open` is
   false, before the `is_stuck` check.
5. Do not hide the row; the user still wants bar counts and last-bar times while closed.

**Success criteria.** A closed futures symbol renders a neutral "closed" pill and a neutral age
colour.

**Verify.** `cd web && npm run build` exits 0, AND
`grep -c "is_market_open" web/src/types/market-data.ts web/src/lib/datetime.ts
web/src/components/monitor/data-health-row.tsx web/src/components/monitor/format-helpers.ts`
prints a non-zero count for each of the four files.

## Task 7.3 — Expose provider status on `/health`

**Goal.** "Why are there no ES bars" is a glance, not a log hunt.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py`, `register_health_checks` (lines 267-271) — it
  currently registers `database` and `redis` on the `HealthCoordinator`.
- `src/pocketquant/core/infra/market_data/routing_data_provider_adapter.py`: a new
  `async def health(self) -> dict` method.

**Steps.**
1. Add `RoutingDataProviderAdapter.health()` returning a dict with, per registered provider id:
   `authenticated` (True for Binance, `client.is_authenticated()` for TradingView), and
   `last_success_at` as an ISO string via `to_utc_iso` (track it in `fetch_ohlcv`).
2. Add a `check_market_data_providers(provider)` function next to the existing
   `check_database` / `check_redis` in
   `src/pocketquant/core/infra/persistence/health_checks.py` that calls `health()` and returns
   the coordinator's expected shape.
3. Register it in `register_health_checks` under the name `market_data_providers`.
4. Keep the payload small; `/health` is polled by the Docker healthcheck every 30 seconds, so
   it must never enumerate symbols or bars.

**Success criteria.** `/health` includes a `market_data_providers` section naming each
registered provider.

**Verify.** `curl -s :41921/health | grep -c 'market_data_providers'` prints `1`.

## Task 7.4 — Update the documentation

**Goal.** The docs describe the asset-class model, the provider table and the new settings.

**Target files and symbols.**
- `docs/system-architecture.md`: the "Layer 4: Adapters" structure block (from line 278), the
  "Where Does X Live?" table (from line 479), the "Dependency Injection (Dishka)" providers
  paragraph (line 674) and the "PaperBrokerAdapter accounting model" section (line 643).
- `README.md`: the settings mention added in Phase 4 Task 4.1 and Phase 5 Task 5.6.
- `docs/code-standards.md`: already updated in Phase 2 Task 2.11 — do not touch again.

**Steps.**
1. In the Layer 4 structure block, add `core/infra/calendars/`, `core/infra/market_data/` and
   `core/infra/tradingview/` with a one-line purpose each.
2. Add four rows to "Where Does X Live?": trading calendars (`core/infra/calendars/`),
   provider routing (`core/infra/market_data/`), TradingView adapters
   (`core/infra/tradingview/`), and the calendar port plus asset-class enum
   (`core/domain/market_data/trading_calendar_port.py`, `core/domain/shared/enums.py`).
3. Update the DI providers paragraph to say that both market-data ports now resolve to routing
   adapters keyed by asset class, and that adding a provider is one adapter plus one config
   entry.
4. Add three sentences to the PaperBroker accounting section: the margin model is unchanged;
   PnL is now points times `ContractSpec.multiplier` times contracts; `LINEAR_SPEC` with
   multiplier 1.0 reproduces the prior crypto arithmetic exactly.
5. Verify every claim you write against the source before writing it. Do not restate the plan.

**Success criteria.** Each of the three new packages appears in the architecture document.

**Verify.** `grep -c "core/infra/calendars\|core/infra/tradingview\|core/infra/market_data"
docs/system-architecture.md` prints at least `6`.

## Task 7.5 — Prove G4 and G5 end to end

**Goal.** Provider extensibility and crypto non-regression are demonstrated, not assumed.

**Target files and symbols.** None beyond the tests written in Phase 4 Task 4.6.

**Steps.**
1. G4: re-run the config-only third-provider test from Phase 4 and capture
   `git diff --stat` for the commit that introduced it, confirming it touched no file under
   `engine/` or `app/`.
2. G5: over one full cron cycle on the VPS, compare `synced_count` and the latest bar values
   for `BTCUSDT:BINANCE`, `ETHUSDT:BINANCE` and `SOLUSDT:BINANCE` against the Phase 3 parity
   record, and confirm `periods_per_year` for crypto 1m is still 525600.
3. Record both in
   `plans/260921-1436-asset-class-index-futures/reports/phase-07-g4-g5.md`.

**Success criteria.** G4 and G5 both hold.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_provider_registration_g4.py -q`
exits 0 printing `2 passed`, AND `uv run python -c "from
pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar;
from pocketquant.core.domain.shared.enums import Interval;
print(Continuous24x7Calendar().periods_per_year(Interval.MINUTE_1))"` exits 0 and prints
`525600`.

## Task 7.6 — Record the success metrics

**Goal.** The 18 success metrics from the advice have recorded numbers.

**Target files and symbols.**
- New file
  `plans/260921-1436-asset-class-index-futures/reports/completion-success-metrics.md`.

**Steps.**
1. Walk section 9 of `plans/reports/advise-260921-2001-index-futures-data-provider.md` and
   record the observed value for every metric, citing where it was measured (test name,
   endpoint, or log query).
2. For any metric that cannot be measured yet (for example a metric that needs a holiday
   early-close that has not occurred), state that explicitly with the earliest date it can be
   measured. Do not mark it pass.
3. Include the secrets check: `git grep -i "tradingview_.*=" -- ':!*.md'` must find only
   settings field declarations.

**Success criteria.** Every metric has either a recorded number or a stated, dated deferral.

**Verify.** The file exists and
`grep -c "^- " plans/260921-1436-asset-class-index-futures/reports/completion-success-metrics.md`
prints at least `18`.

## Task 7.7 — Phase 7 gate

**Goal.** The whole plan is green.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run every gate one final time, including the web build and the timezone matrix.
2. Confirm `plan.md` phase statuses are updated through the plan CLI, not by editing status
   cells directly. Run `ak plan --help` first and follow the current CLI contract.

**Success criteria.** Every gate passes.

**Verify.** All of the following exit 0: `uv run ruff check src tests scripts`,
`uv run pyright`, `uv run lint-imports` (prints `Contracts: 8 kept, 0 broken.`),
`uv run pytest tests/ -q` (`0 failed`), `just test-tz`, and `cd web && npm run build`.

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
