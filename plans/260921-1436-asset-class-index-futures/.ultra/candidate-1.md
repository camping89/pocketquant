=== FILE: plan.md ===
---
title: "Asset-class index futures (ES/NQ/YM) via TradingView"
description: "Generalize the crypto-only pipeline with an asset class, a trading-calendar port and provider routing, then add CME index futures through TradingView."
status: pending
priority: P1
effort: "86h"
branch: develop
tags: [market-data, timezone, calendar, provider-routing, futures, tradingview]
created: 2026-09-21
blockedBy: []
blocks: []
---

# Asset-class index futures (ES/NQ/YM) via TradingView

## Overview

PocketQuant is hardwired to one 24/7 crypto venue. Dishka binds exactly one
`IDataProviderPort` and one `IRealtimeQuoteProviderPort`, and the sync cron,
cascade aggregator, integrity grid, freshness checks, annualization table and
paper broker all assume continuous trading and price-times-quantity units. This
plan adds `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` to the **existing**
pipeline by turning every one of those assumptions into a parameter: an
`AssetClass` enum plus a persisted `calendar_id` and `ContractSpec` on the symbol
record, a `ITradingCalendarPort` whose 24/7 implementation reproduces today's
crypto numbers exactly, and provider resolution keyed by asset class. No parallel
futures pipeline is built.

The order is chosen to retire risk on the crypto path first. The UTC invariant
and the routing layer are both provable against BTC/ETH/SOL before a single
futures bar exists, so the two hardest failure classes (timezone drift and
provider mis-routing) are eliminated before the scraper's own flakiness enters.

**Phase numbering note.** The source advice
(`plans/reports/advise-260921-2001-index-futures-data-provider.md`) numbers its
route Phase 0 through Phase 6. This plan maps advice Phase 0 to plan Phase 1,
advice Phase 1 to plan Phase 2, and so on through advice Phase 6 to plan
Phase 7. Where a phase file says "advice Phase N" it means the source document.

## Phases

| # | Phase | Depends on | Effort | Status |
|---|-------|-----------|--------|--------|
| 1 | [UTC invariant and the two live crypto bugs](./phase-01-utc-invariant-and-crypto-bugfixes.md) | — | 12h | Pending |
| 2 | [Trading-calendar port and asset-class domain model](./phase-02-calendar-port-and-asset-class-model.md) | 1 | 14h | Pending |
| 3 | [Thread the calendar through the pipeline (24/7 only)](./phase-03-thread-calendar-through-pipeline.md) | 2 | 16h | Pending |
| 4 | [Provider routing adapters and settings](./phase-04-provider-routing-and-settings.md) | 3 | 8h | Pending |
| 5 | [TradingView history adapter, seeding and backfill](./phase-05-tradingview-history-and-backfill.md) | 4 | 16h | Pending |
| 6 | [Realtime quotes and contract-aware trading math](./phase-06-realtime-quotes-and-contract-math.md) | 5 | 12h | Pending |
| 7 | [UI, docs and success-metric run-through](./phase-07-ui-docs-and-metric-runthrough.md) | 6 | 8h | Pending |

Phases are strictly sequential. Each one leaves the system shippable, and phases
1, 3 and 4 are provable against crypto alone.

## Goals

| # | Goal | Phase |
|---|------|-------|
| G1 | Fresh futures bars land within one cron cycle during CME session hours | 5 |
| G2 | A paper ES strategy runs a full session with correct USD PnL | 6 |
| G3 | A 1h ES backtest reports dollar PnL and Sharpe consistent with the contract spec | 6 |
| G4 | Adding a provider is one adapter plus one config entry, zero caller edits | 4 |
| G5 | BTC/ETH/SOL behaviour and tests are unchanged | 3, 7 |
| G6 | The app refuses to start on a non-UTC host; the DST-boundary suite passes | 1, 2 |

## Success Criteria

- [ ] `TZ=Asia/Saigon` startup raises `RuntimeError`; `TZ=UTC` starts (test-reproduced)
- [ ] Every registered cron job reports the same `next_run_time` under three host zones
- [ ] `uv run ruff check src tests` passes with `DTZ` enabled
- [ ] `uv run pytest tests/ -q` reports 0 failed; test count at or above the 669-test baseline
- [ ] `uv run lint-imports` reports `Contracts: 8 kept, 0 broken.`
- [ ] `uv run pyright src` reports `0 errors`
- [ ] Golden-file test proves crypto bars, cascade output and metrics byte-identical across Phase 3
- [ ] `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and `session_open(2026-11-02) == 2026-11-01T23:00:00Z`
- [ ] Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`, `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across one full week
- [ ] ES round trip of 2 contracts 4500.00 to 4500.25 records realized PnL 25.00 USD minus commission
- [ ] A mock third provider registered through config alone receives fetches, with no diff under `engine/` or `app/`

## Non-Goals

A real futures broker; multi-year 1m futures history (deferred, accepted);
Databento or IBKR adapters; tick fidelity beyond the scraper; contract-roll
modelling inside paper positions; redoing the margin accounting shipped in plan
`260628-2013`; any branching on TradingView plan tier.

## Standing Constraints

Single uvicorn worker. Ports in `core/domain`, adapters in `core/infra`, all
repositories in `core.infra.persistence.repositories`. `fastapi` only in `app`
(import-linter, 8 contracts). Routes use `FromDishka[...]` with `DishkaRoute`,
never `Depends()`. UUIDv7 primary keys only. Composite symbol `{CODE}:{EXCHANGE}`.
Credentials only in `../pocketquant-config/`, never in this repo. Log level is
frequency plus audience: DEBUG for per-bar and per-tick, INFO for one-shot
lifecycle and per-trade, never unbounded payloads above DEBUG.

<!-- slug: asset-class-index-futures -->

=== FILE: phase-01-utc-invariant-and-crypto-bugfixes.md ===
---
phase: 1
title: "UTC invariant and the two live crypto bugs"
status: pending
priority: P1
effort: "12h"
dependencies: []
---

# Phase 1: UTC invariant and the two live crypto bugs

Maps to advice Phase 0.

## Context

The pipeline is UTC by convention, not by construction. Two bugs are live on
crypto today and are independent of futures:

- `core/infra/scheduling/scheduler.py:79` sets `timezone="UTC"` on the scheduler,
  but `:219` and `:228` build `CronTrigger(...)` with no `timezone=` and pass the
  prebuilt trigger to `add_job` at `:245`. APScheduler 3.11.2 falls back to
  `tzlocal.get_localzone()` and pickles the host zone into the Mongo jobstore.
  Affects `sync_backfill hour=3`, `sync_integrity hour=4`, `sync_repair "0 */12"`
  and `sync_verify_cascade "0 * * * *"` (registered at `sync_jobs.py:691-724`).
- `core/infra/binance/binance_adapter.py:80-83` floors `now` to the 604800000 ms
  epoch week, which is Thursday-aligned, so from Thursday to Sunday the
  in-progress Monday-open weekly kline passes the `< cutoff_dt` guard at `:108`
  and is persisted partial.

**HARD ORDERING CONSTRAINT.** Task 2 must land as ONE commit. `integrity_jobs.py:50`
is deliberately naive (`datetime.now(UTC).replace(tzinfo=None)`) so that its
`expected` set compares with the naive datetimes `bar_repository.find_datetimes`
returns, because the Mongo client is not `tz_aware`. Flipping `tz_aware=True`
alone makes the integrity check report every bar missing and triggers a full
resync of every symbol on the next `sync_repair` run.

## Baselines measured on 2026-09-21 (develop)

- `uv run pytest tests/ -q` -> `668 passed, 1 skipped`
- `uv run ruff check src tests` -> `All checks passed!`
- `uv run lint-imports` -> `Contracts: 8 kept, 0 broken.`
- `uv run pyright src` -> `0 errors, 0 warnings, 0 informations`
- `uv run ruff check src --select DTZ --no-cache` -> `Found 3 errors.`
- `uv run ruff check tests --select DTZ --no-cache` -> `Found 28 errors.`

## Tasks

### Task 1.1 — Add the UTC boundary helpers

**Goal.** `require_utc()` exists and raises on any naive or non-UTC datetime, so
adapter and calendar boundaries have one guard to call.

**Target files and symbols.**
- `src/pocketquant/core/common/time/__init__.py` — add `require_utc`, extend `__all__`

**Steps.**
1. In `core/common/time/__init__.py`, after `coerce_utc` (currently lines 17-23), add:
   `def require_utc(value: datetime, *, field: str = "datetime") -> datetime:` which
   raises `ValueError(f"{field} must be a timezone-aware UTC datetime, got {value!r}")`
   when `value.tzinfo is None`, and otherwise returns `value.astimezone(UTC)`.
2. Add a one-line docstring saying this is the strict counterpart to `coerce_utc`:
   `coerce_utc` silently attaches UTC to naive values and stays for `from_mongo`
   back-compatibility; `require_utc` rejects them at ingress boundaries.
3. Append `"require_utc"` to the `__all__` list at line 33.

**Success criteria.** `from pocketquant.core.common.time import require_utc` imports;
naive input raises `ValueError`; an `America/Chicago`-aware input returns the same
instant with `tzinfo=UTC`.

**Verify.** `uv run python -c "from datetime import datetime; from zoneinfo import ZoneInfo; from pocketquant.core.common.time import require_utc; print(require_utc(datetime(2026,3,8,17,tzinfo=ZoneInfo('America/Chicago'))).isoformat())"`
prints exactly `2026-03-08T22:00:00+00:00` and exits 0.

### Task 1.2 — ONE COMMIT: tz-aware Mongo client, aware integrity grid, delete the naive epoch branch

**Goal.** Mongo reads return aware UTC datetimes and the integrity grid compares
aware to aware, with no window in which the two disagree.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/mongodb.py` — `Database.connect`, the `AsyncMongoClient(...)` call at lines 44-49
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` — line 50 `now = datetime.now(UTC).replace(tzinfo=None)`
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` — line 24 naive epoch branch
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py` — comment at lines 54-55

**Steps.**
1. In `mongodb.py`, change the `AsyncMongoClient(...)` call to add `tz_aware=True,`
   and `tzinfo=UTC,` after `serverSelectionTimeoutMS=5000,`. Import `UTC` from
   `datetime` at the top of the file if it is not already imported.
2. In `integrity_jobs.py`, change line 50 to `now = datetime.now(UTC)` (remove the
   `.replace(tzinfo=None)` call entirely).
3. In `bar_builder_domain_service.py`, replace line 24
   `epoch = datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`
   with `epoch = datetime(1970, 1, 1, tzinfo=UTC)`.
4. In `bar_filters.py`, replace the two-line comment at 54-55 ("Mongo client is not
   tz_aware; raw projection returns naive datetimes. / Coerce both sides ...") with
   a single line stating that the Mongo client is `tz_aware=True` and `coerce_utc`
   remains as a defensive no-op for documents written before the flip. Leave the
   `coerce_utc` calls at lines 56 and 59 in place.
5. Commit all four files together with one message. Do not commit any of them
   separately.

**Success criteria.** `Bar.from_mongo` round-trips aware UTC; `check_integrity`
returns `missing_count` values consistent with pre-change behaviour for a dense
crypto series; no file from this task is left uncommitted.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py tests/app_test/market_data/test_sync_source_labels.py tests/core_test/unit/domain/bar/services/test_bar_builder.py -q`
exits 0 and reports `0 failed`. Then `git show --stat HEAD` lists exactly these
four paths: `mongodb.py`, `integrity_jobs.py`, `bar_builder_domain_service.py`,
`bar_filters.py`.

### Task 1.3 — Reject naive datetimes on the Bar entity and normalise the API DTOs

**Goal.** No naive datetime crosses the adapter or route boundary, and the four
documented serialisation sites emit `to_utc_iso()` output.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar.datetime` (line 35), `Bar.to_dict` (line 104)
- `src/pocketquant/engine/market_data/ohlcv_service.py` — `GetOHLCVQuery` (line 14), line 66 `.isoformat()`
- `src/pocketquant/engine/backtest/backtest_command_service.py` — `RunBacktestCommand` (line 22), lines 74-75
- `src/pocketquant/engine/backtest/backtest_report_app_service.py` — lines 396-397
- `src/pocketquant/engine/market_data/sync_status_service.py` — `_iso_z` (lines 72-73)

**Steps.**
1. In `bar/entities.py`, add a `@field_validator("datetime", "created_at", "updated_at", mode="before")`
   classmethod named `_normalise_utc` that returns `None` for `None`, raises
   `ValueError("Bar datetime must be timezone-aware; adapters must not emit naive datetimes")`
   for a naive `datetime`, and otherwise returns `value.astimezone(UTC)`. Import
   `field_validator` from `pydantic` and `UTC` from `datetime`.
2. Because `from_mongo` already calls `coerce_utc` (lines 87, 94-96), it feeds the
   validator aware values and is unaffected. Do not change `from_mongo`.
3. In `bar/entities.py` line 104, replace `self.datetime.isoformat() if self.datetime else None`
   with `to_utc_iso(self.datetime)`; do the same for `updated_at` at line 111.
   Add `to_utc_iso` to the existing `from pocketquant.core.common.time import ...` line.
4. In `ohlcv_service.py`, add a `__post_init__` to the `GetOHLCVQuery` dataclass that
   assigns `self.start_date = coerce_utc(self.start_date)` and the same for
   `self.end_date`. Import `coerce_utc`. Replace line 66's `.isoformat()` with
   `to_utc_iso(bar.datetime)`. Leave the cache-key `isoformat()` calls at lines 84
   and 86 alone — they are cache keys, not API output.
5. In `backtest_command_service.py`, add
   `@field_validator("start_date", "end_date", mode="after")` to `RunBacktestCommand`
   that returns `coerce_utc(v)`. Replace the two `.isoformat()` calls at lines 74-75
   with `to_utc_iso(...)`.
6. In `backtest_report_app_service.py`, replace the two `.isoformat()` calls at
   lines 396-397 with `to_utc_iso(...)`.
7. In `sync_status_service.py`, replace the body of `_iso_z` with `return to_utc_iso(dt)`
   and delete the now-unused `.replace("+00:00", "Z")` hand-roll. Keep the function
   name so its two call sites at lines 130-131 are untouched.
8. Add `tests/core_test/unit/domain/bar/test_bar_rejects_naive_datetime.py` with two
   tests: constructing `Bar(datetime=datetime(2026, 1, 1))` raises `ValidationError`,
   and `Bar(datetime=datetime(2026,3,8,17,tzinfo=ZoneInfo("America/Chicago"))).datetime`
   equals `datetime(2026,3,8,22,tzinfo=UTC)`.

**Success criteria.** A naive `Bar.datetime` is impossible to construct; the four
`.isoformat()` API sites named in `docs/code-standards.md:777` now use `to_utc_iso()`.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar/ tests/engine_test/market_data/test_ohlcv_service.py tests/backtest_test/ -q`
exits 0 with `0 failed`, and `uv run pytest tests/core_test/unit/domain/bar/test_bar_rejects_naive_datetime.py -q`
prints `2 passed`.

### Task 1.4 — Enable ruff DTZ and clear the remaining src findings

**Goal.** Naive datetime construction is a lint error in `src`, and `src` is clean.

**Target files and symbols.**
- `pyproject.toml` — `[tool.ruff.lint] select` (currently `["E", "F", "I", "N", "W", "UP", "TID"]`), new `[tool.ruff.lint.per-file-ignores]`
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py:37` — `date.today()`
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:81` — `datetime.min`

**Steps.**
1. In `pyproject.toml`, change `select` to `["E", "F", "I", "N", "W", "UP", "TID", "DTZ"]`.
2. Add immediately below it:
   ```toml
   [tool.ruff.lint.per-file-ignores]
   # Test fixtures pin fixed naive instants on purpose, and
   # test_mongo_datetime_normalization.py asserts the naive-to-UTC coercion path.
   # The invariant that matters is that src/ never constructs a naive datetime.
   "tests/**" = ["DTZ001", "DTZ901"]
   ```
3. In `backtest_strategy_loader.py:37`, replace `today = date.today()` with
   `today = datetime.now(UTC).date()`. `datetime` is already imported at that
   module's top; add `UTC` to that import. Remove `date` from the import line only
   if no other reference remains (`date` is still used in type hints at lines 41-46
   and 22-23 — check before removing).
4. In `cascade_aggregator.py:81`, replace `datetime.min` with
   `datetime.min.replace(tzinfo=UTC)` inside the `sorted(...)` key lambda. `UTC` is
   already imported at line 19.
5. Task 1.2 already removed the third finding at `bar_builder_domain_service.py:24`.

**Success criteria.** `DTZ` is active repo-wide; zero DTZ findings remain under `src`.

**Verify.** `uv run ruff check src --select DTZ --no-cache` prints `All checks passed!`
and exits 0. `uv run ruff check src tests` prints `All checks passed!` and exits 0.

### Task 1.5 — Pass `timezone=UTC` to both CronTrigger constructors

**Goal.** Cron firing times are host-zone independent and no host zone is pickled
into the Mongo jobstore.

**Target files and symbols.**
- `src/pocketquant/core/infra/scheduling/scheduler.py` — `CronTrigger(` at line 219 and line 228
- `tests/core_test/infra/scheduling/test_scheduler_cron_timezone.py` (new)

**Steps.**
1. Import `UTC` from `datetime` at the top of `scheduler.py` if absent.
2. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call
   starting at line 219 (the `cron_expression` branch).
3. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call
   starting at line 228 (the `hour`/`minute`/`second`/`day_of_week` branch).
4. Add a load-bearing comment above the first one: passing a prebuilt trigger to
   `add_job` bypasses the scheduler's own `timezone="UTC"` (line 79), so APScheduler
   would otherwise resolve the zone through `tzlocal` and persist it in the jobstore.
5. Create `tests/core_test/infra/scheduling/test_scheduler_cron_timezone.py` with a
   test that constructs `JobScheduler(history_repo=None)`, calls `initialize(settings)`
   with a settings stub, registers one cron job through `add_cron_job` for each
   branch (one with `cron_expression="0 */12 * * *"`, one with `hour=3, minute=0`),
   and asserts `job.trigger.timezone` equals `UTC` for both. Mirror the fixture
   style already used in `tests/core_test/infra/scheduling/test_scheduler_on_error_logging.py`.

**Success criteria.** Both registered triggers report `timezone == UTC` regardless
of the host `TZ` under which the test runs.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/core_test/infra/scheduling/test_scheduler_cron_timezone.py -q`
exits 0 and reports `0 failed`.

### Task 1.6 — Fix the Binance weekly in-progress cutoff

**Goal.** The latest persisted `1w` bar for a Binance symbol is always the last
closed Monday-open week, never the in-progress one.

**Target files and symbols.**
- `src/pocketquant/core/infra/binance/binance_adapter.py` — lines 80-83, `last_closed_open_ms` / `cutoff_dt` / `end_time_ms`
- `tests/core_test/infra/binance/test_binance_client_in_progress_filter.py` (extend)

**Steps.**
1. Import `get_bar_start` from `pocketquant.core.domain.bar.services.bar_builder_domain_service`
   and `Interval` if not already imported in `binance_adapter.py`.
2. Replace the epoch-floor computation. Where line 81 currently reads
   `last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms`, compute
   `now_dt = datetime.now(UTC)` then `current_open = get_bar_start(now_dt, interval)`
   then `cutoff_dt = current_open` then
   `last_closed_open_ms = int(current_open.timestamp() * 1000)` and
   `end_time_ms = last_closed_open_ms`. Delete the now-redundant
   `datetime.fromtimestamp(last_closed_open_ms / 1000, tz=UTC)` line.
3. Update the existing comment block at lines 75-79 to say the cutoff is derived
   from the same alignment function the sync filter uses, so the two can never
   disagree; the raw epoch floor lands on Thursday for `1w` because the Unix epoch
   was a Thursday.
4. Add a test to `tests/core_test/infra/binance/test_binance_client_in_progress_filter.py`
   named `test_weekly_cutoff_is_monday_aligned_on_a_thursday`: freeze `now` at
   `datetime(2026, 9, 24, 12, 0, tzinfo=UTC)` (a Thursday) by monkeypatching
   `pocketquant.core.infra.binance.binance_adapter.datetime`, call the same helper
   the module uses to compute the cutoff, and assert the resulting `cutoff_dt`
   equals `datetime(2026, 9, 21, tzinfo=UTC)` (that week's Monday) — not
   `datetime(2026, 9, 24, tzinfo=UTC)`.

**Success criteria.** For a Thursday `now`, the `1w` cutoff is the current week's
Monday 00:00 UTC, so the in-progress weekly kline is excluded.

**Verify.** `uv run pytest tests/core_test/infra/binance/ -q` exits 0 and reports
`0 failed`, and the output includes `test_weekly_cutoff_is_monday_aligned_on_a_thursday`
when run with `-v`.

### Task 1.7 — Pin `TZ=UTC` in every runtime surface and prove `zoneinfo` resolves

**Goal.** No deployment or dev shell can run in a non-UTC process zone, and
`ZoneInfo("America/Chicago")` resolves inside the built image.

**Target files and symbols.**
- `deploy/Dockerfile` — runtime stage `ENV` block at lines 44-47, and the `apt-get install` at lines 33-36
- `deploy/compose.prod.yml` — the `app:` service, add an `environment:` block next to `env_file:` at lines 43-44
- `justfile` — the `be` recipe
- `pyproject.toml` — `dependencies`

**Steps.**
1. In `deploy/Dockerfile`, add `TZ=UTC \` as the first line of the runtime `ENV`
   block so it reads `ENV TZ=UTC \` then `PATH=...`, `PYTHONUNBUFFERED=1`,
   `PYTHONDONTWRITEBYTECODE=1`.
2. Add `tzdata` to the runtime-stage `apt-get install -y --no-install-recommends`
   list alongside `curl`. `uv.lock` carries the PyPI `tzdata` package only under
   `sys_platform == 'win32' or sys_platform == 'emscripten'` markers, so the Linux
   container does **not** get it from Python; `zoneinfo` needs the OS database for
   `America/Chicago`, which Phase 2 depends on.
3. In `deploy/compose.prod.yml`, under the `app:` service and immediately above
   `env_file:`, add:
   ```yaml
   # Explicit even though env_file exists: a missing TZ key in .env must not
   # unpin the process zone. The startup assertion refuses a non-UTC host.
   environment:
     TZ: "UTC"
   ```
4. In `justfile`, change the `be` recipe body to
   `TZ=UTC {{python}} -m uvicorn pocketquant.app.main:app --reload --host 0.0.0.0 --port 41921`
   and keep the existing comment block above it.
5. `deploy/compose.local.yml` defines only `mongodb` and `redis` services — there is
   no app service there. Do **not** add a `TZ` entry to it; the local app runs
   through `just be`, which task step 4 covers.

**Success criteria.** The built image reports `UTC` for its process zone and can
construct `ZoneInfo("America/Chicago")`.

**Verify.** `docker build -f deploy/Dockerfile -t pocketquant:tzcheck .` exits 0,
then `docker run --rm pocketquant:tzcheck python -c "import time,zoneinfo;print(time.tzname, zoneinfo.ZoneInfo('America/Chicago').key)"`
prints exactly `('UTC', 'UTC') America/Chicago` and exits 0.

### Task 1.8 — Fail fast on a non-UTC process timezone

**Goal.** The app raises `RuntimeError` at startup on any host that is not UTC,
and logs one INFO line recording what it observed.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py` — new `assert_process_timezone_utc(container)` coroutine
- `src/pocketquant/app/main.py` — `lifespan`, the import block at lines 9-26 and the call order at lines 54-74
- `tests/app_test/unit/test_timezone_startup_assertion.py` (new)

**Steps.**
1. In `main_extensions.py`, add `async def assert_process_timezone_utc(container: AsyncContainer) -> None:`.
   It must:
   - `import time` and `from tzlocal import get_localzone_name` (tzlocal 5.3.1 is
     already installed as an APScheduler dependency);
   - read `local_name = get_localzone_name()`;
   - `logger.info("runtime.timezone", tz_env=os.environ.get("TZ"), tzname=time.tzname, tzlocal=local_name)`
     exactly once;
   - raise `RuntimeError(f"Process timezone must be UTC; got tzname={time.tzname} tzlocal={local_name}")`
     when `time.timezone != 0 or time.daylight or local_name not in {"UTC", "Etc/UTC"}`.
2. Add `async def assert_registered_triggers_utc(container: AsyncContainer) -> None:`
   in the same module. It resolves `JobScheduler` from the container, iterates the
   scheduler's jobs, and raises `RuntimeError` naming the offending `job.id` when a
   job's `trigger` has a `timezone` attribute that is not UTC. Return immediately
   when `settings.enable_jobs` is false.
3. In `main.py`, import both new names in the `from pocketquant.app.main_extensions import (...)`
   block (lines 9-26, alphabetical order to satisfy ruff `I`).
4. In `lifespan`, call `await assert_process_timezone_utc(container)` as the FIRST
   awaited statement inside the `try:` at line 54, before
   `app.state.database = await container.get(Database)`. Call
   `await assert_registered_triggers_utc(container)` immediately after
   `await start_background_jobs(container)` (line 67).
5. Create `tests/app_test/unit/test_timezone_startup_assertion.py` with two tests
   that monkeypatch `time.timezone`, `time.daylight` and
   `pocketquant.app.main_extensions.get_localzone_name`: one asserting a UTC
   environment returns without raising, one asserting `Asia/Saigon` raises
   `RuntimeError` whose message contains `must be UTC`.

**Success criteria.** Startup under a non-UTC host raises before any Mongo or
scheduler work happens; exactly one `runtime.timezone` INFO line is emitted per boot.

**Verify.** `uv run pytest tests/app_test/unit/test_timezone_startup_assertion.py -q`
prints `2 passed`. Then `TZ=Asia/Saigon uv run python -c "import asyncio,time; from pocketquant.app.main_extensions import assert_process_timezone_utc; asyncio.run(assert_process_timezone_utc(None))"`
exits non-zero and its stderr contains `must be UTC`.

### Task 1.9 — Cross-zone test recipe, CI matrix and the cron equality test

**Goal.** The unit suite is proven host-zone independent in CI, and a single test
would have caught the CronTrigger bug.

**Target files and symbols.**
- `justfile` — new `test-tz` recipe
- `.github/workflows/cicd.yml` — the `tests` job, `Run pytest (full suite)` step at lines 34-35
- `tests/core_test/infra/scheduling/test_scheduler_cron_timezone.py` — add the equality test

**Steps.**
1. Add to `justfile`, after the existing `test` recipe:
   ```
   # Run the suite under three host zones — the check that catches host-zone leakage.
   test-tz:
       TZ=UTC {{python}} -m pytest -q
       TZ=Asia/Saigon {{python}} -m pytest -q
       TZ=America/Chicago {{python}} -m pytest -q
   ```
2. In `.github/workflows/cicd.yml`, add `strategy: { matrix: { tz: ["UTC", "Asia/Saigon", "America/Chicago"] } }`
   to the `tests` job (immediately under `timeout-minutes: 15`), and change the
   pytest step to `run: TZ=${{ matrix.tz }} uv run pytest tests/ -q`. Leave the
   `lint-imports` step unchanged.
3. In `test_scheduler_cron_timezone.py`, add `test_next_run_time_identical_across_host_zones`:
   for each of `"UTC"`, `"Asia/Saigon"`, `"America/Chicago"`, set `os.environ["TZ"]`,
   call `time.tzset()`, clear the `tzlocal` cache
   (`tzlocal.unix._cache_tz = None` guarded by `contextlib.suppress(AttributeError)`),
   build the same `CronTrigger` through `JobScheduler.add_cron_job(hour=3, minute=0)`,
   and collect `trigger.get_next_fire_time(None, datetime(2026, 9, 21, 12, 0, tzinfo=UTC))`.
   Assert all three collected values are equal and that the hour is `3`. Restore
   the original `TZ` and call `time.tzset()` in a `finally` block.

**Success criteria.** The equality test fails if `timezone=UTC` is reverted on
either `CronTrigger`; CI runs the suite under three zones.

**Verify.** `uv run pytest tests/core_test/infra/scheduling/test_scheduler_cron_timezone.py -q`
exits 0 and reports `0 failed`. Then `just test-tz` exits 0 with three `0 failed`
summaries.

### Task 1.10 — Phase gate

**Goal.** The whole repo is green under the new invariant and the gate behaviours
are reproduced.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates below in order.
2. Deploy to the VPS through the normal pipeline and confirm the app becomes
   healthy and the `runtime.timezone` INFO line shows `tzlocal=UTC`.
3. On the VPS, confirm every cron job's `next_run_time` in
   `GET /api/v1/system/jobs` matches the documented UTC hour: `sync_backfill` at
   03:00 UTC, `sync_integrity` at 04:00 UTC.
4. Record the observed `next_run_time` values in the phase notes.

**Success criteria.** All gates pass; the deployed app starts; the four daily jobs
fire at their documented UTC hours.

**Verify.** All four of the following exit 0:
`uv run pytest tests/ -q` reporting `0 failed` and at least `668 passed`;
`uv run ruff check src tests` printing `All checks passed!`;
`uv run lint-imports` printing `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` printing `0 errors, 0 warnings, 0 informations`.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `tz_aware=True` lands without the integrity fix | Medium | High — full resync of every symbol | Task 1.2 is one commit; the Verify step inspects `git show --stat HEAD` |
| `DTZ` surfaces findings beyond the measured 3 in `src` | Low | Low | Baseline measured 2026-09-21; re-run the count before editing |
| `AwareDatetime` validator breaks a Binance path | Low | Medium | `binance_mappers.py:57-58,90-91` already build with `tz=UTC` (verified) |
| Container lacks `America/Chicago` after the `TZ` pin | Medium | High in Phase 2 | Task 1.7 adds OS `tzdata` and verifies it in the image |
| Jobstore still holds host-zone-pickled triggers after deploy | Medium | Medium | `add_job` uses `replace_existing=True` (`scheduler.py:240`), so registration overwrites |

## Rollback

Every change in this phase is additive or a one-line substitution. Revert the
phase commit range with `git revert`. The only stateful side effect is the
`apscheduler_jobs` collection, which `register_sync_jobs` rewrites with
`replace_existing=True` on the next boot, so no manual cleanup is required.

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
effort: "14h"
dependencies: [1]
---

# Phase 2: Trading-calendar port and asset-class domain model

Maps to advice Phase 1.

## Context

This phase introduces the vocabulary and nothing else: an `AssetClass` enum, a
`ContractSpec` value object, an `ITradingCalendarPort` with two implementations,
and the persisted `calendar_id` / `contract_spec` / `session_date` fields. No
existing behaviour changes. Phase 3 is what actually routes the pipeline through
the port; splitting them keeps the byte-identical crypto proof isolated to one
diff.

Verified today: there is no `multiplier`, `contract_size`, `tick_size` or
`point_value` anywhere in `src/` (the only `multiplier` hits are an OKX
reconnection backoff at `okx_reconnection_handler.py:43` and a backtest
replay-speed field at `backtest/config.py:21`). `Symbol.asset_type` is a
free-string field at `core/domain/symbol/entities.py:38`.
`COMPOSITE_SYMBOL_RE` at `entities.py:19` is `^[A-Z0-9_-]+:[A-Z0-9_-]+$` and
`COMPOSITE_SYMBOL_PATTERN` at `entities.py:24` is
`^[A-Z0-9._-]{1,32}:[A-Z0-9._-]{1,32}$`; both reject `!`.

## Naming decisions (follow these exactly)

Per `docs/code-standards.md` "Class Naming by Layer": the port is
`ITradingCalendarPort` in `trading_calendar_port.py` (one port per file); the
infra implementation wrapping a third-party library is
`CmeGlobexEquityCalendarAdapter` in `cme_globex_equity_calendar_adapter.py`; the
pure domain implementation carries no suffix and is `Continuous24x7Calendar`,
following the same rule that names `PnL`, `OHLCV` and `Interval` after the
concept they model.

## Tasks

### Task 2.1 — Add the `AssetClass` enum

**Goal.** A closed enum names the three asset classes the system supports.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py` — new `AssetClass(str, Enum)`

**Steps.**
1. Append to `core/domain/shared/enums.py`:
   ```python
   class AssetClass(str, Enum):
       CRYPTO_SPOT = "crypto_spot"
       CRYPTO_PERP = "crypto_perp"
       INDEX_FUTURE = "index_future"
   ```
2. Add a docstring saying a new asset class is a new member here plus a new
   calendar record — never a new branch in the sync, cascade or integrity code.
3. Do NOT touch `_PERIODS_PER_YEAR` or `Interval.periods_per_year` in this task.
   Phase 3 Task 3.6 moves annualization onto the calendar.

**Success criteria.** `AssetClass.INDEX_FUTURE.value == "index_future"` and the
enum is a `str` subclass so it round-trips through Mongo unchanged.

**Verify.** `uv run python -c "from pocketquant.core.domain.shared.enums import AssetClass; print([a.value for a in AssetClass])"`
prints exactly `['crypto_spot', 'crypto_perp', 'index_future']` and exits 0.

### Task 2.2 — Add the `ContractSpec` value object

**Goal.** Contract unit conversion is a persisted, immutable value object with a
linear default that reproduces today's crypto math.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/value_objects.py` (new) — `ContractSpec`, `LINEAR_CONTRACT_SPEC`
- `src/pocketquant/core/domain/symbol/__init__.py` — re-export

**Steps.**
1. Create `core/domain/symbol/value_objects.py` with a frozen Pydantic model:
   ```python
   class ContractSpec(BaseModel):
       model_config = ConfigDict(frozen=True)
       multiplier: float = 1.0        # USD per 1.0 of price move per contract
       tick_size: float = 0.0         # 0.0 = no tick rounding
       lot_step: float | None = None  # None = fractional quantity allowed
       currency: str = "USD"
       commission_kind: Literal["percentage", "per_contract"] = "percentage"
       commission_value: float = 0.0  # bps when percentage, USD/contract otherwise
   ```
2. Add `to_mongo()` returning `self.model_dump()` and a `from_mongo(doc)`
   classmethod returning `cls(**doc)` when `doc` is truthy and `LINEAR_CONTRACT_SPEC`
   when it is `None` or `{}`.
3. Define the module constant `LINEAR_CONTRACT_SPEC = ContractSpec()` with a
   comment: this is the crypto shape — multiplier 1, fractional quantity, no tick
   rounding — and it is what every existing symbol migrates to, so realized PnL
   stays `(exit - entry) * quantity` exactly.
4. Add the three futures presets as module constants so the seeder and the tests
   share one source:
   `ES_CONTRACT_SPEC = ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, commission_kind="per_contract", commission_value=2.5)`,
   `NQ_CONTRACT_SPEC = ContractSpec(multiplier=20.0, tick_size=0.25, lot_step=1.0, commission_kind="per_contract", commission_value=2.5)`,
   `YM_CONTRACT_SPEC = ContractSpec(multiplier=5.0, tick_size=1.0, lot_step=1.0, commission_kind="per_contract", commission_value=2.5)`.
5. Re-export `ContractSpec` and `LINEAR_CONTRACT_SPEC` from
   `core/domain/symbol/__init__.py` alongside the existing `Symbol` export.

**Success criteria.** `ContractSpec` is frozen (mutation raises), and the ES preset
has `multiplier == 50.0`, `tick_size == 0.25`, `lot_step == 1.0`.

**Verify.** `uv run pytest tests/core_test/unit/domain/symbol/ -q` exits 0 after
Task 2.11 adds that directory; until then verify with
`uv run python -c "from pocketquant.core.domain.symbol.value_objects import ES_CONTRACT_SPEC as s; print(s.multiplier, s.tick_size, s.lot_step)"`
printing exactly `50.0 0.25 1.0` and exiting 0.

### Task 2.3 — Define `ITradingCalendarPort`

**Goal.** One interface expresses every schedule question the pipeline asks, so
a future asset class needs no new branching.

**Target files and symbols.**
- `src/pocketquant/core/domain/market_data/trading_calendar_port.py` (new) — `ITradingCalendarPort`

**Steps.**
1. Create the file next to the two existing ports
   (`data_provider_port.py`, `realtime_quote_provider_port.py`).
2. Define `class ITradingCalendarPort(ABC):` with these members. Every returned
   `datetime` is timezone-aware UTC; every `session_date` is a naive `date` in the
   exchange's own calendar.
   ```python
   calendar_id: str          # "CRYPTO_24_7" | "CME_GLOBEX_EQUITY"
   tz: ZoneInfo              # exchange-local zone, e.g. America/Chicago

   @abstractmethod
   def is_open(self, instant: datetime) -> bool: ...
   @abstractmethod
   def session_date(self, instant: datetime) -> date: ...
   @abstractmethod
   def session_open(self, session_date: date) -> datetime: ...
   @abstractmethod
   def session_close(self, session_date: date) -> datetime: ...
   @abstractmethod
   def previous_close(self, instant: datetime) -> datetime: ...
   @abstractmethod
   def sessions(self, start: datetime, end: datetime) -> list[date]: ...
   @abstractmethod
   def trading_minutes(self, start: datetime, end: datetime) -> list[datetime]: ...
   @abstractmethod
   def bar_start(self, instant: datetime, interval: Interval) -> datetime: ...
   @abstractmethod
   def bucket_starts(self, interval: Interval, range_start: datetime,
                     range_end: datetime) -> list[datetime]: ...
   @abstractmethod
   def expected_source_bars(self, interval: Interval, bucket_start: datetime) -> int: ...
   @abstractmethod
   def periods_per_year(self, interval: Interval) -> float | None: ...
   ```
3. Document each method with one line stating the contract. In particular:
   `bar_start` returns the opening instant of the bar of `interval` that contains
   `instant`; `bucket_starts` returns every cascade bucket opening whose bucket
   overlaps `[range_start, range_end)` (the overlap semantics documented at
   `cascade_aggregator.py:74-95` must be preserved); `expected_source_bars` returns
   how many 1m source bars a complete bucket of `interval` contains;
   `trading_minutes` returns every minute-aligned tradeable instant in
   `[start, end)`.
4. Add an explicit note that implementations must not import pymongo, redis,
   aiohttp, httpx or fastapi — `tests/core_test/unit/domain/test_domain_purity.py`
   enforces this by AST walk over `core/domain/`.

**Success criteria.** The port imports cleanly from `core.domain` and the domain
purity test still passes.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_domain_purity.py -q`
prints `1 passed` and exits 0.

### Task 2.4 — Implement `Continuous24x7Calendar`

**Goal.** A pure domain calendar reproduces every current crypto number exactly,
so Phase 3's refactor is provably behaviour-preserving.

**Target files and symbols.**
- `src/pocketquant/core/domain/market_data/continuous_24x7_calendar.py` (new) — `Continuous24x7Calendar`, `CONTINUOUS_24X7`
- `src/pocketquant/core/domain/shared/enums.py` — read `_PERIODS_PER_YEAR` (do not edit yet)

**Steps.**
1. Implement `Continuous24x7Calendar(ITradingCalendarPort)` with
   `calendar_id = "CRYPTO_24_7"` and `tz = ZoneInfo("UTC")`.
2. `is_open` always returns `True`. `session_date(instant)` returns
   `require_utc(instant).date()`. `session_open(d)` returns
   `datetime(d.year, d.month, d.day, tzinfo=UTC)`. `session_close(d)` returns
   `session_open(d) + timedelta(days=1)`. `previous_close(instant)` returns
   `require_utc(instant)` (a 24/7 market has no close, so "last expected bar
   close" is now).
3. `bar_start(instant, interval)` must reproduce the current
   `get_bar_start` body verbatim after Phase 1 Task 1.2 removed the naive branch:
   `DAY_1` -> `replace(hour=0, minute=0, second=0, microsecond=0)`;
   `WEEK_1` -> that midnight minus `timedelta(days=midnight.weekday())`;
   everything else -> floor against `datetime(1970,1,1,tzinfo=UTC)` by
   `INTERVAL_SECONDS[interval]`. Call `require_utc(instant)` first.
4. `bucket_starts(interval, range_start, range_end)` must reproduce
   `cascade_aggregator.compute_boundaries` verbatim: floor
   `range_start.timestamp()` to `tf_seconds`, then walk forward by `tf_seconds`
   while `current < range_end`. Copy the docstring's overlap rationale across.
5. `expected_source_bars(interval, bucket_start)` returns the current
   `_TF_EXPECTED_BARS` values: 5m 5, 15m 15, 1h 60, 4h 240, 1d 1440; `0` for any
   other interval (matching `_TF_EXPECTED_BARS.get(tf, 0)` at
   `cascade_aggregator.py:139`).
6. `sessions(start, end)` returns every UTC calendar date in `[start, end)`.
   `trading_minutes(start, end)` returns every minute-aligned instant in
   `[start, end)`.
7. `periods_per_year(interval)` returns the current `_PERIODS_PER_YEAR` values by
   `interval.value` lookup, returning `None` for an unknown key — identical
   semantics to `Interval.periods_per_year_for`.
8. Export a module singleton `CONTINUOUS_24X7 = Continuous24x7Calendar()`. It is
   stateless and therefore safe to share process-wide.

**Success criteria.** For every interval, `CONTINUOUS_24X7.bar_start` returns the
same value as the current `get_bar_start`, and `bucket_starts` the same list as
the current `compute_boundaries`.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_aggregator.py tests/core_test/unit/domain/bar/services/test_bar_builder.py -q`
exits 0 with `0 failed` (these still exercise the original functions and must stay
green), and Task 2.11's new equivalence test passes.

### Task 2.5 — Add `pandas_market_calendars` and implement the CME adapter

**Goal.** CME Globex equity session rules, including holidays and early closes,
come from a maintained library behind the port.

**Target files and symbols.**
- `pyproject.toml` — `dependencies`
- `src/pocketquant/core/infra/calendars/__init__.py` (new)
- `src/pocketquant/core/infra/calendars/cme_globex_equity_calendar_adapter.py` (new) — `CmeGlobexEquityCalendarAdapter`

**Steps.**
1. Add `"pandas-market-calendars>=4.4.0",` to the `dependencies` list in
   `pyproject.toml` (after `"pandas>=2.1.0",`). Run `uv sync` so `uv.lock` updates.
2. Confirm the alias string before writing code — the audit recorded class
   `CMEGlobexEquitiesExchangeCalendar` with alias `"CME Globex Equity"`,
   `ZoneInfo("America/Chicago")`, `market_open = time(17)` offset -1 day,
   `market_close = time(16)`. Run the Verify command below FIRST; if the alias
   differs, STOP and follow the Failure Protocol rather than guessing.
3. Create `core/infra/calendars/cme_globex_equity_calendar_adapter.py` implementing
   `ITradingCalendarPort` with `calendar_id = "CME_GLOBEX_EQUITY"` and
   `tz = ZoneInfo("America/Chicago")`. Construct the underlying calendar once in
   `__init__` via `pandas_market_calendars.get_calendar("CME Globex Equity")`.
4. `session_open(d)` / `session_close(d)`: call the library's `schedule(d, d)` and
   read the `market_open` / `market_close` columns, then convert with
   `.to_pydatetime().astimezone(UTC)`. Never add a fixed offset and never construct
   a UTC instant by arithmetic on a wall-clock hour.
5. `is_open(instant)`: `session_open(session_date(instant)) <= instant < session_close(...)`
   for the session the instant falls in; return `False` when the library returns an
   empty schedule for that date (holiday).
6. `session_date(instant)`: the CME session that opens at 17:00 CT on day D-1 and
   closes at 16:00 CT on day D has `session_date = D`. Derive it by converting the
   instant to `America/Chicago` and adding one day when the local time is at or
   after 17:00, then snapping to the next scheduled session date if the result is
   not a scheduled session.
7. `previous_close(instant)`: the most recent `session_close` at or before
   `instant`; when the market is open, this is the previous session's close.
8. `sessions(start, end)`: the library's `valid_days`/`schedule` index restricted
   to `[start, end)`. `trading_minutes(start, end)`: for each session in range,
   every minute from `session_open` (inclusive) to `session_close` (exclusive),
   clipped to `[start, end)`. Do not include the 16:00-17:00 CT maintenance gap —
   it is simply the space between one `session_close` and the next `session_open`.
9. `bar_start(instant, interval)`: for `DAY_1` return `session_open(session_date(instant))`;
   for `WEEK_1` return the `session_open` of the first session of that session's
   ISO week; for intraday intervals return
   `session_open + floor((instant - session_open) / interval) * interval`.
10. `bucket_starts(interval, range_start, range_end)`: for `DAY_1` and `WEEK_1`,
    the `bar_start` of each session overlapping the range; for intraday intervals,
    `session_open + k*interval` for each session, kept while the bucket start is
    before `session_close` and the bucket overlaps `[range_start, range_end)`.
11. `expected_source_bars(interval, bucket_start)`:
    `len(trading_minutes(bucket_start, bucket_start + interval_duration))`, clipped
    at the session close so an early-close day reports its real count.
12. `periods_per_year(interval)`: derive from the calendar, not a constant. Compute
    `sessions_per_year` and `minutes_per_year` from `trading_minutes` over the
    trailing 365 days ending at the most recent completed session, then divide by
    the interval's minutes. Cache the result per interval in an instance dict; the
    adapter is an APP-scoped singleton so the cache lives for the process.
13. Add `core/infra/calendars/__init__.py` re-exporting the adapter class.

**Success criteria.** The adapter resolves real CME sessions with DST-correct UTC
instants and never imports anything into `core/domain`.

**Verify.** First run
`uv run python -c "import pandas_market_calendars as m; c=m.get_calendar('CME Globex Equity'); print(type(c).__name__, c.tz)"`
— it must print `CMEGlobexEquitiesExchangeCalendar America/Chicago` and exit 0.
Then `uv run lint-imports` prints `Contracts: 8 kept, 0 broken.` and exits 0.

### Task 2.6 — Calendar registry and per-symbol resolver

**Goal.** Any engine call site can ask "which calendar governs this symbol?" and
get an answer without knowing about Mongo or `pandas_market_calendars`.

**Target files and symbols.**
- `src/pocketquant/core/infra/calendars/trading_calendar_registry.py` (new) — `TradingCalendarRegistry`
- `src/pocketquant/core/infra/calendars/symbol_calendar_resolver.py` (new) — `SymbolCalendarResolver`
- `src/pocketquant/app/di/market_data.py` — new `@provide(scope=Scope.APP)` methods

**Steps.**
1. `TradingCalendarRegistry` holds `dict[str, ITradingCalendarPort]` keyed by
   `calendar_id`, seeded with `CONTINUOUS_24X7` and one
   `CmeGlobexEquityCalendarAdapter()`. Expose `get(calendar_id: str) -> ITradingCalendarPort`
   which raises `KeyError` naming the unknown id, and `ids() -> list[str]`.
2. `SymbolCalendarResolver.__init__(self, symbol_repository: SymbolRepository, registry: TradingCalendarRegistry)`.
   Add `async def for_symbol(self, symbol: str) -> ITradingCalendarPort` which looks
   the composite symbol up, reads its `calendar_id`, and returns the registered
   calendar. When the symbol record is absent or carries no `calendar_id`, return
   `CONTINUOUS_24X7` and log one DEBUG `calendar.default_applied` line — never
   WARNING, because this fires per sync iteration.
3. Cache with `cachetools.TTLCache(maxsize=512, ttl=300)` (cachetools is already a
   dependency in `pyproject.toml`). Add a load-bearing comment: the resolver is an
   APP-scoped singleton, so the cache lives for the whole process; a 300s TTL
   bounds staleness after an admin edits a symbol's `calendar_id`, which is the
   only way the mapping changes.
4. In `app/di/market_data.py`, add `get_trading_calendar_registry(self) -> TradingCalendarRegistry`
   and `get_symbol_calendar_resolver(self, symbol_repository: SymbolRepository, registry: TradingCalendarRegistry) -> SymbolCalendarResolver`,
   both `@provide(scope=Scope.APP)`. Import `SymbolRepository` from
   `pocketquant.core.infra.persistence.repositories.symbol_repository`.

**Success criteria.** `SymbolCalendarResolver.for_symbol("BTCUSDT:BINANCE")` returns
`CONTINUOUS_24X7`; `for_symbol("ES1!:CME_MINI")` returns the CME adapter once the
symbol record exists; an unknown `calendar_id` raises `KeyError`.

**Verify.** `uv run pytest tests/core_test/infra/calendars/ -q` exits 0 and reports
`0 failed` after Task 2.11 adds those tests.

### Task 2.7 — Extend `Symbol` with asset class, calendar id and contract spec

**Goal.** The schedule and contract shape are persisted alongside the asset class,
exactly as R1b requires.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py` — `Symbol` fields (lines 35-40), `Symbol.create` (lines 62-70), `to_mongo` (78-87), `from_mongo` (89-100)

**Steps.**
1. Replace the `asset_type: str | None = None` field at line 38 with:
   ```python
   asset_class: AssetClass = AssetClass.CRYPTO_SPOT
   calendar_id: str = "CRYPTO_24_7"
   contract_spec: ContractSpec = Field(default_factory=lambda: LINEAR_CONTRACT_SPEC)
   ```
2. Update `Symbol.create` (line 63) to take `asset_class: AssetClass = AssetClass.CRYPTO_SPOT`,
   `calendar_id: str = "CRYPTO_24_7"` and `contract_spec: ContractSpec | None = None`
   in place of `asset_type`, passing `contract_spec or LINEAR_CONTRACT_SPEC`.
3. Update `to_mongo` (line 84) to emit `"asset_class": self.asset_class.value`,
   `"calendar_id": self.calendar_id`, `"contract_spec": self.contract_spec.to_mongo()`
   and to stop emitting `"asset_type"`.
4. Update `from_mongo` (line 97) to read `asset_class=AssetClass(doc.get("asset_class", "crypto_spot"))`,
   `calendar_id=doc.get("calendar_id", "CRYPTO_24_7")` and
   `contract_spec=ContractSpec.from_mongo(doc.get("contract_spec"))`. The defaults
   make `from_mongo` safe against un-migrated documents, which is what keeps the
   app bootable between deploy and migration.
5. Grep for remaining `asset_type` references and update every one:
   `uv run python -c "import subprocess,sys; sys.exit(0)"` is not the check — run
   `grep -rn "asset_type" src/ tests/ web/src/` and fix each hit. At the time of
   writing the only `src/` definitions are in `entities.py` itself (lines 38, 65,
   70, 84, 97); re-run the grep because it may have changed.

**Success criteria.** A `Symbol` built with no arguments carries
`AssetClass.CRYPTO_SPOT`, `"CRYPTO_24_7"` and `LINEAR_CONTRACT_SPEC`; an
un-migrated Mongo document loads with those same defaults.

**Verify.** `uv run pytest tests/ -q -k "symbol"` exits 0 with `0 failed`, and
`grep -rn "asset_type" src/` produces no output (exit code 1 from grep is expected
and correct).

### Task 2.8 — Widen both composite-symbol regexes to accept `!`

**Goal.** `ES1!:CME_MINI` validates end to end.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py:19` — `COMPOSITE_SYMBOL_RE`
- `src/pocketquant/core/domain/symbol/entities.py:24` — `COMPOSITE_SYMBOL_PATTERN`

**Steps.**
1. Change `COMPOSITE_SYMBOL_RE` to `re.compile(r"^[A-Z0-9!_-]+:[A-Z0-9!_-]+$")`.
2. Change `COMPOSITE_SYMBOL_PATTERN` to
   `re.compile(r"^[A-Z0-9.!_-]{1,32}:[A-Z0-9.!_-]{1,32}$")`.
3. Add a comment naming why: TradingView continuous front-month contracts are
   written `ES1!`, `NQ1!`, `YM1!`, and the exchange suffix stays meaningful to the
   adapter (`CME_MINI`, `CBOT_MINI`).
4. No call site changes are needed. The complete caller list, verified today:
   `COMPOSITE_SYMBOL_RE` is used only at `entities.py:48`;
   `COMPOSITE_SYMBOL_PATTERN` at `app/common/symbol_validation.py:23`,
   `engine/market_data/tracked_symbols_service.py:35` and
   `engine/market_data/tracked_symbols_backfill.py:65`. Confirm with
   `grep -rn "COMPOSITE_SYMBOL_RE\|COMPOSITE_SYMBOL_PATTERN" src/ tests/`.
5. `web/src/lib/symbol-format.ts` splits on the first `:` with `indexOf` and applies
   no character class, so the SPA needs no change. `encodeURIComponent("!")` leaves
   `!` unescaped, which FastAPI path routing accepts.

**Success criteria.** `Symbol.create("es1!:cme_mini")` yields `symbol == "ES1!:CME_MINI"`;
`validate_composite_symbol("ES1!:CME_MINI")` returns it unchanged; `"BTC/USD:X"`
still raises.

**Verify.** `uv run python -c "from pocketquant.core.domain.symbol import Symbol; print(Symbol.create('es1!:cme_mini').symbol)"`
prints exactly `ES1!:CME_MINI` and exits 0.

### Task 2.9 — Persist `session_date` and `calendar_id` on bars and index them

**Goal.** Daily and weekly bars carry a stable day key that does not move with DST.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar` fields, `to_mongo` (line 60), `from_mongo` (line 76)
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py` — `ensure_indexes` (line 284)

**Steps.**
1. Add two optional fields to `Bar`: `session_date: date | None = None` and
   `calendar_id: str | None = None`. Both default to `None` so every existing bar
   loads unchanged and the unique index `(symbol, interval, datetime)` is untouched.
2. Emit both in `to_mongo` (store `session_date` as an ISO `str`, because BSON has
   no date-only type and a `datetime` would reintroduce a timezone question).
   Read both back in `from_mongo`, parsing with `date.fromisoformat` when present.
3. In `bar_repository.ensure_indexes`, after the existing unique index creation at
   lines 286-290, add a second non-unique index
   `[("symbol", 1), ("interval", 1), ("session_date", 1)]` named
   `ix_ohlcv_symbol_interval_session_date`, with a comment that it serves 1d/1w
   session-day lookups while `datetime` keeps moving with DST.
4. Do not populate the fields yet. Phase 3 Task 3.2 sets them at write time.

**Success criteria.** Existing bar documents load and re-save without either field
appearing as a non-null value; `ensure_indexes` is idempotent on an existing
collection.

**Verify.** `uv run pytest tests/core_test/infra/persistence/test_bar_repository.py tests/core_test/unit/domain/bar/ -q`
exits 0 with `0 failed`.

### Task 2.10 — One-off migration stamping existing symbols

**Goal.** Every symbol already in Mongo carries an explicit asset class, calendar
id and linear contract spec.

**Target files and symbols.**
- `scripts/migrate_symbol_asset_class.py` (new)

**Steps.**
1. Create the script following the conventions in `scripts/README.md`: reads
   `MONGODB_URL` from the environment, never from CLI flags; dry-run by default.
2. Accept `--apply` to perform writes. Without it, print the counts it would change
   and exit 0.
3. For every document in the `symbols` collection that lacks `asset_class`, `$set`
   `asset_class: "crypto_spot"`, `calendar_id: "CRYPTO_24_7"` and
   `contract_spec: {multiplier: 1.0, tick_size: 0.0, lot_step: null, currency: "USD", commission_kind: "percentage", commission_value: 0.0}`,
   and `$unset` `asset_type`.
4. Print a one-line summary: matched, modified, skipped.
5. Note in the module docstring that per `scripts/README.md` this one-time migration
   is removed from `scripts/` once it has run in production and survives only in
   git history.

**Success criteria.** A dry run reports the number of un-migrated symbols; `--apply`
is idempotent — a second run reports `modified=0`.

**Verify.** `uv run python scripts/migrate_symbol_asset_class.py` exits 0 and prints
a line containing `matched=`. Then against the local stack,
`uv run python scripts/migrate_symbol_asset_class.py --apply` exits 0, and running
it a second time prints `modified=0`.

### Task 2.11 — Calendar and contract test suite

**Goal.** Every DST, holiday and session-boundary case named in R10 is covered by
a test with a hard-coded UTC expectation.

**Target files and symbols.**
- `tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py` (new)
- `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py` (new)
- `tests/core_test/unit/domain/symbol/test_contract_spec.py` (new)

**Steps.**
1. In `test_cme_globex_equity_calendar.py`, assert these exact instants (each one
   was computed against `zoneinfo` on 2026-09-21 and is correct):
   - spring forward: `session_open(date(2026, 3, 9)) == datetime(2026, 3, 8, 22, tzinfo=UTC)`
   - fall back: `session_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 23, tzinfo=UTC)`
   - matching closes: `session_close(date(2026, 3, 9)) == datetime(2026, 3, 9, 21, tzinfo=UTC)`
     and `session_close(date(2026, 11, 2)) == datetime(2026, 11, 2, 22, tzinfo=UTC)`
2. Add a Sunday-reopen test: `is_open(datetime(2026, 3, 8, 21, 59, tzinfo=UTC))` is
   `False` and `is_open(datetime(2026, 3, 8, 22, 1, tzinfo=UTC))` is `True`.
3. Add a session-spans-UTC-midnight test: `session_date(datetime(2026, 3, 9, 2, 0, tzinfo=UTC))`
   equals `date(2026, 3, 9)` — the same session as the 22:00 UTC open on 3-8.
4. Add a Juneteenth early-close test: the 2026-06-19 session closes at 12:00 CT,
   so `session_close(date(2026, 6, 19)) == datetime(2026, 6, 19, 17, tzinfo=UTC)`.
5. Add a holiday test: pick a full-closure US holiday from the library's schedule
   for 2026 and assert `sessions()` omits it and `is_open` is `False` across it.
6. Add a weekend-quiet test: `trading_minutes` over Friday 16:00 CT to Sunday
   17:00 CT returns an empty list.
7. In `test_continuous_24x7_calendar.py`, add the equivalence tests that protect
   Phase 3: for every `Interval` member and a set of ~20 sample instants,
   `CONTINUOUS_24X7.bar_start(ts, iv)` equals the current
   `get_bar_start(ts, iv)`; and for four sample ranges,
   `CONTINUOUS_24X7.bucket_starts(...)` equals the current `compute_boundaries(...)`.
   Also assert `periods_per_year` matches `Interval.periods_per_year_for` for all
   seven intervals and returns `None` for `"3m"`.
8. In `test_contract_spec.py`, assert `LINEAR_CONTRACT_SPEC.multiplier == 1.0` and
   `lot_step is None`; assert mutation of a frozen spec raises; assert the three
   futures presets carry ES 50 / NQ 20 / YM 5.
9. Run the whole new suite under all three host zones, because these are exactly
   the assertions a host-zone leak would break.

**Success criteria.** Every listed assertion passes under `TZ=UTC`,
`TZ=Asia/Saigon` and `TZ=America/Chicago`.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/core_test/infra/calendars/ tests/core_test/unit/domain/market_data/ tests/core_test/unit/domain/symbol/ -q`
exits 0 and reports `0 failed`.

### Task 2.12 — Phase gate

**Goal.** The new vocabulary is in place with no behaviour change anywhere.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates.
2. Confirm no sync, cascade, integrity or freshness code path was edited in this
   phase: `git diff --stat <phase-1-tip>..HEAD` must not list
   `cascade_aggregator.py`, `integrity_jobs.py`, `sync_status_service.py`,
   `anomaly_log.py`, `bar_filters.py` or `sync_jobs.py`.
3. Run the migration against the production database and record the counts.

**Success criteria.** All gates pass and the diff scope check holds.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors, 0 warnings, 0 informations`. All four exit 0.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `pandas_market_calendars` alias differs from `"CME Globex Equity"` | Low | High — nothing else works | Task 2.5 step 2 verifies the alias before any code is written; mismatch triggers the Failure Protocol |
| The library does not model the 16:00-17:00 CT halt as expected | Medium | Medium | The halt is the gap between `session_close` and the next `session_open`; Task 2.11 step 6 asserts the weekend case and the same shape covers the daily halt |
| `pandas_market_calendars` pulls a heavy transitive tree into `core/infra` | Low | Low | `pandas` is already a dependency; `lint-imports` keeps it out of `engine` and `core/domain` |
| Removing `asset_type` breaks an unnoticed consumer | Low | Medium | Task 2.7 step 5 greps `src/`, `tests/` and `web/src/` and the phase gate re-runs the full suite |
| `SymbolCalendarResolver` cache returns a stale calendar after an admin edit | Low | Medium | 300s TTL bounds it; the field only changes through the admin route |
| The CME `periods_per_year` derivation is slow on first call | Medium | Low | Cached per interval on an APP-scoped singleton; computed once per process |

## Rollback

Nothing in this phase changes an executing code path. Reverting the phase commits
restores `asset_type`. The only persisted change is the symbol migration and the
new bar index: re-add `asset_type` by reversing the `$set`/`$unset`, and drop
`ix_ohlcv_symbol_interval_session_date` — the unique index that the pipeline
depends on is untouched.

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
effort: "16h"
dependencies: [2]
---

# Phase 3: Thread the calendar through the pipeline (24/7 only)

Maps to advice Phase 2.

## Context

This phase retires the five P0s that would fire on day one of a session-scheduled
asset class, executed with the 24/7 calendar ONLY so the crypto path proves the
refactor before any futures symbol exists. Verified sites:

- **Alignment.** `bar_builder_domain_service.py:10-32` defines 1d as
  `replace(hour=0)` and 1w as Monday 00:00; `bar_filters.py:72-82` drops anything
  else on every sync (called from `sync_service.py:79-81`); `SYNC_INTERVALS` at
  `sync_jobs.py:54-62` includes `DAY_1` and `WEEK_1`.
- **Cascade.** `cascade_aggregator.py:98-108` (`compute_boundaries`) floors to a
  fixed UTC epoch grid; `_TF_EXPECTED_BARS[DAY_1] = 1440` at `:46`; the partial
  warning is at `:158-166`.
- **Integrity.** `integrity_jobs.py:62-63` builds a dense arithmetic grid; the
  docstring at `:46-47` admits it is 24/7-only; `repair_integrity` at `:79-116`
  resyncs 5000 bars per symbol/interval.
- **Freshness.** `sync_status_service.py:62-69` (`_is_stuck`),
  `anomaly_log.py:35-40,52-59` (`emit_no_progress`), `web/src/lib/datetime.ts:88-97`
  (`ageColorClass`) all measure `now - last_bar`.
- **Annualization.** `core/domain/shared/enums.py:5-13` and
  `performance_calculator_domain_service.py:13-14`.

## Design decision: the calendar is a REQUIRED keyword argument

Every pure function that gains a calendar takes it as a required keyword-only
parameter with NO default. A default of `CONTINUOUS_24X7` would be silently wrong
for a futures symbol, and a silently wrong alignment filter drops 100% of provider
bars. Making it required converts that failure into an immediate `TypeError` that
the 669-test suite surfaces at exactly the offending call site. The cost is
mechanical edits in six test files, listed per task.

`SyncService` is the exception: it already receives `symbol_repository` in
`__init__` (`sync_service.py:42`), so it resolves the calendar itself and
`_sync_by_intervals` in `sync_jobs.py` needs no signature change.

## Complete call-site inventory (verified 2026-09-21)

| Symbol | Call sites |
|---|---|
| `get_bar_start` | `integrity_jobs.py:51`, `bar_app_service.py:88`, `bar_builder_domain_service.py:125`, exported at `bar/services/__init__.py:3,6` |
| `is_bar_aligned` | `integrity_jobs.py:57`, `bar_alignment.py:7`, `bar_builder_domain_service.py:38` |
| `filter_aligned_bars` | `bar_filters.py:74` |
| `drop_misaligned_bars` | `sync_service.py:80` |
| `has_aligned_bar` | `provider_fetch.py:61` |
| `compute_boundaries` | `cascade_aggregator.py:166` |
| `cascade_for_symbol` | `sync_jobs.py:413`, `tracked_symbols_backfill.py:176` |
| `check_integrity` | `routes/integrity.py:33`, `integrity_jobs.py:92`, `integrity_jobs.py:119`, `sync_jobs.py:302` |
| `repair_integrity` | `routes/integrity.py:45`, `sync_jobs.py:347` |
| `Interval.periods_per_year_for` | `backtest_report_app_service.py:368` (only production caller) |

## Tasks

### Task 3.1 — Capture the golden-file baseline BEFORE any refactor

**Goal.** A committed fixture proves crypto bars, cascade output and metrics are
byte-identical across this phase.

**Target files and symbols.**
- `tests/app_test/market_data/test_calendar_refactor_golden.py` (new)
- `tests/app_test/market_data/fixtures/golden_cascade_btcusdt.json` (new)

**Steps.**
1. Build a deterministic in-memory series of 1440 synthetic 1m `Bar` objects for
   `BTCUSDT:BINANCE` starting at `datetime(2026, 9, 14, 0, 0, tzinfo=UTC)`, with
   `open/high/low/close` derived from the bar index so the values are reproducible
   with no randomness.
2. Run the CURRENT code against them and record, as a JSON fixture:
   - for each `Interval`, `[get_bar_start(ts, iv).isoformat() for ts in samples]`
     over 24 sample instants;
   - for each of the five `CASCADE_TFS`, `[b.isoformat() for b in compute_boundaries(tf, range_start, range_end)]`
     over a 26-hour range;
   - the aggregated OHLCV dicts produced by `aggregate_ohlcv` per bucket;
   - `Interval.periods_per_year_for(v)` for all seven interval strings.
3. Write the fixture to `fixtures/golden_cascade_btcusdt.json` and commit it in
   this task's commit, BEFORE editing any production file.
4. Write the test to load the fixture and compare against the CURRENT API. It must
   pass immediately on unchanged code.
5. Add a module docstring: this file is the contract for G5. If a later task makes
   it fail, the refactor changed crypto behaviour and must be corrected — the
   fixture must never be regenerated to make a failure go away.

**Success criteria.** The test passes against unmodified `develop` code and the
fixture is committed.

**Verify.** `uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q`
prints `1 passed` (or the number of test functions written) with `0 failed`, and
`git status --porcelain tests/app_test/market_data/fixtures/` produces no output
after committing.

### Task 3.2 — Calendar-aware alignment

**Goal.** A bar's expected opening instant comes from the calendar, so a 17:00 CT
daily open is as valid as a 00:00 UTC one.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` — `get_bar_start`, `is_bar_aligned`, `filter_aligned_bars`, `BarBuilderDomainService.create_for_tick`
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py:72-82` — `drop_misaligned_bars`
- `src/pocketquant/engine/market_data/sync_internals/bar_alignment.py:6-7` — `has_aligned_bar`
- `src/pocketquant/engine/market_data/sync_service.py:51-81` — `SyncService.__init__`, `sync_one`
- `src/pocketquant/engine/market_data/app_services/bar_app_service.py:88`
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py:51,57`

**Steps.**
1. Change the three domain functions to take a required keyword-only calendar:
   - `def get_bar_start(timestamp: datetime, interval: Interval, *, calendar: ITradingCalendarPort) -> datetime:`
     whose body becomes `return calendar.bar_start(timestamp, interval)`;
   - `def is_bar_aligned(timestamp, interval, *, calendar) -> bool:` returning
     `timestamp == calendar.bar_start(timestamp, interval)`;
   - `def filter_aligned_bars(bars, interval, *, calendar) -> tuple[list[Bar], list[Bar]]:`
     forwarding the calendar.
   Delete the interval-specific bodies; the logic now lives in
   `Continuous24x7Calendar.bar_start` (Phase 2 Task 2.4 step 3) and in the CME
   adapter.
2. `BarBuilderDomainService.create_for_tick` (line 118) gains a required keyword-only
   `calendar` and forwards it at line 125.
3. `drop_misaligned_bars(records, interval, *, calendar)` forwards to
   `filter_aligned_bars`. Leave the WARNING log at lines 76-81 as is — it stays
   WARNING because after this change it means a real provider defect, not a routine
   session bar.
4. `has_aligned_bar(records, interval, *, calendar)` forwards to `is_bar_aligned`.
   `fetch_with_retry` in `provider_fetch.py` gains a required keyword-only
   `calendar` and passes it at line 61.
5. `SyncService.__init__` gains `calendar_resolver: SymbolCalendarResolver` as a new
   parameter stored on `self._calendar_resolver`. In `sync_one`, immediately after
   `symbol = request.symbol.upper()` (line 53), add
   `calendar = await self._calendar_resolver.for_symbol(symbol)` and pass
   `calendar=calendar` into `fetch_with_retry` (line 66) and `drop_misaligned_bars`
   (line 80). Update the Dishka provider for `SyncService` at
   `app/di/market_data.py:26` — it uses `provide(SyncService, scope=Scope.APP)`, so
   Dishka injects the new dependency automatically once
   `SymbolCalendarResolver` is registered (Phase 2 Task 2.6).
6. `bar_app_service.py:88` is on the realtime tick path and has no repo access.
   Give `BarAppService.__init__` a `calendar_resolver: SymbolCalendarResolver`
   parameter (wire it in `app/di/market_data.py:29-32`), resolve per symbol inside
   the method containing line 88, and pass the calendar to `get_bar_start`.
7. `integrity_jobs.py:51,57` are handled in Task 3.4; leave them broken until then
   and note that the suite will be red between 3.2 and 3.4 — do not "fix" them by
   passing `CONTINUOUS_24X7`.
8. Set `session_date` and `calendar_id` on bars at write time: in
   `bar_filters.drop_misaligned_bars`, after computing `aligned`, stamp each kept
   bar with `bar.session_date = calendar.session_date(bar.datetime)` and
   `bar.calendar_id = calendar.calendar_id` for `DAY_1` and `WEEK_1` only. This is
   the single write point Phase 2 Task 2.9 deferred.
9. Update the test files that call the changed functions:
   `tests/core_test/unit/domain/bar/services/test_bar_builder.py` (lines 13-14,
   102-127), `tests/app_test/unit/handlers/sync/test_bar_filters.py`,
   `tests/app_test/unit/handlers/sync/test_provider_fetch.py`,
   `tests/engine_test/market_data/test_sync_service.py`. Add
   `calendar=CONTINUOUS_24X7` at each call and import it from
   `pocketquant.core.domain.market_data.continuous_24x7_calendar`.

**Success criteria.** Passing `CONTINUOUS_24X7` reproduces every current alignment
result; omitting the calendar raises `TypeError` at the call site.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar/ tests/app_test/unit/handlers/sync/ tests/engine_test/market_data/test_sync_service.py tests/app_test/market_data/test_calendar_refactor_golden.py -q`
exits 0 and reports `0 failed`.

### Task 3.3 — Calendar-aware cascade

**Goal.** Cascade buckets are session-anchored and expected counts come from the
calendar, so a 23-hour session no longer reads as a partial day.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` — `compute_boundaries` (98-108), `_TF_EXPECTED_BARS` (41-47), `cascade_for_symbol` (111-...), the partial warning (158-166)
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:413`
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py:176`

**Steps.**
1. Change `compute_boundaries(tf, range_start, range_end, *, calendar)` to
   `return calendar.bucket_starts(tf, range_start, range_end)` and move the existing
   overlap-semantics docstring onto the port method (Phase 2 Task 2.3 step 3 already
   asked for it) while keeping a one-line pointer here.
2. Delete the module-level `_TF_EXPECTED_BARS` dict at lines 41-47. Replace the
   `expected_count = _TF_EXPECTED_BARS.get(tf, 0)` line at 139 with
   `expected_count = calendar.expected_source_bars(tf, boundary)` computed INSIDE
   the per-boundary loop, because an early-close day has a different count per
   bucket. Move the `limit=expected_count + 5` argument (line 150) accordingly.
3. `cascade_for_symbol(symbol, lookback_minutes, bar_repo, *, calendar)` gains the
   required keyword-only calendar and forwards it. Stamp `session_date` and
   `calendar_id` on each produced `DAY_1` bar before upsert.
4. At `sync_jobs.py:413`, resolve the calendar for `ts.symbol` through
   `SymbolCalendarResolver` (obtain it with `await container.get(SymbolCalendarResolver)`
   near the other `container.get` calls in that function) and pass it.
5. At `tracked_symbols_backfill.py:176`, do the same. `TrackedSymbolBackfillService`
   is DI-constructed, so add `calendar_resolver: SymbolCalendarResolver` to its
   `__init__` (line 86) and store it.
6. `CASCADE_TFS` at lines 32-38 stays as is — 1w is still not cascaded, and the
   rationale comment at `sync_jobs.py:51-53` remains correct.
7. Update `tests/app_test/market_data/test_cascade_aggregator.py` (lines 143-262) and
   `tests/app_test/market_data/test_sync_source_labels.py` (lines 50, 169) to pass
   `calendar=CONTINUOUS_24X7`.

**Success criteria.** With `CONTINUOUS_24X7`, boundaries and expected counts are
identical to the committed golden fixture.

**Verify.** `uv run pytest tests/app_test/market_data/ -q` exits 0 and reports
`0 failed`, and the golden test is among the passing tests when run with `-v`.

### Task 3.4 — Calendar-aware integrity grid

**Goal.** Weekends, maintenance halts and holidays stop being reported as gaps, so
`sync_repair` cannot thrash.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` — `check_integrity` (36-76), `repair_integrity` (79-...)
- `src/pocketquant/app/routes/integrity.py:33,45`
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:302,347`

**Steps.**
1. `check_integrity(symbol, interval, bar_repo, days_back=7, *, calendar)` gains the
   required keyword-only calendar.
2. Replace line 51 `end = get_bar_start(now, interval)` with
   `end = calendar.bar_start(now, interval)`; `now` is already aware after Phase 1
   Task 1.2.
3. Replace line 57 `is_bar_aligned(d["datetime"], interval)` with
   `is_bar_aligned(d["datetime"], interval, calendar=calendar)`.
4. Replace the arithmetic grid at lines 62-63. For `Interval.MINUTE_1` use
   `expected = set(calendar.trading_minutes(start, end))`. For `DAY_1` and `WEEK_1`
   use `expected = {calendar.session_open(d) for d in calendar.sessions(start, end)}`
   (for `WEEK_1`, keep only the first session of each ISO week). For the remaining
   intraday intervals use `expected = set(calendar.bucket_starts(interval, start, end))`.
5. Update the docstring at lines 46-47: delete the "only reliable for 24/7 markets"
   note and state that the expected set comes from the calendar, so session-based
   instruments are handled without special-casing.
6. `repair_integrity` gains the same required keyword-only calendar and forwards it
   at lines 92 and 119. Add an early return for
   `interval is Interval.WEEK_1 and calendar.calendar_id != "CRYPTO_24_7"`, returning
   a report with `skipped="weekly_convention_pending"` and logging one DEBUG line —
   there is no weekly convention for a session calendar yet and a repair would
   resync 5000 bars pointlessly.
7. At `routes/integrity.py:33,45`, inject `FromDishka[SymbolCalendarResolver]` into
   both route functions (the router already uses `DishkaRoute`), resolve the
   calendar for the validated symbol, and pass it.
8. At `sync_jobs.py:302,347`, resolve through the resolver already fetched from the
   container in those job bodies and pass it.
9. Update `tests/app_test/market_data/test_sync_source_labels.py:82` to pass
   `calendar=CONTINUOUS_24X7`.

**Success criteria.** For a dense crypto 1m series, `missing_count` is identical to
the pre-change value; `check_integrity` on a hypothetical CME calendar over a
weekend reports `missing_count == 0`.

**Verify.** `uv run pytest tests/app_test/market_data/test_sync_source_labels.py tests/app_test/integration/test_sync_backfill_gap_fill.py -q`
exits 0 with `0 failed`.

### Task 3.5 — Calendar-aware freshness and the `is_market_open` DTO field

**Goal.** A closed market reads as "closed", not "stuck", and emits no per-minute
WARNs.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_status_service.py:62-69` — `_is_stuck`; `SyncStatusResult` (46-58); `get_sync_status` (117-...)
- `src/pocketquant/engine/market_data/sync_internals/anomaly_log.py:20-61` — `emit_no_progress`
- `src/pocketquant/engine/market_data/sync_service.py:100-111` — the `emit_no_progress` call
- `web/src/types/market-data.ts:79-89` — `SyncStatus`
- `web/src/components/monitor/data-health-row.tsx:50-72`, `web/src/components/monitor/format-helpers.ts:19`

**Steps.**
1. Change `_is_stuck(latest_bar_dt, interval, *, calendar)` to measure age against
   the last expected bar close rather than `now`:
   `reference = calendar.previous_close(datetime.now(UTC))` then
   `age = (reference - latest_bar_dt).total_seconds()`. For the 24/7 calendar,
   `previous_close` returns `now` (Phase 2 Task 2.4 step 2), so crypto behaviour is
   byte-identical.
2. Add `is_market_open: bool = True` to the `SyncStatusResult` dataclass after
   `is_stuck` (line 57).
3. In `get_sync_status`, resolve the calendar per status row through
   `SymbolCalendarResolver` (add it to `SyncStatusQueryService.__init__` at line 49
   and to its Dishka provider) and populate both `is_stuck=` and
   `is_market_open=calendar.is_open(datetime.now(UTC))` in the `SyncStatusResult(...)`
   construction at lines 122-132.
4. In `emit_no_progress`, add a required keyword-only `calendar` parameter and make
   the FIRST statement:
   ```python
   if not calendar.is_open(datetime.now(UTC)):
       logger.debug("market_data.sync.skipped_closed", symbol=symbol, interval=interval.value)
       return
   ```
   DEBUG, not WARNING — this fires once per symbol per minute while the market is
   closed, which is exactly the frequency the CLAUDE.md log rule forbids above DEBUG.
5. Also compute `age_s` (line 36-40) against `calendar.previous_close(datetime.now(UTC))`
   instead of `datetime.now(UTC)`.
6. At `sync_service.py:102`, pass `calendar=calendar` (already resolved in Task 3.2
   step 5).
7. Add `is_market_open?: boolean` to the `SyncStatus` interface in
   `web/src/types/market-data.ts`.
8. In `data-health-row.tsx`, when `s.is_market_open === false`, render a neutral
   "Closed" badge instead of the stuck badge at line 72 and suppress the
   `ageColorClass` staleness colouring at line 68 by using `'age-neutral'`. In
   `format-helpers.ts:19`, return `'neutral'` before the `s.is_stuck` check when
   `s.is_market_open === false`.
9. Do NOT change `web/src/lib/datetime.ts:88-97` (`ageColorClass`). It is a pure
   elapsed-time helper; gating happens at the call site, which keeps the helper
   reusable and avoids threading market state through the display layer.

**Success criteria.** With the 24/7 calendar, `_is_stuck` and `emit_no_progress`
produce identical output to today; with a closed calendar, `emit_no_progress`
returns before logging at WARNING.

**Verify.** `uv run pytest tests/app_test/unit/handlers/status/test_sync_status_service.py tests/app_test/unit/handlers/sync/test_no_progress_tracking.py -q`
exits 0 with `0 failed`. Then `cd web && npx tsc --noEmit` exits 0.

### Task 3.6 — Move annualization onto the calendar

**Goal.** The `Interval` enum stops owning a calendar it does not know about.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py:3-13,25-40` — `_PERIODS_PER_YEAR`, `Interval.periods_per_year`, `Interval.periods_per_year_for`
- `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:13-14` — `TRADING_DAYS_PER_YEAR`
- `src/pocketquant/engine/backtest/backtest_report_app_service.py:368-373`
- `tests/core_test/unit/domain/shared/test_interval.py:35-62`
- `tests/backtest_test/domain/test_performance_calculator_annualization.py:65`

**Steps.**
1. Delete `_PERIODS_PER_YEAR` (lines 3-13), the `periods_per_year` property
   (lines 25-31) and the `periods_per_year_for` static method (lines 33-40) from
   `core/domain/shared/enums.py`. Their values now live in
   `Continuous24x7Calendar.periods_per_year` (Phase 2 Task 2.4 step 7).
2. At `backtest_report_app_service.py:368`, replace
   `periods_per_year = Interval.periods_per_year_for(self._config.interval)` with a
   calendar lookup: resolve the calendar for `self._config.symbol` and call
   `calendar.periods_per_year(Interval(self._config.interval))`, guarded so an
   unknown interval string still yields `None` and keeps the existing WARNING at
   lines 369-373. `BacktestReportAppService` is constructed inside the backtest
   engine, so pass the resolved calendar into its constructor rather than injecting
   a repository — the backtest layer must not gain a repository dependency
   (CLAUDE.md: all repositories in core, zero repos in backtest).
3. `TRADING_DAYS_PER_YEAR = 365` at `performance_calculator_domain_service.py:14` is
   used only at line 52 (`years = days / TRADING_DAYS_PER_YEAR`) for CAGR over a
   wall-clock window. That is a calendar-year conversion, not a bar-count
   annualization, so it is CORRECT as 365 for every asset class. Leave it, and
   replace its comment with one line saying so, to stop a future reader "fixing" it.
4. Update the docstrings at `performance_calculator_domain_service.py:81` and `:129`
   that still say "(Interval.periods_per_year)" to say
   "(ITradingCalendarPort.periods_per_year)".
5. Move the parametrised expectations from
   `tests/core_test/unit/domain/shared/test_interval.py:35-62` into the new
   `tests/core_test/unit/domain/market_data/test_continuous_24x7_calendar.py`
   (Phase 2 Task 2.11 step 7 already asserts equality; now make it the only home).
   Delete lines 35-62 from `test_interval.py`, keeping the `TestInterval` class.
6. Update `tests/backtest_test/domain/test_performance_calculator_annualization.py:65`
   to use `CONTINUOUS_24X7.periods_per_year(Interval.MINUTE_1)`.

**Success criteria.** `Interval` has no annualization member; crypto
`periods_per_year` at 1m is still 525600.

**Verify.** `uv run pytest tests/core_test/unit/domain/ tests/backtest_test/ -q`
exits 0 with `0 failed`, and
`uv run python -c "from pocketquant.core.domain.shared.enums import Interval; print(hasattr(Interval.MINUTE_1,'periods_per_year'))"`
prints exactly `False`.

### Task 3.7 — Gate the sync cron on the calendar

**Goal.** While a market is closed, the cron does not call the provider at all.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:130-200` — `_sync_by_intervals`

**Steps.**
1. Inside the `for symbol in symbols:` loop at line 164, before the inner
   `for interval in intervals:` loop, resolve
   `calendar = await calendar_resolver.for_symbol(symbol)`.
2. Skip the symbol when the market is closed with one interval of grace after the
   close, so the final bar of a session still gets fetched:
   ```python
   now = datetime.now(UTC)
   grace = timedelta(seconds=INTERVAL_SECONDS[max(intervals, key=lambda i: INTERVAL_SECONDS[i])])
   if not calendar.is_open(now) and now - calendar.previous_close(now) > grace:
       logger.debug("market_data.sync.symbol_skipped_closed", symbol=symbol, job=job_name)
       continue
   ```
   DEBUG because this fires per symbol per minute all weekend.
3. Record the skip in job history so the weekend-quiet success metric is
   observable: call `history_repo.record_detail(doc_id, symbol=symbol, interval="*", status="skipped_closed", bars_fetched=0, bars_inserted=0, filtered_existing=0, filtered_misaligned=0, error=None)`
   once per skipped symbol when `doc_id` is set, mirroring the existing
   `record_detail` call at lines 178-188.
4. Obtain `calendar_resolver` by adding it as a parameter to `_sync_by_intervals`
   and resolving it from the container in each of the three job bodies that call it
   (`sync_jobs.py:253` and `:398`, plus any other call site the grep finds).
5. For a calendar-based asset class, `DAY_1` and `WEEK_1` must be fetched natively
   from the provider rather than cascaded. `SYNC_INTERVALS` (lines 54-62) already
   includes both and `CASCADE_TFS` already excludes `WEEK_1`; the only change needed
   is to exclude `DAY_1` from the cascade when
   `calendar.calendar_id != "CRYPTO_24_7"`. Do this at `sync_jobs.py:413` by
   filtering the `CASCADE_TFS` list passed into `cascade_for_symbol`. Update the
   comment at lines 51-53 to explain both cases.

**Success criteria.** With the 24/7 calendar, `is_open` is always `True`, so no
symbol is ever skipped and crypto behaviour is unchanged.

**Verify.** `uv run pytest tests/app_test/test_sync_jobs_phase.py tests/app_test/unit/market_data/ -q`
exits 0 with `0 failed`.

### Task 3.8 — Phase gate

**Goal.** Crypto is provably byte-identical and one production cron cycle matches
the pre-change cycle.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates plus `just test-tz`.
2. Confirm the golden fixture is unmodified:
   `git diff --exit-code tests/app_test/market_data/fixtures/golden_cascade_btcusdt.json`.
3. Deploy and let one full `sync_1m` plus one `sync_verify_cascade` cycle run on the
   VPS. Compare `synced_count` per symbol and the resulting bar values against the
   equivalent cycle from before the deploy. Record both in the phase notes.
4. Confirm `periods_per_year` for crypto at 1m is still 525600 in a fresh backtest
   report.

**Success criteria.** All gates pass, the fixture is untouched, and the production
cycle is identical.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors, 0 warnings, 0 informations`;
`git diff --exit-code tests/app_test/market_data/fixtures/` exits 0. All five exit 0.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A calendar-aware rewrite silently changes a crypto bucket | Medium | High — corrupts stored bars | Task 3.1 commits the golden fixture before any edit; the gate refuses a modified fixture |
| Required-kwarg churn leaves a call site missed | Medium | Low | A missed site is a `TypeError` the 669-test suite catches immediately, by design |
| The suite is red between Task 3.2 and Task 3.4 | High | Low | Stated explicitly in 3.2 step 7; do not patch it with `CONTINUOUS_24X7` |
| `previous_close` on the 24/7 calendar changes `_is_stuck` semantics | Low | Medium | It returns `now`, so the expression is arithmetically identical; covered by `test_sync_status_service.py` |
| Deleting `Interval.periods_per_year` breaks an unfound caller | Low | Medium | Only production caller is `backtest_report_app_service.py:368` (grep-verified); pyright catches the rest |
| Backtest layer gains a repository dependency via the calendar | Medium | High — violates CLAUDE.md | Task 3.6 step 2 passes a resolved calendar into the constructor, never a repository |

## Rollback

This phase changes signatures across domain, engine and app. Roll back as a whole
with `git revert` of the phase commit range; partial rollback will leave callers
mismatched. The only persisted change is `session_date` / `calendar_id` on newly
written 1d and 1w bars, which are additive optional fields that older code ignores.

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

=== FILE: phase-04-provider-routing-and-settings.md ===
---
phase: 4
title: "Provider routing adapters and settings"
status: pending
priority: P1
effort: "8h"
dependencies: [3]
---

# Phase 4: Provider routing adapters and settings

Maps to advice Phase 3.

## Context

Today DI binds exactly one implementation of each port:
`app/di/infrastructure.py:29-31` returns `BinanceAdapter(settings=settings)` for
`IDataProviderPort`, and `app/di/market_data.py:34-36` returns
`BinanceWebSocketAdapter()` for `IRealtimeQuoteProviderPort`.

This phase replaces both bindings with routing adapters that implement the same
ports and dispatch per symbol. Because the ports are unchanged, `SyncService`,
`fetch_with_retry`, `WsSubscriptionAppService` and `QuoteAppService` need no edits
— that is exactly G4. This phase ships with Binance as the ONLY registered
provider and proves the crypto path is unchanged, so any later regression is
attributable to the TradingView adapter rather than to routing.

`IRealtimeQuoteProviderPort` is a 9-member `Protocol`
(`realtime_quote_provider_port.py:15-58`): `last_tick_at`, `connect`,
`disconnect`, `subscribe`, `unsubscribe`, `run_forever`, `is_connected`,
`subscription_count`, `subscriptions`. The routing realtime provider must expose
all nine to satisfy the `@runtime_checkable` isinstance checks.

## Tasks

### Task 4.1 — Provider settings

**Goal.** The asset-class-to-provider map and per-symbol overrides are config, not
code.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — `Settings`, after `reconcile_interval_seconds` (line 74)

**Steps.**
1. Add to `Settings`:
   ```python
   # Market-data provider routing. JSON in env, e.g.
   #   MARKET_DATA_PROVIDERS={"crypto_spot":["binance"],"index_future":["tradingview"]}
   #   SYMBOL_PROVIDER_OVERRIDES={"ES1!:CME_MINI":["tradingview"]}
   # Ordered lists: first is primary, the rest are REST-only fallbacks.
   market_data_providers: dict[str, list[str]] = Field(
       default_factory=lambda: {"crypto_spot": ["binance"], "crypto_perp": ["binance"]}
   )
   symbol_provider_overrides: dict[str, list[str]] = Field(default_factory=dict)
   ```
2. Import `Field` from `pydantic` in `config.py`.
3. pydantic-settings parses a JSON object from the env string automatically for
   `dict` fields; do not hand-roll a parser.
4. Key the outer dict by `AssetClass` *value strings* rather than the enum, so an
   unknown key in a deployed `.env` produces a clear runtime `KeyError` naming the
   key instead of a settings-load failure that blocks boot.
5. Document both variable names in `README.md` under the Configuration list and in
   `docs/system-architecture.md:775` ("Env vars"). Values go only into
   `../pocketquant-config/vps/default/.env` and
   `../pocketquant-config/local/all-local.env`.

**Success criteria.** `get_settings().market_data_providers["crypto_spot"] == ["binance"]`
with no env override; setting the env var replaces it.

**Verify.** `MARKET_DATA_PROVIDERS='{"index_future":["tradingview"]}' uv run python -c "from pocketquant.core.config import Settings; import os; print(Settings().market_data_providers)"`
exits 0 and its output contains `'index_future': ['tradingview']`.

### Task 4.2 — `RoutingDataProvider`

**Goal.** REST history fetches resolve a provider per symbol and fall through an
ordered list on failure.

**Target files and symbols.**
- `src/pocketquant/core/infra/market_data/__init__.py` (new)
- `src/pocketquant/core/infra/market_data/provider_resolver.py` (new) — `ProviderResolver`
- `src/pocketquant/core/infra/market_data/routing_data_provider.py` (new) — `RoutingDataProvider`

**Steps.**
1. `ProviderResolver.__init__(self, settings: Settings, symbol_repository: SymbolRepository)`.
   `async def provider_ids(self, symbol: str) -> list[str]` returns
   `settings.symbol_provider_overrides[symbol]` when present, else
   `settings.market_data_providers[<the symbol's asset_class value>]`. When the
   symbol record is missing, fall back to the `crypto_spot` list and log one DEBUG
   line. Cache with `cachetools.TTLCache(maxsize=512, ttl=300)` for the same reason
   given in Phase 2 Task 2.6 step 3.
2. `RoutingDataProvider(IDataProviderPort).__init__(self, adapters: dict[str, IDataProviderPort], resolver: ProviderResolver)`.
3. `fetch_ohlcv(symbol, interval, n_bars)`: iterate the resolved ids in order; for
   each, look the adapter up (raise `KeyError` naming an unregistered id), call it,
   and return on a non-empty result. On an exception or an empty list, log one
   WARNING `market_data.provider.fallback` with `symbol`, `interval`,
   `failed_provider`, `next_provider` and continue. After the last id, return `[]`
   and log one WARNING `market_data.provider.exhausted`. WARNING is correct here:
   it is a degraded condition and it is bounded by one line per failed provider per
   sync, not per bar.
4. `search_symbols(query)`: fan out to every registered adapter with
   `asyncio.gather(..., return_exceptions=True)`, concatenate successful results,
   drop exceptions with one DEBUG line each. Search has no per-symbol context, so
   there is nothing to resolve.
5. `close()`: `await` every registered adapter's `close()`, suppressing individual
   exceptions so one bad adapter cannot block shutdown.
6. Add a module docstring stating that fallback exists for REST history only,
   where "try the next one" is cheap and idempotent.

**Success criteria.** With one registered adapter, every call reaches it and the
returned bars are identical to calling `BinanceAdapter` directly. With two adapters
where the first raises, the second is used and exactly one WARNING is logged.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_routing_data_provider.py -q`
exits 0 and reports `0 failed` after Task 4.5 writes it.

### Task 4.3 — `RoutingRealtimeQuoteProvider`

**Goal.** Realtime subscriptions are delegated to the right child provider, with
NO fallback.

**Target files and symbols.**
- `src/pocketquant/core/infra/market_data/routing_realtime_quote_provider.py` (new) — `RoutingRealtimeQuoteProvider`

**Steps.**
1. `__init__(self, adapters: dict[str, IRealtimeQuoteProviderPort], resolver: ProviderResolver)`.
   Keep `self._symbol_provider: dict[str, str]` mapping composite symbol to the id
   that owns its subscription.
2. `subscribe(symbol, callback)`: resolve the ids, take the FIRST one only, record
   the mapping, and delegate. Add a load-bearing comment: realtime must never use
   the fallback chain, because two providers streaming the same symbol would
   double-count ticks in `BarBuilderDomainService.add_tick`.
3. `unsubscribe(symbol)`: look the owning id up, delegate, and delete the mapping.
   A symbol with no recorded owner is a no-op.
4. `connect()` / `disconnect()`: `asyncio.gather` over every child.
5. `run_forever()`: `await asyncio.gather(*(a.run_forever() for a in adapters.values()))`.
   With one registered adapter this is behaviourally identical to today.
6. `is_connected()`: `all(a.is_connected() for a in adapters.values())` when at least
   one adapter exists, else `False`.
7. `subscription_count` property: `sum(a.subscription_count for a in adapters.values())`.
   `subscriptions` property: merged dict across children.
8. `last_tick_at`: a property returning the maximum non-`None` `last_tick_at` across
   children, or `None`. Note in a comment that the Protocol declares it as a plain
   attribute; a read-only property satisfies structural subtyping for every read
   site, and `WsSubscriptionAppService` and `QuoteAppService` only read it.
9. Assert at import time in the module's test (Task 4.5) that
   `isinstance(RoutingRealtimeQuoteProvider(...), IRealtimeQuoteProviderPort)` is
   `True`, because the Protocol is `@runtime_checkable` and DI relies on it.

**Success criteria.** All nine Protocol members are present; `isinstance` against
the Protocol returns `True`; one registered adapter yields identical behaviour.

**Verify.** `uv run pytest tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py -q`
exits 0 with `0 failed`.

### Task 4.4 — Swap the DI bindings, Binance-only

**Goal.** The container serves the routing adapters while only Binance is
registered.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py:29-31` — `get_data_provider`
- `src/pocketquant/app/di/market_data.py:34-36` — `get_realtime_quote_provider`

**Steps.**
1. In `app/di/infrastructure.py`, add `@provide(scope=Scope.APP)` for
   `get_provider_resolver(self, settings: Settings, symbol_repository: SymbolRepository) -> ProviderResolver`.
2. Change `get_data_provider` to build and return
   `RoutingDataProvider(adapters={"binance": BinanceAdapter(settings=settings)}, resolver=resolver)`.
   Keep the return annotation `-> IDataProviderPort` unchanged so every consumer
   resolves the same type.
3. In `app/di/market_data.py`, change `get_realtime_quote_provider` to return
   `RoutingRealtimeQuoteProvider(adapters={"binance": BinanceWebSocketAdapter()}, resolver=resolver)`,
   keeping the `-> IRealtimeQuoteProviderPort` annotation and the existing
   `# type: ignore[return-value]` comment style.
4. Do NOT edit `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService`,
   `QuoteAppService` or any route. If any of them needs a change, the routing
   adapters do not satisfy the ports and the Failure Protocol applies.
5. Register the adapter dict from a single module-level factory so Phase 5 adds
   TradingView by appending one entry rather than editing two DI files.

**Success criteria.** The container resolves both ports; the app boots; crypto
sync, cascade and quotes behave identically.

**Verify.** `uv run pytest tests/app_test/integration/test_app_standalone_runtime.py -q`
exits 0 with `0 failed`, and
`git diff --stat HEAD~1 -- src/pocketquant/engine src/pocketquant/app/routes` produces
no output.

### Task 4.5 — Routing tests including the G4 proof

**Goal.** G4 is demonstrated: a third provider is registered through config alone
with zero caller edits.

**Target files and symbols.**
- `tests/core_test/infra/market_data/test_routing_data_provider.py` (new)
- `tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py` (new)
- `tests/core_test/infra/market_data/test_provider_resolver.py` (new)

**Steps.**
1. Resolver tests: a symbol whose record carries `asset_class=index_future` resolves
   to the `index_future` list; a symbol present in `symbol_provider_overrides`
   resolves to the override regardless of asset class; a missing symbol record
   resolves to the `crypto_spot` list.
2. Fallback test: two stub adapters, the first raising `RuntimeError`; assert the
   second one's result is returned and exactly one
   `market_data.provider.fallback` WARNING was emitted (capture with `caplog`).
3. Empty-result fallback test: the first adapter returns `[]`; assert the second is
   tried.
4. Exhaustion test: both adapters fail; assert `fetch_ohlcv` returns `[]` and does
   not raise, because `SyncService.sync_one` at line 86-87 already handles the
   empty case by marking the sync failed.
5. G4 test named `test_third_provider_needs_only_config`: register a
   `_MockThirdProvider` stub in the adapters dict and set
   `symbol_provider_overrides={"FAKE1!:MOCKEX": ["mock_third"]}`; assert the mock
   received the `fetch_ohlcv` call. Add a docstring stating the G4 criterion: this
   test touches no file under `engine/` or `app/`.
6. Protocol test: `isinstance(RoutingRealtimeQuoteProvider(...), IRealtimeQuoteProviderPort)`
   is `True`; `subscribe` then `unsubscribe` leaves `subscription_count == 0`;
   `subscribe` on a symbol whose list has two ids delegates only to the first.

**Success criteria.** Every listed test passes and the G4 test's diff touches only
`tests/`.

**Verify.** `uv run pytest tests/core_test/infra/market_data/ -q` exits 0 and
reports `0 failed`, and running with `-v` shows `test_third_provider_needs_only_config`
as passed.

### Task 4.6 — Phase gate

**Goal.** Routing is transparent on the crypto path in production.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates.
2. Deploy and let one full `sync_1m` cycle plus one `sync_verify_cascade` run.
   Compare `synced_count` per symbol against the equivalent pre-deploy cycle.
3. Confirm the WS feed reconnects and `subscription_count` matches the tracked
   symbol count.
4. Confirm no `market_data.provider.fallback` or `market_data.provider.exhausted`
   line appears during a healthy cycle.

**Success criteria.** All gates pass; the production cycle is identical; zero
fallback lines.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors, 0 warnings, 0 informations`. All four exit 0.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `RoutingRealtimeQuoteProvider` fails the runtime Protocol check | Medium | High — DI resolution breaks at boot | Task 4.5 step 6 asserts `isinstance` explicitly |
| `last_tick_at` as a property breaks a writer | Low | Medium | Grep confirms `WsSubscriptionAppService` and `QuoteAppService` only read it; `BinanceWebSocketAdapter` writes its own at `:116,197` |
| Fallback masks a real provider outage | Medium | Medium | One WARNING per fallback plus one on exhaustion; Phase 7 surfaces per-provider status on `/health` |
| Realtime double-subscription double-counts ticks | Low | High — corrupts built bars | Realtime takes the first id only; Task 4.3 step 2 makes this explicit and Task 4.5 step 6 tests it |
| An unregistered provider id in `.env` crashes a sync | Medium | Medium | `KeyError` names the id; the sync marks that symbol failed rather than taking the process down |

## Rollback

Revert the two DI provider methods to return the concrete Binance adapters. The
routing modules are additive and inert when unreferenced. No schema or persisted
state changes in this phase.

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
title: "TradingView history adapter, seeding and backfill"
status: pending
priority: P1
effort: "16h"
dependencies: [4]
---

# Phase 5: TradingView history adapter, seeding and backfill

Maps to advice Phase 4.

## Context

The first phase that introduces a futures symbol. The scraper library is isolated
behind an internal client interface so it can be swapped without touching the
adapter, the mappers or any caller — that is the exit route recorded in the
advice's trade-off section.

Two verified constraints shape the mapper:

- `tvdatafeed` builds its DataFrame timestamps with naive LOCAL time at
  `tvDatafeed/main.py:143`. The mapper MUST build every `Bar.datetime` from the
  raw epoch field with `datetime.fromtimestamp(ts, tz=UTC)` and never read the
  DataFrame index.
- `LIMIT_TVDATAFEED_MAX_BARS = 5000` at `core/common/constants.py:35` and the
  backfill docstring are fossils of an earlier migration AWAY from this library.
  `sync_dtos.py:9,22,24,51,53` still uses the constant as a generic request cap.
  Do not repurpose it as the TradingView entitlement cap — that is
  `settings.tradingview_max_bars`, so the two can diverge when the user upgrades.

Never branch on TradingView plan tier. The bar cap, the delay flag and the
credentials are settings (R4).

## Tasks

### Task 5.1 — TradingView settings

**Goal.** Credentials and entitlement are configuration whose values never enter
this repository.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — `Settings`, after the provider-routing fields from Phase 4 Task 4.1

**Steps.**
1. Add:
   ```python
   # TradingView (values live only in ../pocketquant-config — never in this repo)
   tradingview_username: str | None = None
   tradingview_password: SecretStr | None = None
   tradingview_auth_token: SecretStr | None = None
   tradingview_max_bars: int = 5000        # plan entitlement; raise, never branch on tier
   tradingview_poll_seconds: float = 60.0  # Phase 6; delayed CME data cannot change faster
   tradingview_delayed_data: bool = True
   ```
   `SecretStr` is already imported at `config.py:6`.
2. Document the six field names (names only, never values) in `README.md` under the
   Configuration list.
3. Put the actual values in `../pocketquant-config/vps/default/.env` and
   `../pocketquant-config/local/all-local.env`.
4. Add a comment above the block: the poll cadence default is 60s because CME data
   is 10-minute delayed on every plan until the non-professional add-on is bought,
   so polling faster only raises ban risk without improving freshness.

**Success criteria.** The settings load with all six absent; `SecretStr` values do
not appear in `repr()` or in logs.

**Verify.** `uv run python -c "from pocketquant.core.config import Settings; s=Settings(); print(s.tradingview_max_bars, s.tradingview_password)"`
prints `5000 None` and exits 0. Then `git grep -iE "tradingview_(username|password|auth_token)\s*=\s*[\"'][^\"']+" -- ':!*.md'`
produces no output.

### Task 5.2 — The internal TradingView client interface

**Goal.** The scraper library has exactly one import site in the codebase.

**Target files and symbols.**
- `src/pocketquant/core/infra/tradingview/__init__.py` (new)
- `src/pocketquant/core/infra/tradingview/tradingview_client.py` (new) — `ITradingViewClient`, `RawBar`

**Steps.**
1. Define a frozen dataclass `RawBar` with `epoch_seconds: int`, `open: float`,
   `high: float`, `low: float`, `close: float`, `volume: float`. It carries an
   epoch integer, never a `datetime`, so no naive value can enter the system
   through this boundary.
2. Define `class ITradingViewClient(Protocol):` with
   `async def fetch_bars(self, *, code: str, exchange: str, interval: Interval, n_bars: int, fut_contract: int | None) -> list[RawBar]: ...`
   and `def is_authenticated(self) -> bool: ...`.
3. Add a module docstring stating the swap contract: replacing the scraper means
   one new class implementing this Protocol plus one DI line, with no change to the
   adapter, the mappers or any caller.

**Success criteria.** The Protocol imports without pulling in any third-party
scraper module.

**Verify.** `uv run python -c "import pocketquant.core.infra.tradingview.tradingview_client as m; import sys; print('tvDatafeed' not in sys.modules)"`
prints exactly `True` and exits 0.

### Task 5.3 — `TvDatafeedClient`

**Goal.** The synchronous, thread-based library runs without blocking the event
loop, and a login failure degrades rather than crashing.

**Target files and symbols.**
- `pyproject.toml` — `dependencies`
- `src/pocketquant/core/infra/tradingview/tvdatafeed_client.py` (new) — `TvDatafeedClient`

**Steps.**
1. Add the scraper to `dependencies` in `pyproject.toml` and run `uv sync`. Use the
   maintained fork the advice names: `tvdatafeed` from
   `https://github.com/rongardF/tvdatafeed` — declare it as a git dependency with a
   pinned commit or tag, never an unpinned `main`, because the advice records
   recurring breakage. Record the pin in `docs/system-architecture.md` under
   Dependencies in Phase 7.
2. `TvDatafeedClient.__init__(self, settings: Settings)` constructs the library
   object lazily on first use inside `asyncio.to_thread`, because construction
   performs the login HTTP round trip.
3. Login: when `tradingview_username` and `tradingview_password` are both set,
   attempt an authenticated session. On any exception, log ONE WARNING
   `provider.tradingview.auth_degraded` with the exception class name only (never
   the credential values), set `self._authenticated = False`, and fall back to the
   library's anonymous mode. Never re-raise — a login failure must not take the
   process down.
4. `is_authenticated()` returns `self._authenticated`.
5. `fetch_bars(...)` calls the library's `get_hist` inside
   `await asyncio.to_thread(...)`, passing `symbol=code`, `exchange=exchange`,
   `interval=<mapped>`, `n_bars=n_bars` and `fut_contract=fut_contract`. Convert
   the returned DataFrame to `list[RawBar]` by reading the epoch from the index's
   underlying int64 values (`df.index.view("int64") // 10**9`), NOT from the
   library's constructed `datetime` objects.
6. Log one DEBUG `provider.tradingview.fetched` per call with `code`, `interval` and
   row count. DEBUG because this is per-symbol per-interval per-cron-cycle. Never
   log the DataFrame.
7. Add a load-bearing comment on the epoch extraction citing
   `tvDatafeed/main.py:143` as the reason.

**Success criteria.** A fetch returns `RawBar` objects whose `epoch_seconds` match
the exchange's UTC instants regardless of the host `TZ`; a login failure logs one
WARNING and leaves the client usable.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tvdatafeed_client.py -q`
exits 0 with `0 failed` (Task 5.6 writes it against a stubbed library object; no
network access is required).

### Task 5.4 — TradingView mappers

**Goal.** Symbol, interval and bar translation is pure and testable offline.

**Target files and symbols.**
- `src/pocketquant/core/infra/tradingview/tradingview_mappers.py` (new) — `split_composite`, `to_tv_interval`, `raw_bar_to_bar`

**Steps.**
1. `split_composite(symbol: str) -> tuple[str, str, int | None]` splits
   `ES1!:CME_MINI` into `("ES", "CME_MINI", 1)`. The rule: when the code ends with
   `N!` (a digit followed by `!`), strip the suffix and return that digit as
   `fut_contract`; otherwise return the code unchanged and `None`. Raise
   `ValueError` naming the input when there is no `:`.
2. `to_tv_interval(interval: Interval) -> <library interval enum>` maps all seven
   members. Keep the mapping as an explicit dict so an unmapped interval raises
   `KeyError` rather than silently defaulting.
3. `raw_bar_to_bar(raw: RawBar, symbol: str, interval: Interval) -> Bar` builds
   `datetime=datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)` and sets
   `tick_count=0`, `source=None` (the sync pipeline stamps the source). Mirror the
   shape of `binance_mappers.kline_to_bar` at `binance_mappers.py:38-70`.
4. Add a load-bearing comment on the `tz=UTC` argument: the library's own timestamps
   are naive local (`tvDatafeed/main.py:143`), so the epoch is the only trustworthy
   field.

**Success criteria.** `split_composite("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)`;
`split_composite("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)`;
`raw_bar_to_bar` produces the same `Bar.datetime` under every host `TZ`.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q`
exits 0 with `0 failed`.

### Task 5.5 — `TradingViewAdapter`

**Goal.** A second `IDataProviderPort` implementation that the routing layer can
register without any caller change.

**Target files and symbols.**
- `src/pocketquant/core/infra/tradingview/tradingview_adapter.py` (new) — `TradingViewAdapter`

**Steps.**
1. `TradingViewAdapter(IDataProviderPort).__init__(self, client: ITradingViewClient, settings: Settings, calendar_resolver: SymbolCalendarResolver)`.
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - clamp `n_bars` to `min(n_bars, settings.tradingview_max_bars)` and log one
     DEBUG `provider.tradingview.clamped` when clamping occurs;
   - `code, exchange, fut_contract = split_composite(symbol)`;
   - `raws = await client.fetch_bars(...)`;
   - map each with `raw_bar_to_bar`;
   - resolve the calendar for the symbol and drop the in-progress bar: keep only
     bars whose `datetime` is strictly before `calendar.bar_start(datetime.now(UTC), interval)`.
     This mirrors the Binance cutoff logic fixed in Phase 1 Task 1.6 and reuses the
     same alignment source, so the two can never disagree;
   - return the list in ascending `datetime` order.
3. `search_symbols(query)`: call the client's search if the library exposes one;
   otherwise return `[]` and log one DEBUG line. Do not raise — `RoutingDataProvider.search_symbols`
   fans out and tolerates empty results.
4. `close()`: release the client's session if it holds one; otherwise a no-op.
5. Never inspect `settings.tradingview_delayed_data` or any plan-tier notion to
   choose behaviour. The flag exists only so the UI can badge the data in Phase 7.
6. Register the adapter in the routing adapter dict from Phase 4 Task 4.4 step 5
   under the id `"tradingview"`, and add
   `"index_future": ["tradingview"]` to `MARKET_DATA_PROVIDERS` in both config-repo
   env files.

**Success criteria.** Every returned `Bar` has an aware UTC `datetime`, the count
never exceeds `tradingview_max_bars`, and the in-progress bar is absent.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_adapter.py -q`
exits 0 with `0 failed`.

### Task 5.6 — Offline-fixture test suite

**Goal.** The adapter pair is fully tested with no network access.

**Target files and symbols.**
- `tests/core_test/infra/tradingview/fixtures/es1_1h_raw.json` (new)
- `tests/core_test/infra/tradingview/test_tradingview_mappers.py` (new)
- `tests/core_test/infra/tradingview/test_tradingview_adapter.py` (new)
- `tests/core_test/infra/tradingview/test_tvdatafeed_client.py` (new)

**Steps.**
1. Create `es1_1h_raw.json`: 48 rows of plausible ES 1h data spanning the
   2026-03-08 spring-forward session, each row `{"epoch_seconds": ..., "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}`.
   Include the session open at epoch `1772661600` (`2026-03-08T22:00:00Z`) so the
   DST case is exercised end to end. Use no credentials and no real API capture.
2. Mapper tests: `split_composite` for `ES1!:CME_MINI`, `NQ1!:CME_MINI`,
   `YM1!:CBOT_MINI` and `BTCUSDT:BINANCE`; a malformed input raising `ValueError`;
   `raw_bar_to_bar` producing `datetime(2026, 3, 8, 22, tzinfo=UTC)` for the fixture's
   first row under all three host zones; `to_tv_interval` covering all seven
   `Interval` members and raising `KeyError` on a fabricated one.
3. Adapter tests with a `_StubTradingViewClient` returning the fixture: the clamp
   applies when `n_bars > tradingview_max_bars`; the in-progress bar is dropped when
   `datetime.now(UTC)` is frozen inside the last fixture bar; results are ascending;
   every `datetime` is aware UTC.
4. Client test: stub the library object so `get_hist` returns a small DataFrame with
   a known int64 index; assert `fetch_bars` reads the epoch from the index and not
   from any constructed `datetime`; assert a login exception produces
   `is_authenticated() is False` and exactly one WARNING, with no exception
   propagated.
5. Add a conftest marker so this directory does not require the `integration`
   marker — everything here must run in the default suite.

**Success criteria.** The whole directory passes offline under three host zones.

**Verify.** `TZ=America/Chicago uv run pytest tests/core_test/infra/tradingview/ -q`
exits 0 and reports `0 failed`, with no network access required.

### Task 5.7 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist as `Symbol`
records with the right asset class, calendar and contract spec, and are tracked.

**Target files and symbols.**
- `scripts/seed_index_futures_symbols.py` (new)

**Steps.**
1. Follow `scripts/README.md`: read `MONGODB_URL` from the environment, dry-run by
   default, `--apply` to write.
2. For each of the three, upsert a `Symbol` via `SymbolRepository.upsert` with
   `asset_class=AssetClass.INDEX_FUTURE`, `calendar_id="CME_GLOBEX_EQUITY"`, and
   the matching preset from `core/domain/symbol/value_objects.py`
   (`ES_CONTRACT_SPEC`, `NQ_CONTRACT_SPEC`, `YM_CONTRACT_SPEC`), plus
   `name` values `"E-mini S&P 500 continuous"`, `"E-mini Nasdaq-100 continuous"`
   and `"E-mini Dow continuous"`.
3. Upsert a matching `TrackedSymbol` for each via `TrackedSymbolRepository.upsert`
   with `seeded_from="admin"`, mirroring the shape built at
   `app/market_data/app_services/tracked_symbol_seeder.py:75-80`.
4. Print one summary line listing the three composites and whether each was created
   or already present.
5. Do NOT extend `seed_tracked_symbols` in
   `app/market_data/app_services/tracked_symbol_seeder.py`. That function derives
   symbols from strategies and open orders on every boot; hard-coding three
   instruments into it would make them unremovable through the admin route.

**Success criteria.** The three symbols and tracked symbols exist; a second run
reports all three as already present.

**Verify.** `uv run python scripts/seed_index_futures_symbols.py --apply` exits 0,
then `curl -s localhost:41921/api/v1/market-data/tracked-symbols | grep -c "CME_MINI"`
prints `2` and exits 0.

### Task 5.8 — Initial backfill to the configured cap

**Goal.** All seven timeframes carry as much history as the entitlement allows, and
the cron accumulates forward from there.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py` — `TrackedSymbolBackfillService.run` (line 94), `_direct` (120), `_cascade` (148)

**Steps.**
1. Confirm `_direct` (line 120) is the mode used for a calendar-based asset class at
   every interval, not just 1m. In `BackfillTrackedSymbolCommand.resolved_mode`
   (line 77), return `"direct"` whenever the resolved calendar's `calendar_id` is
   not `"CRYPTO_24_7"`. Add a comment: cascading futures 1d across UTC midnight
   would produce daily bars that never match the vendor chart, which is a stated
   do-not in the advice.
2. Because `resolved_mode` is a property on a Pydantic command, move the decision
   into `TrackedSymbolBackfillService.run` (line 94) where the resolver is
   available, and leave the command's property as the crypto default.
3. For each of the three symbols and each of the seven intervals in
   `SYNC_INTERVALS`, run the backfill to `n = settings.tradingview_max_bars` through
   the existing admin route
   `POST /api/v1/market-data/tracked-symbols/{symbol}/backfill?interval=<iv>&n=<cap>&mode=direct`.
   The route already caps `n` at 5000 (`routes/tracked_symbols.py:91`); when
   `tradingview_max_bars` is raised above 5000, raise that `le=` bound in the same
   edit and note that the bound is a request guard, not an entitlement.
4. URL-encode the composite symbol: `ES1!%3ACME_MINI`. The `!` needs no encoding.
5. Record the resulting bar count per symbol per interval in the phase notes.

**Success criteria.** `bars` count for `ES1!:CME_MINI` at 1m equals
`min(tradingview_max_bars, available)`; 1d and 1w bars open at 17:00 CT on their
session dates.

**Verify.** `curl -s "localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1d?limit=3"`
exits 0 and returns JSON whose first `datetime` value ends in either `T22:00:00Z`
or `T23:00:00Z` — never `T00:00:00Z`.

### Task 5.9 — Phase gate (G1)

**Goal.** G1 is met and a full week including a weekend produces no anomaly noise.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates.
2. During an open CME session, request the latest 1m ES bar and confirm freshness.
3. Over one full week including a weekend and, if one falls in the window, an
   early-close holiday, count anomaly events for `ES1!:CME_MINI`. The target is zero
   `misaligned_bars_dropped`, zero `integrity.issues_found`, zero `no_progress`,
   zero `stuck_threshold_crossed` and zero `partial_aggregate`.
4. Confirm the weekend-quiet metric: `job_history` shows `sync_1m` details with
   `status="skipped_closed"` for the three futures symbols and zero `no_progress`
   entries for them.
5. Point `sync_verify_cascade` at ES and confirm zero divergent bars across 24
   consecutive hourly runs, with 4h `datetime` values anchored at the session open
   (22:00 or 23:00 UTC), never 00:00 or 04:00 UTC.
6. Confirm the crypto symbols are unaffected across the same window.

**Success criteria.** G1 holds, the anomaly counts are zero, and `divergent_fraction`
is 0.0 for 24 consecutive runs.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors`. Then, during a session,
`curl -s "localhost:41921/api/v1/market-data/ohlcv/ES1!%3ACME_MINI/1m?limit=1"`
returns a bar whose `datetime` is within 2 minutes of now, or within 12 minutes
while `tradingview_delayed_data` is true.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| The scraper's login breaks (open issues Dec 2025, Mar 2026) | High over time | High — no futures data | Pinned dependency; degraded anonymous mode never crashes; swap cost is one `ITradingViewClient` implementation |
| The mapper reads the library's naive local timestamps | Medium | High — silently wrong bars | Task 5.3 step 5 and Task 5.4 step 3 read the epoch only; Task 5.6 runs the tests under three host zones |
| `fut_contract` parsing mis-handles a future symbol shape | Low | Medium | `split_composite` is pure and tested against all four shapes in Task 5.6 step 2 |
| Bar cap yields only ~4 trading days of 1m history | Certain | Medium — accepted trade-off | Recorded as a non-goal; the cron accumulates forward; the Databento one-off import remains available |
| The blocking library stalls the event loop | Medium | High — single uvicorn worker | Every call goes through `asyncio.to_thread`; Task 5.3 step 5 makes this explicit |
| Backfill hits a scraper rate limit | Medium | Low | 3 symbols x 7 intervals is 21 calls; run them serially through the admin route, not concurrently |
| A credential leaks into the repo | Low | High | Task 5.1 Verify greps for assigned values; CLAUDE.md forbids secrets outside `../pocketquant-config` |

## Rollback

Remove `"index_future"` from `MARKET_DATA_PROVIDERS` and delete the three
`TrackedSymbol` records; the sync cron then ignores the futures symbols entirely
and the crypto path is untouched. The `Symbol` records and any accumulated bars are
provider-neutral and can stay — they remain valid under a future adapter. To
remove them fully, delete the three symbols and their bars by composite id.

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
title: "Realtime quotes and contract-aware trading math"
status: pending
priority: P1
effort: "12h"
dependencies: [5]
---

# Phase 6: Realtime quotes and contract-aware trading math

Maps to advice Phase 5.

## Context

Two independent workstreams that share a phase because they share a gate (G2
and G3): the polling realtime adapter, and contract units in the paper broker and
backtest.

**The margin accounting is NOT being redone.** `PaperBrokerAdapter` already
migrated to futures/margin accounting in plan `260628-2013`: opening or adding to
a position does not move cash, and balance changes only by the realized-PnL delta
on reduce or close (`paper_broker_adapter.py:518-524`, `_reduce_and_credit` at
`:599-615`). See `docs/journals/2026-06-28-paper-broker-futures-accounting.md`.
This phase adds ONLY the unit conversion on top of it.

Verified PnL sites: `PositionAggregate._calculate_pnl_per_unit`
(`core/domain/position/entities.py:258-262`) is the single place both realized and
unrealized PnL are computed — `reduce_quantity` multiplies it by quantity at
`:189-190` and the `unrealized_pnl` property does the same at `:268-270`. Applying
the multiplier there is the DRY fix and reaches both paths with one edit.

Commission: `core/domain/trading/commission_model.py` defines the
`CommissionModel` Protocol as `compute(price, quantity) -> float` and one
implementation, `PercentageCommissionModel(bps)`.
`PaperBrokerAdapter._commission` at `:484-485` is the only caller.

## Tasks

### Task 6.1 — `TradingViewQuoteAdapter` (polling, session-gated)

**Goal.** A second `IRealtimeQuoteProviderPort` implementation emits the existing
quote-dict contract from polled bar closes.

**Target files and symbols.**
- `src/pocketquant/core/infra/tradingview/tradingview_quote_adapter.py` (new) — `TradingViewQuoteAdapter`

**Steps.**
1. `__init__(self, client: ITradingViewClient, settings: Settings, calendar_resolver: SymbolCalendarResolver)`.
   Keep `self._subscriptions: dict[str, Callable[[dict[str, Any]], Any]]`,
   `self._tasks: dict[str, asyncio.Task]`, `self._last_close: dict[str, float]` and
   `self.last_tick_at: datetime | None = None`, mirroring
   `binance_websocket_adapter.py:49-55`.
2. Implement all nine Protocol members. `connect()` and `disconnect()` manage the
   polling task set rather than a socket. `is_connected()` returns
   `client.is_authenticated() and bool(self._tasks)`.
3. `subscribe(symbol, callback)` registers the callback and starts one polling task
   for that symbol. `unsubscribe(symbol)` cancels the task and awaits its
   cancellation before removing the entry, so no task outlives its subscription.
4. The per-symbol polling loop:
   - resolve the calendar once at task start;
   - each iteration, `if not calendar.is_open(datetime.now(UTC)): await asyncio.sleep(settings.tradingview_poll_seconds); continue`
     — no network call while the market is closed;
   - otherwise fetch the latest 2 bars at `Interval.MINUTE_1`;
   - when the newest closed bar's `close` differs from `self._last_close[symbol]`,
     build the quote dict and invoke the callback;
   - update `self.last_tick_at = datetime.now(UTC)` on every successful poll,
     whether or not the price changed, so the staleness watchdog sees liveness;
   - log at DEBUG only. This is a per-poll hot path.
5. Emit the exact dict shape `aggtrade_to_quote_dict` produces
   (`binance_mappers.py:93-106`): keys `symbol`, `timestamp`, `last_price`,
   `volume`, `bid`, `ask`, `change`, `change_percent`, `open_price`, `high_price`,
   `low_price`, `prev_close`. Set `timestamp` to the bar's own aware UTC open
   instant, `last_price` to its close, `volume` to its volume, and the rest to
   `None`. Downstream handlers already tolerate `None` for those fields.
6. Catch every exception inside the loop, log one WARNING
   `provider.tradingview.poll_failed` with the exception class name, and continue —
   a transient scraper failure must never kill the task.
7. Add a load-bearing comment: `tick_count` will be 1 per poll because per-tick
   volume deltas are unavailable from a bar-close poll, so `BarBuilderDomainService`
   volume for this provider is the bar's own volume rather than a sum of deltas.

**Success criteria.** All nine members present; `isinstance` against the Protocol
is `True`; no network call is made while the calendar reports closed.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q`
exits 0 with `0 failed`, including a test asserting zero client calls across ten
loop iterations with a stub calendar whose `is_open` returns `False`.

### Task 6.2 — Register the quote adapter and loosen its staleness threshold

**Goal.** The routing realtime provider serves futures symbols, and the 30s
watchdog does not fight a 60s poll cadence.

**Target files and symbols.**
- `src/pocketquant/app/di/market_data.py` — the routing adapter dict from Phase 4 Task 4.4
- `src/pocketquant/core/infra/binance/binance_websocket_adapter.py:237-250` — `_stale_connection_watchdog`

**Steps.**
1. Add `"tradingview": TradingViewQuoteAdapter(...)` to the realtime adapter dict.
   Because Phase 4 Task 4.4 step 5 put that dict behind one factory, this is a
   one-line addition.
2. The 30s staleness watchdog lives inside `BinanceWebSocketAdapter`
   (`:237-250`), not in the routing layer, so it does NOT apply to the TradingView
   adapter. Confirm this by reading the method before changing anything. If the
   check turns out to be shared, give `TradingViewQuoteAdapter` its own threshold of
   `max(120.0, settings.tradingview_poll_seconds * 3)` and do not touch the Binance
   one.
3. Add one INFO `provider.tradingview.quotes_started` line at `connect()` and one
   `provider.tradingview.quotes_stopped` at `disconnect()`. INFO is correct: these
   are one-shot lifecycle events.

**Success criteria.** Both providers stream concurrently; the Binance watchdog is
unchanged; no false staleness disconnect for a futures symbol.

**Verify.** `uv run pytest tests/app_test/unit/market_data/test_quote_app_service.py tests/core_test/infra/binance/test_binance_websocket_client.py -q`
exits 0 with `0 failed`.

### Task 6.3 — `PerContractCommissionModel`

**Goal.** Commission can be charged per contract instead of as a notional
percentage.

**Target files and symbols.**
- `src/pocketquant/core/domain/trading/commission_model.py` — add `PerContractCommissionModel`

**Steps.**
1. Add, next to `PercentageCommissionModel`:
   ```python
   class PerContractCommissionModel:
       def __init__(self, usd_per_contract: float) -> None:
           self._usd_per_contract = usd_per_contract

       def compute(self, price: float, quantity: float) -> float:
           return abs(quantity) * self._usd_per_contract
   ```
2. It satisfies the existing `CommissionModel` Protocol unchanged — `price` is
   accepted and ignored, which is the whole point of a per-contract fee.
3. Add a factory `commission_model_for(spec: ContractSpec) -> CommissionModel` in
   the same module returning `PerContractCommissionModel(spec.commission_value)`
   when `spec.commission_kind == "per_contract"` and
   `PercentageCommissionModel(bps=spec.commission_value)` otherwise. This keeps the
   branch in one place instead of at every construction site.
4. Extend `tests/core_test/unit/domain/trading/test_commission_model.py` with:
   `PerContractCommissionModel(2.5).compute(4500.0, 2) == 5.0`; the price argument
   has no effect; `commission_model_for(ES_CONTRACT_SPEC)` returns the per-contract
   model and `commission_model_for(LINEAR_CONTRACT_SPEC)` the percentage one.

**Success criteria.** Per-contract commission is price-independent; the factory
picks the right model from a spec.

**Verify.** `uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q`
exits 0 with `0 failed`.

### Task 6.4 — Contract multiplier on the position aggregate

**Goal.** Realized and unrealized PnL become
`(exit - entry) * multiplier * quantity` with one edit that reaches both paths.

**Target files and symbols.**
- `src/pocketquant/core/domain/position/entities.py` — `PositionAggregate` fields (lines 28-45), `open` classmethod (line 47), `_calculate_pnl_per_unit` (258-262), `market_value` (274-276)

**Steps.**
1. Add `contract_multiplier: float = 1.0` to `PositionAggregate` after
   `entry_commission` (line 44). Default 1.0 so every existing position, test and
   stored document behaves exactly as before.
2. Change `_calculate_pnl_per_unit` to return the price difference multiplied by
   `self.contract_multiplier`. Add a load-bearing comment: this single site feeds
   both `reduce_quantity` (line 189) and the `unrealized_pnl` property (line 269),
   so applying the multiplier here keeps realized and mark-to-market consistent by
   construction.
3. Add `contract_multiplier: float = 1.0` to the `open` classmethod signature and
   pass it through.
4. `market_value` (line 275) currently returns `self.quantity * self.current_price`.
   Multiply by `contract_multiplier` so a futures position reports notional
   correctly. Grep for `market_value` consumers before changing and list them in the
   commit message.
5. Persist the field: add it to `to_mongo` (near line 256) and read it in
   `from_mongo` (near line 275) with a default of `1.0`, so a document written
   before this change loads as linear.
6. Extend `tests/core_test/unit/domain/position/test_position_trade_emission.py`
   with the worked example: a LONG of 2 contracts at 4500.00 with
   `contract_multiplier=50.0`, reduced fully at 4500.25, yields
   `realized_pnl == 25.0`. Assert `unrealized_pnl` before the reduce is also 25.0.

**Success criteria.** With `contract_multiplier=1.0` every existing test result is
unchanged; with 50.0 the ES worked example yields exactly 25.0.

**Verify.** `uv run pytest tests/core_test/unit/domain/position/ tests/core_test/infra/brokers/ -q`
exits 0 with `0 failed`, and running with `-v` shows the new ES worked-example test
passing.

### Task 6.5 — Thread `ContractSpec` through the paper broker

**Goal.** The broker opens positions with the right multiplier, rounds quantity to
the lot step and charges the right commission.

**Target files and symbols.**
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` — `__init__` (108-140), `_can_afford` (487-500), `_execute_fill` (517-...)
- `src/pocketquant/core/infra/brokers/broker_factory.py:33-43` — `BrokerFactory.create`
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:111-132` — `create_broker`

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` to `PaperBrokerAdapter.__init__`
   after `commission_model` (line 116). Store
   `self._contract_spec = contract_spec or LINEAR_CONTRACT_SPEC`. Every existing
   construction site therefore keeps today's behaviour with no edit; the verified
   list is `broker_factory.py:37`, `backtest_sandbox_app_service.py:119` and `:150`,
   plus eleven test files.
2. When `commission_model` is `None` and a non-linear `contract_spec` is supplied,
   default it to `commission_model_for(self._contract_spec)` rather than to
   `PercentageCommissionModel(bps=0.0)`.
3. Where the broker opens a position, pass
   `contract_multiplier=self._contract_spec.multiplier` into `PositionAggregate.open`.
4. `_can_afford` (line 487): the margin model already exempts short-covering BUYs
   (lines 491-497 explain why). Multiply the notional check at line 500 by
   `self._contract_spec.multiplier` so a 2-contract ES entry is not gated against a
   $9000 notional when the real notional is $450,000. Add a comment: under the 1x
   margin model this check is a sanity bound on the opening notional, not a cash
   debit.
5. Quantity rounding: when `self._contract_spec.lot_step` is not `None`, round the
   order quantity down to a whole multiple of it before the fill, and reject the
   order with the existing rejection path when the result is 0. Integer contracts
   are the requirement; do not silently fill a fractional contract.
6. In `BrokerFactory.create` (line 33), read an optional `contract_spec` out of the
   `config` dict and forward it. Keep `commission_bps` working for the crypto path.
7. In `BacktestSandboxAppService.create_broker` (line 112), add a
   `contract_spec: ContractSpec | None = None` parameter and forward it. Leave the
   placeholder broker at line 150 alone — it never trades.

**Success criteria.** With no `contract_spec` supplied every existing broker test
produces identical numbers; with `ES_CONTRACT_SPEC` a 2-contract round trip from
4500.00 to 4500.25 realizes 25.0 minus 2 x 2.5 x 2 commission.

**Verify.** `uv run pytest tests/core_test/infra/brokers/ tests/backtest_test/engine/ -q`
exits 0 with `0 failed`.

### Task 6.6 — Contract-aware backtest configuration

**Goal.** A 1h ES backtest reports dollar PnL and Sharpe consistent with the
contract spec.

**Target files and symbols.**
- `src/pocketquant/core/domain/backtest/config.py` — `BacktestConfig` (lines 26-40)
- `src/pocketquant/engine/backtest/backtest_dispatch.py` — the broker construction path
- `src/pocketquant/engine/backtest/backtest_report_app_service.py:368` — the annualization lookup from Phase 3 Task 3.6

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` to `BacktestConfig` after
   `parameters` (line 35). Update the docstring attribute list (lines 12-24) with
   one line: `None` means the linear crypto shape.
2. Update `to_dict` / `from_dict` (lines 41-56) to round-trip it, using
   `ContractSpec.to_mongo()` / `ContractSpec.from_mongo()`.
3. In the dispatch path that calls `create_broker`, resolve the symbol's
   `ContractSpec` from the `Symbol` record when `config.contract_spec` is `None`, so
   a user running an ES backtest does not have to supply it by hand. Pass the
   resolved spec into `create_broker`.
4. Phase 3 Task 3.6 already routed annualization through
   `calendar.periods_per_year`. Confirm here that a 1h ES backtest reports
   `periods_per_year` near `23 * 252 = 5796` rather than 8760, and record the exact
   calendar-derived value in the phase notes.
5. Do not add a `contract_spec` field to `RunBacktestCommand`. The API surface stays
   unchanged; the spec is derived from the symbol, which is the DRY source of truth.

**Success criteria.** A 1h ES backtest reports dollar PnL equal to
points x 50 x contracts and a Sharpe computed from the session-derived
`periods_per_year`.

**Verify.** `uv run pytest tests/backtest_test/ -q` exits 0 with `0 failed`, and a
new test `tests/backtest_test/engine/test_es_contract_backtest.py` asserting a
two-contract ES round trip of 0.25 points yields 25.0 gross passes.

### Task 6.7 — Position sizing on the lot step

**Goal.** Risk-based sizing returns whole contracts for a futures instrument.

**Target files and symbols.**
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py:12-...` — `PositionCalculatorDomainService.calculate`

**Steps.**
1. Read the existing `calculate` signature and body before editing — it is the only
   method on the class.
2. Add a keyword-only `contract_spec: ContractSpec | None = None` parameter.
3. When a spec with a non-`None` `lot_step` is supplied, divide the risk-derived
   notional by `spec.multiplier` before converting to quantity, then floor the
   result to a whole multiple of `lot_step`. Return 0 when the floor is 0, so an
   account too small for one contract sizes to no trade rather than to a fraction.
4. With no spec, or with `lot_step is None`, the existing computation must be
   returned byte-identically. Add a regression test asserting that.
5. Add `tests/core_test/unit/domain/risk/test_position_calculator_contract_spec.py`
   covering: linear default unchanged; ES sizing floors to whole contracts; an
   account that cannot afford one contract returns 0.

**Success criteria.** Crypto sizing is unchanged; ES sizing yields integers.

**Verify.** `uv run pytest tests/core_test/unit/domain/risk/ -q` exits 0 with
`0 failed`.

### Task 6.8 — Phase gate (G2 and G3)

**Goal.** A live paper ES session and a 1h ES backtest both produce correct USD
figures.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates.
2. G2: run a paper strategy on `ES1!:CME_MINI` for one full CME session. Execute
   one round trip of 2 contracts entering at 4500.00 and exiting at 4500.25.
   Confirm realized PnL is 25.00 USD minus per-contract commission, and that the
   equity curve shows no jump at fill time other than commission.
3. G3: run a 1h ES backtest over the available window. Confirm dollar PnL equals
   points x 50 x contracts and that Sharpe uses the calendar-derived
   `periods_per_year` (near 5796), not 8760.
4. Confirm the quote adapter made zero client calls across the weekend by checking
   for the absence of `provider.tradingview.poll_failed` and the presence of the
   session gating in DEBUG logs.
5. Record both figures in the phase notes.

**Success criteria.** G2 and G3 both hold with the exact numbers above.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors`. All four exit 0, and the G2 round trip
reports realized PnL of exactly 25.00 before commission in the trade record.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| The multiplier is applied twice (aggregate and broker) | Medium | High — 2500x PnL error | Applied at exactly one site, `_calculate_pnl_per_unit`; Task 6.4 step 2 names it and the worked-example test pins the number |
| `market_value` consumers break on the multiplied value | Medium | Medium | Task 6.4 step 4 requires a grep of consumers before the edit |
| Polling at 60s misses a fast move | Certain | Low — accepted | Delayed CME data makes sub-minute polling meaningless; recorded as a trade-off |
| An orphaned polling task survives unsubscribe | Medium | Medium — leaks a task per symbol | Task 6.1 step 3 cancels and awaits before removing the entry |
| `_can_afford` blocks legitimate futures entries | Medium | High — no fills | Task 6.5 step 4 multiplies the bound; the existing short-cover exemption is preserved |
| Fractional-contract fills slip through | Low | Medium | Lot-step flooring plus rejection at 0 in Task 6.5 step 5 |
| Contract roll produces a basis jump in a held position | Certain over time | Low — stated non-goal | Documented in Phase 7; results are read with the roll in mind |

## Rollback

Every change is guarded by a default that reproduces the linear crypto shape:
`contract_multiplier=1.0`, `contract_spec=None`, `lot_step=None`. Reverting the
phase restores exact prior behaviour. Persisted positions gain one optional field
that older code ignores. Remove `"tradingview"` from the realtime adapter dict to
stop polling without touching anything else.

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

=== FILE: phase-07-ui-docs-and-metric-runthrough.md ===
---
phase: 7
title: "UI, docs and success-metric run-through"
status: pending
priority: P2
effort: "8h"
dependencies: [6]
---

# Phase 7: UI, docs and success-metric run-through

Maps to advice Phase 6.

## Context

The SPA already renders an exchange badge from the composite symbol
(`web/src/components/controls/symbol-selector.tsx:39,47`) and splits on the first
`:` with no character class (`web/src/lib/symbol-format.ts:6-10`), so `CME_MINI`
and `CBOT_MINI` render without code changes. What remains is Binance-specific
placeholder text, the "closed" state wiring finished in Phase 3 Task 3.5, docs,
and the measured run-through.

Verified Binance-specific placeholders: `add-symbol-dialog.tsx:23,24,72`,
`backtest-form.tsx:44,72`, `routes/index.tsx:21`. The remaining `BTCUSDT:BINANCE`
hits are illustrative JSDoc comments on type definitions, which are fine as
examples and should be left alone.

## Tasks

### Task 7.1 — Generic symbol placeholders in the SPA

**Goal.** No user-facing string implies the platform is Binance-only.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx:23,24,72`
- `web/src/components/backtest/backtest-form.tsx:44,72`
- `web/src/routes/index.tsx:21`

**Steps.**
1. In `add-symbol-dialog.tsx`, change the error text at line 23 to
   `'Symbol is required (e.g. ES1!:CME_MINI)'`, the format error at line 24 to
   `'Use composite format: CODE:EXCHANGE (e.g. ES1!:CME_MINI)'`, and the input
   placeholder at line 72 to `"e.g. BTCUSDT:BINANCE or ES1!:CME_MINI"`.
2. In `backtest-form.tsx`, change the validation message at line 72 to
   `'Symbol must be CODE:EXCHANGE (e.g. ES1!:CME_MINI).'`. Leave the default state
   at line 44 as `'BTCUSDT:BINANCE'` — it is the most-used symbol and changing it
   would alter every user's default form.
3. In `routes/index.tsx:21`, leave the chart's default search param as
   `'BTCUSDT:BINANCE'` for the same reason. Update only the JSDoc at line 20 to
   note that any composite symbol is valid.
4. Confirm the three futures symbols appear in the `SymbolSelector` dropdown: it
   filters `useSymbols()` on `s.is_active` (line 29), and the seeder from Phase 5
   Task 5.7 creates them active.
5. Confirm the exchange badge renders `CME_MINI` and `CBOT_MINI` by reading
   `parseSymbol` output at `symbol-selector.tsx:39,47`.

**Success criteria.** The three symbols are selectable in the chart, strategy and
backtest dialogs, and the badges read `CME_MINI` / `CBOT_MINI`.

**Verify.** `cd web && npx tsc --noEmit` exits 0, then `cd web && npm run build`
exits 0. Manually confirm in the running SPA that selecting `ES1!:CME_MINI` renders
a chart and shows the `CME_MINI` badge.

### Task 7.2 — Surface the "closed" state and the delayed-data badge

**Goal.** A closed market reads as closed, and delayed data is labelled.

**Target files and symbols.**
- `web/src/components/monitor/data-health-row.tsx:50-72` and `format-helpers.ts:19` — verify Phase 3 Task 3.5 step 8 landed
- `web/src/components/chart/trading-chart.tsx` — delayed-data badge
- `src/pocketquant/engine/market_data/sync_status_service.py` — `is_market_open` from Phase 3

**Steps.**
1. Confirm the monitor row renders "Closed" rather than "Stuck" when
   `is_market_open === false`, and that `ageColorClass` is suppressed for that row.
   If Phase 3 Task 3.5 step 8 was not completed, complete it here.
2. Add a small badge near the chart symbol heading rendering `DELAYED` when the
   symbol's provider reports delayed data. Source it from the `/health` provider
   block added in Task 7.3 rather than from a new endpoint.
3. Do not modify `web/src/lib/datetime.ts:88-97` (`ageColorClass`) — it is a pure
   elapsed-time helper and gating belongs at the call site, as decided in Phase 3.
4. `web/src/lib/datetime.ts:26-35` labels historical bars with today's UTC offset
   (finding P3-1). This is cosmetic, Asia/Saigon has no DST, and fixing it means
   per-timestamp offset formatting. Record it as known and out of scope here rather
   than fixing it mid-phase.

**Success criteria.** Over a weekend, the three futures rows show "Closed" with
neutral colouring and no stuck badge, while crypto rows are unaffected.

**Verify.** `cd web && npx tsc --noEmit` exits 0 and `cd web && npm run build`
exits 0. Over a closed session, `curl -s localhost:41921/api/v1/market-data/status`
returns `"is_market_open": false` for each futures row and `true` for each crypto
row.

### Task 7.3 — Provider status on `/health`

**Goal.** "Why are there no ES bars" becomes a glance instead of a log hunt.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py:267-271` — `register_health_checks`
- `src/pocketquant/core/infra/market_data/routing_data_provider.py` — a `status()` method

**Steps.**
1. Add `def status(self) -> dict[str, Any]` to `RoutingDataProvider` returning, per
   registered provider id: `authenticated` (from the adapter when it exposes
   `is_authenticated`, else `True`), `last_success_at` as `to_utc_iso(...)`, and
   `last_error` as the exception class name only — never a message that might carry
   a URL with a token.
2. Track `last_success_at` and `last_error` inside `fetch_ohlcv` as plain instance
   attributes. `RoutingDataProvider` is an APP-scoped singleton, so this state lives
   for the process and is shared across requests; that is intended for a status
   view, and nothing user-scoped is stored.
3. In `register_health_checks` (line 267), register a `"market_data_providers"`
   check that resolves `IDataProviderPort` and returns its `status()` dict.
   `HealthCoordinator.register(name, check_function)` already takes a callable
   (`core/common/health/coordinator.py:11`).
4. Add a `sessions` block listing each tracked symbol's `calendar_id` and current
   `is_open` value, so the closed state is visible without opening the monitor page.
5. Keep the response bounded — one entry per provider and one per tracked symbol.
   Do not include bar payloads or config values.

**Success criteria.** `GET /health` includes a `market_data_providers` object naming
each registered provider and a `sessions` object naming each tracked symbol.

**Verify.** `curl -s localhost:41921/health | python3 -m json.tool` exits 0 and its
output contains both `market_data_providers` and `sessions`, and contains neither
`password` nor `token`.

### Task 7.4 — Documentation

**Goal.** The architecture docs describe the provider table, the calendar port and
the new settings.

**Target files and symbols.**
- `docs/system-architecture.md:479-535` ("Where Does X Live?"), `:773-776` (Configuration), `:777-779` (Dependencies), `:790-798` (Ops Context)
- `README.md` — the Configuration mention
- `docs/code-standards.md:770-790` — the Datetime Serialization section

**Steps.**
1. Add rows to the "Where Does X Live?" table: trading-calendar port and
   implementations (`core/domain/market_data/trading_calendar_port.py`,
   `continuous_24x7_calendar.py`, `core/infra/calendars/`); provider routing
   (`core/infra/market_data/`); TradingView adapters (`core/infra/tradingview/`);
   asset class and contract spec (`core/domain/shared/enums.py`,
   `core/domain/symbol/value_objects.py`).
2. Update the Configuration list at line 775 with the six TradingView field names
   and the two provider-routing variables — names only, never values.
3. Update Dependencies at line 779 to name `pandas-market-calendars` (CME session
   rules) and the pinned `tvdatafeed` fork, including the pin.
4. Update Ops Context "External Services" at line 795 to add TradingView, noting it
   is an unofficial scraper with no stability promise and that the exit path is one
   `ITradingViewClient` implementation plus one config line.
5. Add a short subsection under the existing "PaperBrokerAdapter accounting model"
   heading at line 643 stating that contract units are now a `ContractSpec`
   parameter layered on the unchanged margin model, and pointing at
   `docs/journals/2026-06-28-paper-broker-futures-accounting.md`.
6. Add one paragraph to `docs/code-standards.md` near the Datetime Serialization
   section (line 775) recording the UTC invariant: `TZ=UTC` is pinned in the
   Dockerfile and compose, asserted at startup, enforced by ruff `DTZ`, and the
   Mongo client is `tz_aware=True`. Note `require_utc` as the strict boundary guard
   and `coerce_utc` as the lenient `from_mongo` path.
7. Do not write a new top-level doc. Every one of these is an update to the
   smallest owning surface, per the repository's documentation rule.

**Success criteria.** A reader who knows only the docs can find the calendar port,
the provider registry and every new setting name.

**Verify.** `grep -c "tradingview_max_bars\|MARKET_DATA_PROVIDERS\|pandas-market-calendars\|ITradingCalendarPort" docs/system-architecture.md README.md`
prints a total of at least 6 across the two files and exits 0.

### Task 7.5 — G4 and G5 verification

**Goal.** The two structural goals are demonstrated, not asserted.

**Target files and symbols.** None (verification only).

**Steps.**
1. G4: confirm `tests/core_test/infra/market_data/test_routing_data_provider.py::test_third_provider_needs_only_config`
   passes and that the commit introducing it touched no file under `src/pocketquant/engine/`
   or `src/pocketquant/app/`.
2. G5: run one full `sync_1m` cron cycle and compare `synced_count` and bar values
   for BTC, ETH and SOL against the pre-Phase-1 baseline recorded in the Phase 1
   notes. Confirm crypto `periods_per_year` at 1m is still 525600.
3. Confirm the test count has not fallen below the 669-test baseline and that no
   test was skipped to make a gate pass.
4. Record both results in the phase notes.

**Success criteria.** G4 and G5 both hold with recorded evidence.

**Verify.** `uv run pytest tests/core_test/infra/market_data/ -q -k third_provider`
exits 0 and reports `1 passed`. Then `uv run pytest tests/ -q` reports `0 failed`
and a passed count of at least 668.

### Task 7.6 — Success-metric run-through

**Goal.** Every metric from the advice is measured once on the VPS and recorded.

**Target files and symbols.**
- `plans/260921-1436-asset-class-index-futures/completion-report.md` (new)

**Steps.**
1. Create the completion report and record, with the observed value for each:
   - startup refuses under `TZ=Asia/Saigon` and starts under `TZ=UTC`;
   - identical `next_run_time` for every cron job across three host zones;
   - the latest `1w` `BTCUSDT:BINANCE` bar on a Thursday-to-Sunday run is the
     previous Monday 00:00 UTC;
   - zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
     `stuck_threshold_crossed` and `partial_aggregate` events for
     `ES1!:CME_MINI` across one full week;
   - futures 1d bars open at 17:00 CT and close at 16:00 CT with `session_date`
     populated, on both sides of a DST transition;
   - the golden-file test still passes;
   - `uv run ruff check src tests` passes with `DTZ` enabled;
   - `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
     `session_open(2026-11-02) == 2026-11-01T23:00:00Z`;
   - G1 latency during a live session;
   - weekend quiet: `sync_1m` details with `status="skipped_closed"` and zero
     `no_progress` entries for the futures symbols;
   - `sync_verify_cascade` `divergent_fraction = 0.0` for 24 consecutive runs, with
     4h `datetime` values at 22:00 or 23:00 UTC;
   - backfill depth at 1m equal to `min(tradingview_max_bars, available)`;
   - G2 realized PnL of 25.00 USD minus commission;
   - G3 dollar PnL and the calendar-derived `periods_per_year`;
   - G4 and G5 from Task 7.5;
   - `git grep -i "tradingview_.*=" -- ':!*.md'` finds only field declarations.
2. For any metric that cannot be measured yet (a DST transition or a holiday outside
   the window), record the date it will be measurable and leave it open rather than
   marking it met.
3. Record the accepted trade-offs explicitly so a future reader does not re-litigate
   them: the deferred multi-year 1m history, the scraper fragility, delayed quotes
   until the CME add-on, polling rather than streaming, the unadjusted continuous
   contract roll, and calendar rules living in code rather than the database.

**Success criteria.** Every metric carries either a measured value or a dated
follow-up; no metric is silently dropped.

**Verify.** `test -f plans/260921-1436-asset-class-index-futures/completion-report.md`
exits 0, and `grep -c "^- " plans/260921-1436-asset-class-index-futures/completion-report.md`
prints at least 18.

### Task 7.7 — Phase gate

**Goal.** The delivery is closed out green.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the four repo gates plus the web build.
2. Confirm no secret is present anywhere in the repository.
3. Mark the plan status through the plan CLI — run `ak plan --help` first and follow
   the current contract. Do not edit plan status cells by hand.

**Success criteria.** All gates pass and no secret is found.

**Verify.** `uv run pytest tests/ -q` reports `0 failed`;
`uv run ruff check src tests` prints `All checks passed!`;
`uv run lint-imports` prints `Contracts: 8 kept, 0 broken.`;
`uv run pyright src` prints `0 errors`; `cd web && npm run build` exits 0; and
`git grep -iE "tradingview_(username|password|auth_token)\s*=\s*[\"'][^\"']+" -- ':!*.md'`
produces no output. All six conditions hold.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| A DST transition or holiday falls outside the measurement window | High | Low | Task 7.6 step 2 records a dated follow-up rather than marking the metric met |
| `/health` leaks a credential through an error message | Low | High | Task 7.3 step 1 stores the exception class name only; Task 7.7 greps for assigned values |
| Provider status state on an APP-scoped singleton is misread as per-request | Low | Low | Task 7.3 step 2 names the lifetime explicitly; nothing user-scoped is stored |
| Doc updates drift from the code | Medium | Low | Every doc claim in Task 7.4 names a file path that the Verify grep checks |
| The SPA build breaks on the new badge | Low | Low | `npx tsc --noEmit` plus `npm run build` are both gates |

## Rollback

Every change in this phase is presentational or documentary. Revert the phase
commits; the backend behaviour delivered in Phases 1 through 6 is unaffected.

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
