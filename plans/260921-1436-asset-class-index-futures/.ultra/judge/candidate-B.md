=== FILE: plan.md ===
---
title: "Index futures (ES/NQ/YM) via asset-class model and provider routing"
description: "Generalize PocketQuant from one 24/7 crypto venue to an asset-class + trading-calendar model with provider routing, then add TradingView-sourced CME index futures through the existing pipeline."
status: pending
priority: P1
effort: 11d
branch: develop
tags: [market-data, asset-class, trading-calendar, timezone, provider-routing, tradingview, futures]
blockedBy: []
blocks: []
created: 2026-09-21
---

## Overview

PocketQuant is hardwired to one 24/7 crypto venue: DI binds exactly one REST provider
and one WS provider, and sync, cascade, integrity, freshness, annualization and paper-broker
math all assume continuous trading and `price x quantity` units. This plan delivers
`ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` for charts, paper trading and
higher-timeframe backtests through the **same** pipeline, by making session schedule,
annualization basis, contract spec and provider selection into parameters rather than
assumptions. There is no parallel futures pipeline.

**Phase numbering.** The confirmed advice in `plans/reports/advise-260921-2001-index-futures-data-provider.md`
numbers its route Phase 0 through Phase 6. This plan maps advice Phase 0 to plan Phase 1,
advice Phase 1 to plan Phase 2, and so on through advice Phase 6 to plan Phase 7. Read the
advice's "Phase N" as this plan's "Phase N+1".

The ordering retires risk before it compounds: the UTC invariant and the provider-routing
layer are each proven on the crypto path before a single futures bar exists, so the two
hardest-to-debug failure classes (timezone drift, provider mis-routing) are gone before the
scraper's own flakiness enters the picture.

## Phases

| # | Phase | File | Effort | Depends on |
|---|-------|------|--------|------------|
| 1 | UTC Invariant and Live Crypto Bugfixes | [phase-01-utc-invariant-and-crypto-bugfixes.md](./phase-01-utc-invariant-and-crypto-bugfixes.md) | 1.5d | — |
| 2 | Trading Calendar Port and Asset-Class Model | [phase-02-calendar-port-and-asset-class-model.md](./phase-02-calendar-port-and-asset-class-model.md) | 2d | 1 |
| 3 | Calendar Threading with Crypto Parity | [phase-03-calendar-threading-crypto-parity.md](./phase-03-calendar-threading-crypto-parity.md) | 2d | 2 |
| 4 | Provider Routing Layer | [phase-04-provider-routing-layer.md](./phase-04-provider-routing-layer.md) | 1d | 3 |
| 5 | TradingView History Adapter and Symbol Seed | [phase-05-tradingview-history-and-seed.md](./phase-05-tradingview-history-and-seed.md) | 2d | 4 |
| 6 | Realtime Quotes and Contract Math | [phase-06-realtime-quotes-and-contract-math.md](./phase-06-realtime-quotes-and-contract-math.md) | 1.5d | 5 |
| 7 | UI, Docs and Success-Metric Run-Through | [phase-07-ui-docs-and-metric-runthrough.md](./phase-07-ui-docs-and-metric-runthrough.md) | 1d | 6 |

Phases are strictly sequential. Each phase owns a disjoint file set from its predecessor's
open work, so no two phases may be executed concurrently.

## Goals

- **G1** Fresh futures bars within one cron cycle during CME session hours.
- **G2** A paper ES strategy runs a full session with correct USD PnL.
- **G3** A 1h ES backtest reports dollar PnL and Sharpe consistent with the contract spec.
- **G4** Adding a provider is one adapter plus one config entry, with zero caller edits.
- **G5** BTC/ETH/SOL behaviour and tests are unchanged.
- **G6** The app refuses to start on a non-UTC host and the DST-boundary suite passes.

## Success criteria

- `uv run pytest tests/ -q` reports at least `668 passed, 1 skipped` at every phase boundary
  (the verified pre-change baseline on branch `develop`, 2026-09-21).
- `uv run lint-imports` prints `Contracts: 9 kept, 0 broken.` from Phase 2 onward
  (8 today, plus the new calendar-library containment contract).
- `uv run ruff check src tests` prints `All checks passed!` with `DTZ` enabled.
- Golden-file test proves crypto bars, cascade output and performance metrics are
  byte-identical across the Phase 3 refactor.
- Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
  `stuck_threshold_crossed` or `partial_aggregate` events for `ES1!:CME_MINI` across one
  full week including a weekend.
- `git grep -i "tradingview_.*=" -- ':!*.md'` returns only settings field declarations,
  never values.

## Non-goals

A real futures broker; multi-year 1m futures history; Databento or IBKR adapters;
tick-level fidelity beyond the scraper; modelling contract roll inside paper positions;
redoing the margin accounting shipped in plan `260628-2013`; any branching on TradingView
plan tier.

=== FILE: phase-01-utc-invariant-and-crypto-bugfixes.md ===
---
phase: 1
title: "UTC Invariant and Live Crypto Bugfixes"
status: pending
priority: P1
effort: "1.5d"
dependencies: []
---

## Context

The pipeline is UTC by convention, not by construction. The APScheduler cron triggers
actually run in the **host** timezone despite the scheduler declaring UTC; the Mongo client
is not `tz_aware`; nothing pins `TZ` in any deploy file; and the Binance weekly cutoff is
floored to a Thursday-aligned epoch week. All four are live defects on the crypto path
today, independent of futures. This phase closes them and makes UTC a checked invariant, so
that every later phase can trust its timestamps.

Verified baseline before you start (branch `develop`, 2026-09-21):
- `uv run pytest tests/ -q` -> `668 passed, 1 skipped`
- `uv run lint-imports` -> exit 0, `Contracts: 8 kept, 0 broken.`
- `uv run ruff check src tests` -> `All checks passed!`
- `uv run ruff check --select DTZ --output-format=concise src` -> exactly 3 findings
- `uv run ruff check --select DTZ --output-format=concise tests scripts` -> exactly 31 findings

The development host in this environment is `Asia/Ho_Chi_Minh` (UTC+7), so the cross-zone
behaviour in this phase is directly observable.

---

### Task 1.1 — Pin `TZ=UTC` in every runtime surface

**Goal.** Every process that runs PocketQuant code starts with the process timezone set to UTC.

**Target files and symbols.**
- `deploy/Dockerfile` — the `ENV` block at lines 44-47 in the runtime stage (currently sets
  `PATH`, `PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE`).
- `deploy/compose.prod.yml` — the `app:` service (starts line 32); it currently has only
  `env_file: - .env` and no `environment:` block.
- `justfile` — the `be:` recipe.

**Steps.**
1. In `deploy/Dockerfile`, add `TZ=UTC` as a fourth entry in the existing runtime-stage
   `ENV` block so it reads `ENV PATH="/app/.venv/bin:$PATH" \` / `    PYTHONUNBUFFERED=1 \` /
   `    PYTHONDONTWRITEBYTECODE=1 \` / `    TZ=UTC`.
2. In `deploy/compose.prod.yml`, add an `environment:` block to the `app:` service directly
   below its `env_file:` block, containing the single entry `- TZ=UTC`. Add a one-line
   comment above it explaining that the explicit entry means a missing `TZ` key in `.env`
   cannot unpin the container zone.
3. In `justfile`, change the `be:` recipe body so the uvicorn invocation runs with `TZ=UTC`.
   Because `set windows-shell` is configured, do not use a bash-only `TZ=UTC cmd` prefix —
   instead add a `just` recipe-level environment line: put `export TZ := "UTC"` at the top of
   the `justfile`, directly under the `python :=` assignment line.
4. Do NOT touch `deploy/compose.local.yml`. Verified: that file defines only `mongodb` and
   `redis` services (lines 4 and 22) and has no `app` service, so there is nothing to pin.

**Success criteria.** `TZ=UTC` appears in the Dockerfile runtime stage, in the compose.prod
`app` service environment, and as a justfile-level export.

**Verify.** `grep -c 'TZ=UTC' deploy/Dockerfile deploy/compose.prod.yml` prints
`deploy/Dockerfile:1` and `deploy/compose.prod.yml:1`, and
`grep -c 'export TZ := "UTC"' justfile` prints `1`.

---

### Task 1.2 — Give both `CronTrigger` constructors an explicit UTC timezone

**Goal.** Every registered cron job fires at the same UTC instant regardless of the host zone.

**Target files and symbols.**
- `src/pocketquant/core/infra/scheduling/scheduler.py` — `CronTrigger(...)` at line 219 (the
  `cron_expression` branch) and at line 228 (the `hour/minute/second/day_of_week` branch),
  both inside `JobScheduler.add_cron_job`. `CronTrigger` is imported at line 28; the
  scheduler itself already declares `timezone="UTC"` at line 79.
- New test file `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py`.

**Steps.**
1. Add `from datetime import UTC` to the imports of `scheduler.py` if it is not already
   imported there.
2. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call at
   line 219.
3. Add `timezone=UTC,` as the last keyword argument to the `CronTrigger(...)` call at
   line 228.
4. Add a short comment above the first of the two calls: a pre-built trigger keeps its own
   timezone, so the scheduler-level `timezone="UTC"` at line 79 does not reach it, and
   APScheduler would otherwise fall back to `tzlocal.get_localzone()` and pickle the host
   zone into the Mongo jobstore.
5. Create `tests/core_test/infra/scheduling/test_cron_trigger_timezone.py` with two tests
   that build a `JobScheduler`, call `initialize()` with a stub `Settings`, register one job
   through each branch (once with `cron_expression="0 */12 * * *"`, once with `hour=3`), and
   assert `str(job.trigger.timezone) == "UTC"` for both.

**Success criteria.** Both registered triggers report a UTC timezone even though the host is
`Asia/Ho_Chi_Minh`.

**Verify.** `uv run pytest tests/core_test/infra/scheduling/test_cron_trigger_timezone.py -q`
exits 0 and prints `2 passed`.

---

### Task 1.3 — Replace the host-dependent `date.today()` in the backtest loader

**Goal.** The backtest fallback date window is computed from UTC, not the host calendar date.

**Target files and symbols.**
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py:37` — `today = date.today()`
  inside the date-range helper whose fallback returns `(today - timedelta(days=365), today)`.

**Steps.**
1. Change line 37 from `today = date.today()` to `today = datetime.now(UTC).date()`.
2. Ensure the module imports `UTC` from `datetime`. It already imports `datetime` and
   `timedelta`; add `UTC` to that import list.
3. If the `date` name becomes unused as a runtime value but is still used as a type
   annotation (it is: the function signature returns `tuple[date, date]`), keep the `date`
   import.

**Success criteria.** `date.today()` no longer appears anywhere in `src/`.

**Verify.** `grep -rn "date.today()" src/` prints nothing and exits 1.

---

### Task 1.4 — Enable ruff `DTZ` and clear every finding

**Goal.** Naive datetime construction becomes a lint error across `src`, `tests` and `scripts`.

**Target files and symbols.**
- `pyproject.toml` — `[tool.ruff.lint] select = ["E", "F", "I", "N", "W", "UP", "TID"]`.
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:81` — the
  `sorted(bars, key=lambda b: b.datetime or datetime.min)` fallback (DTZ901).
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py:24` — the naive
  epoch branch `datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`
  (DTZ001). **Do not fix this one here** — it is deleted in Task 1.6; add a temporary
  `# noqa: DTZ001` with the comment "removed in the tz_aware commit" and delete the noqa there.
- 31 findings across `tests/` and `scripts/` (see step 4 for the file list).

**Steps.**
1. In `pyproject.toml`, change the ruff lint select list to
   `select = ["E", "F", "I", "N", "W", "UP", "TID", "DTZ"]`.
2. Fix `cascade_aggregator.py:81` by replacing `datetime.min` with
   `datetime.min.replace(tzinfo=UTC)`. The module already imports `UTC`.
3. Add `# noqa: DTZ001  # removed in the tz_aware commit (Task 1.6)` to
   `bar_builder_domain_service.py:24`.
4. Fix the test and script findings by adding `tzinfo=UTC` to each naive `datetime(...)`
   literal and `.replace(tzinfo=UTC)` to each `datetime.min` use, in these files
   (counts are the verified DTZ findings per file):
   `tests/core_test/unit/domain/test_mongo_datetime_normalization.py` (4),
   `tests/backtest_test/engine/test_backtest_app_service_persistence.py` (4),
   `scripts/backfill/test_binance_bars.py` (3),
   `tests/scripts/rubric/test_reconciliation.py` (2),
   `tests/backtest_test/engine/test_result_collector_mark_to_market.py` (2),
   `tests/backtest_test/engine/test_hitnrun2_backtest.py` (2),
   `tests/backtest_test/engine/test_engulfing_pullback30_touch_backtest.py` (2),
   `tests/backtest_test/engine/test_engulfing_backtest.py` (2),
   `tests/app_test/market_data/test_cascade_aggregator.py` (2, both DTZ901),
   `tests/scripts/rubric/test_trade_path_analysis.py` (1),
   `tests/engine_test/test_live_metrics_query_service.py` (1),
   `tests/core_test/infra/persistence/test_trade_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_trade_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_order_repository.py` (1),
   `tests/core_test/infra/persistence/backtest/test_backtest_repository_slimmed.py` (1),
   `tests/backtest_test/test_backtest_stats_service.py` (1),
   `tests/backtest_test/domain/test_trade_stats_calculator.py` (1).
5. `tests/core_test/unit/domain/test_mongo_datetime_normalization.py` is the one exception:
   its naive datetimes exist precisely to prove `coerce_utc` attaches UTC. Do NOT add
   `tzinfo=UTC` there. Instead add `# noqa: DTZ001` to each of its 4 findings with the
   comment "naive on purpose: this test asserts coerce_utc behaviour".

**Success criteria.** DTZ is active in ruff config and reports zero findings.

**Verify.** `uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`,
and `grep -n 'DTZ' pyproject.toml` prints a line containing `"DTZ"` inside the select list.

---

### Task 1.5 — Add the fail-fast startup timezone assertion

**Goal.** The application refuses to boot on a non-UTC host and logs one INFO line naming
the runtime timezone when it does boot.

**Target files and symbols.**
- New file `src/pocketquant/core/common/time/runtime_timezone.py` with two functions:
  `assert_process_timezone_utc() -> None` and
  `assert_triggers_utc(jobs: Iterable[object]) -> None`.
- `src/pocketquant/core/common/time/__init__.py` — export both names in `__all__`.
- `src/pocketquant/app/main.py` — `lifespan()`; insert the process check immediately after
  the `logger.info("application_starting", environment=settings.environment)` call at
  line 42, before the `set_sync_container(container)` line at 52.
- `src/pocketquant/app/main_extensions.py` — `start_background_jobs()` at line 138; insert
  the trigger check after the `await register_sync_jobs(...)` call (lines 152-155).
- New test file `tests/core_test/unit/common/test_runtime_timezone.py`.

**Steps.**
1. Create `runtime_timezone.py`. `assert_process_timezone_utc()` must:
   - import `time` and `tzlocal` (tzlocal 5.3.1 is already a locked transitive dependency of
     APScheduler — verified in `uv.lock`);
   - read `local_name = tzlocal.get_localzone_name()`;
   - raise `RuntimeError` with a message naming `os.environ.get("TZ")`, `time.tzname`,
     `time.timezone`, `time.daylight` and `local_name` unless
     `time.timezone == 0 and not time.daylight and local_name in {"UTC", "Etc/UTC"}`;
   - on success emit exactly one `logger.info("runtime.timezone", tz=..., tzname=...,
     localzone=...)` line. One-shot lifecycle event, so INFO is the correct level.
2. `assert_triggers_utc(jobs)` must iterate the jobs, skip any whose `trigger` has no
   `timezone` attribute, and raise `RuntimeError` naming the offending `job.id` and its
   timezone if `str(job.trigger.timezone) != "UTC"`.
3. Export both from `core/common/time/__init__.py`.
4. Call `assert_process_timezone_utc()` in `main.py::lifespan` at the position named above.
5. In `main_extensions.py::start_background_jobs`, after `await register_sync_jobs(...)`,
   resolve the scheduler that is already fetched there (`await container.get(JobScheduler)`)
   and call `assert_triggers_utc(scheduler.get_jobs())`. If `JobScheduler` exposes no
   `get_jobs()` passthrough, add a thin `get_jobs()` method to `JobScheduler` returning
   `self._scheduler.get_jobs()` (raising `RuntimeError` when `self._scheduler is None`,
   matching the existing guard style at `scheduler.py:214`).
6. Do NOT call `assert_process_timezone_utc()` from `tests/app_test/integration/app_factory.py`
   or from `start_background_jobs`. That factory builds its own lifespan and must stay
   runnable under a foreign host zone so the Task 1.9 TZ matrix can execute the full suite.
7. Write `tests/core_test/unit/common/test_runtime_timezone.py` with three tests:
   one monkeypatching `tzlocal.get_localzone_name` to `"UTC"` plus `time.timezone` to `0`
   and `time.daylight` to `0` and asserting no raise; one monkeypatching the name to
   `"Asia/Saigon"` and asserting `pytest.raises(RuntimeError)`; one passing a fake job whose
   `trigger.timezone` is `ZoneInfo("Asia/Saigon")` into `assert_triggers_utc` and asserting
   `pytest.raises(RuntimeError)`.

**Success criteria.** The assertion raises on a non-UTC process zone and is silent (one INFO
log) on UTC.

**Verify.** `uv run pytest tests/core_test/unit/common/test_runtime_timezone.py -q` exits 0
and prints `3 passed`.

---

### Task 1.6 — Make Mongo `tz_aware` and remove the naive integrity site IN ONE COMMIT

**Goal.** Every datetime read back from Mongo is timezone-aware UTC, and the integrity job
still compares like with like.

**HARD ORDERING CONSTRAINT.** These four edits must land in a single commit. Flipping
`tz_aware` alone makes `check_integrity` compute `expected - aligned_times` between an aware
set and a naive set, report every bar as missing, and trigger `repair_integrity` to resync
5000 bars for every symbol and interval every 12 hours. Do not split this task.

**Target files and symbols.**
- `src/pocketquant/core/infra/persistence/mongodb.py:44-49` — the `AsyncMongoClient(...)`
  construction inside `Database.connect`.
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py:50` —
  `now = datetime.now(UTC).replace(tzinfo=None)` inside `check_integrity`.
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py:24` — the naive
  epoch branch `datetime(1970, 1, 1, tzinfo=UTC) if timestamp.tzinfo else datetime(1970, 1, 1)`,
  plus the `# noqa: DTZ001` added in Task 1.4.
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py:54-55` — the comment
  "Mongo client is not tz_aware; raw projection returns naive datetimes."

**Steps.**
1. In `mongodb.py`, add `tz_aware=True,` and `tzinfo=UTC,` to the `AsyncMongoClient(...)`
   keyword arguments, keeping the existing `minPoolSize`, `maxPoolSize` and
   `serverSelectionTimeoutMS`. Add `from datetime import UTC` to the module imports.
2. In `integrity_jobs.py:50`, change the line to `now = datetime.now(UTC)` (drop the
   `.replace(tzinfo=None)`).
3. In `bar_builder_domain_service.py:24`, replace the conditional with the unconditional
   `epoch = datetime(1970, 1, 1, tzinfo=UTC)` and delete the `# noqa: DTZ001`.
4. In `bar_filters.py:54-55`, update the comment to state that the raw projection now returns
   aware UTC datetimes and that `coerce_utc` is retained as a defensive no-op.
5. Leave `coerce_utc` in `core/common/time/__init__.py` exactly as it is; `Bar.from_mongo`
   still calls it and it must remain a no-op safety net.
6. Commit all four files together with a single conventional commit.

**Success criteria.** Integrity checks return the same `missing_count` as before the change
for a crypto symbol with a dense 1m series, and the Mongo normalization tests still pass.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py tests/core_test/infra/persistence/test_bar_repository.py tests/app_test/unit/handlers/sync/test_bar_filters.py -q`
exits 0, and `git show --stat HEAD --name-only` lists exactly these four paths:
`src/pocketquant/core/infra/persistence/mongodb.py`,
`src/pocketquant/engine/market_data/app_services/integrity_jobs.py`,
`src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py`,
`src/pocketquant/engine/market_data/sync_internals/bar_filters.py`.

---

### Task 1.7 — Make `Bar.datetime` aware by construction and fix the serialization drift

**Goal.** No naive datetime can enter a `Bar` from an adapter, and the four documented
serialization sites emit the `...Z` form that `docs/code-standards.md:777` mandates.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — `Bar.datetime: dt | None` at line 37, and
  the `.isoformat()` calls at lines 104 and 111 inside `to_dict`.
- `src/pocketquant/engine/market_data/ohlcv_service.py:66` — `bar.datetime.isoformat()`
  in the response mapper. Leave lines 84 and 86 alone: those build an internal cache key,
  where `docs/code-standards.md` explicitly permits bare `.isoformat()`.
- `src/pocketquant/engine/backtest/backtest_command_service.py:74-75` — `start_date`/`end_date`.
- `src/pocketquant/engine/backtest/backtest_report_app_service.py:396-397` — `start_date`/`end_date`.
- `src/pocketquant/engine/market_data/sync_status_service.py:72-73` — the hand-rolled
  `_iso_z` helper.
- `src/pocketquant/engine/market_data/ohlcv_service.py` — `GetOHLCVQuery` dataclass at
  line 14 (fields `start_date`, `end_date` at lines 23-24).
- `src/pocketquant/engine/backtest/backtest_command_service.py` — `RunBacktestCommand`
  Pydantic model, `start_date` and `end_date` fields.

**Steps.**
1. In `entities.py`, change `datetime: dt | None = None` to use Pydantic's `AwareDatetime`:
   declare it as `datetime: AwareDatetime | None = None` and add a
   `@field_validator("datetime", mode="before")` classmethod named `_normalise_datetime`
   that returns `None` for `None`, converts an aware non-UTC value with `.astimezone(UTC)`,
   and raises `ValueError("Bar.datetime must be timezone-aware")` for a naive value.
   Import `AwareDatetime` and `field_validator` from `pydantic`.
2. `Bar.from_mongo` already wraps the value in `coerce_utc`, so reads keep working. Do not
   change `from_mongo`.
3. Replace `self.datetime.isoformat()` at `entities.py:104` and
   `self.updated_at.isoformat()` at line 111 with `to_utc_iso(self.datetime)` and
   `to_utc_iso(self.updated_at)`. `to_utc_iso` already returns `None` for `None`, so drop
   the surrounding conditional expressions. `coerce_utc` and `utc_now` are already imported
   from `pocketquant.core.common.time`; add `to_utc_iso` to that import.
4. Replace the `.isoformat()` call at `ohlcv_service.py:66` with `to_utc_iso(bar.datetime)`.
5. Replace the two `.isoformat()` calls at `backtest_command_service.py:74-75` and the two at
   `backtest_report_app_service.py:396-397` with `to_utc_iso(...)`.
6. Delete the local `_iso_z` helper at `sync_status_service.py:72-73` and replace its call
   sites with `to_utc_iso`.
7. Add a UTC-normalising validator to `GetOHLCVQuery`. It is a plain `@dataclass`, so add a
   `__post_init__` that calls `coerce_utc` on `self.start_date` and `self.end_date`.
8. Add `@field_validator("start_date", "end_date", mode="before")` to `RunBacktestCommand`
   that attaches UTC to a naive value with `coerce_utc`. Keep accepting naive input from
   clients for backwards compatibility — normalise, do not reject, at the API edge.

**Success criteria.** Every bar timestamp leaving the API ends in `Z`, and a naive datetime
passed directly to `Bar(datetime=...)` raises.

**Verify.** `uv run pytest tests/engine_test/market_data/test_ohlcv_service.py tests/core_test/unit/domain/bar tests/app_test/unit/handlers/status/test_sync_status_service.py -q`
exits 0, and `grep -rn "\.isoformat()" src/pocketquant/core/domain/bar/entities.py src/pocketquant/engine/market_data/sync_status_service.py`
prints nothing and exits 1.

---

### Task 1.8 — Fix the Binance in-progress weekly cutoff

**Goal.** The latest persisted `1w` bar for a Binance symbol is always a closed week.

**Target files and symbols.**
- `src/pocketquant/core/infra/binance/binance_adapter.py:80-83` —
  `now_ms`, `last_closed_open_ms = (now_ms // bar_duration_ms) * bar_duration_ms`,
  `cutoff_dt`, `end_time_ms`. The `cutoff_dt` guard is applied at line 108.
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` — `get_bar_start`,
  whose `WEEK_1` branch is Monday-anchored (lines 17-22).
- New test file `tests/core_test/infra/binance/test_binance_weekly_cutoff.py`.

**Steps.**
1. Import `get_bar_start` into `binance_adapter.py` from
   `pocketquant.core.domain.bar.services.bar_builder_domain_service`.
2. Replace the epoch-floor block at lines 80-83 with logic that derives the cutoff from the
   alignment function: compute `now = datetime.now(UTC)`, then
   `cutoff_dt = get_bar_start(now, interval)`, then
   `last_closed_open_ms = int(cutoff_dt.timestamp() * 1000)` and `end_time_ms = last_closed_open_ms`.
   This keeps sub-day intervals byte-identical (their `get_bar_start` is the same epoch floor)
   while making `1w` Monday-anchored and `1d` UTC-midnight-anchored.
3. Add a comment recording why: a plain `floor(now / 604800000)` lands on Thursday because
   the Unix epoch was a Thursday, so from Thursday to Sunday the in-progress Monday-open
   weekly kline passed the `< cutoff_dt` guard and was persisted partial.
4. Create `tests/core_test/infra/binance/test_binance_weekly_cutoff.py`. Freeze `now` to a
   Thursday (for example `datetime(2026, 5, 7, 12, 0, tzinfo=UTC)`), assert the derived
   `1w` cutoff equals the Monday of that week (`2026-05-04T00:00:00+00:00`), and assert the
   `1h` cutoff is unchanged from the old epoch-floor result.

**Success criteria.** On a Thursday-to-Sunday `now`, the weekly cutoff is the current week's
Monday open, so the in-progress weekly kline is excluded.

**Verify.** `uv run pytest tests/core_test/infra/binance/ -q` exits 0 and reports no
failures, including the pre-existing `test_binance_client_in_progress_filter.py`.

---

### Task 1.9 — Add the cross-timezone CI matrix and the `just test-tz` recipe

**Goal.** The suite is proven identical under three host timezones, and one test asserts the
cron `next_run_time` is zone-invariant.

**Target files and symbols.**
- `.github/workflows/cicd.yml` — the `tests:` job (starts at the `jobs:` block; it runs
  `uv run lint-imports` then `uv run pytest tests/ -q`).
- `justfile` — a new `test-tz:` recipe.
- New test file `tests/core_test/infra/scheduling/test_cron_next_run_time_zone_invariant.py`.

**Steps.**
1. In the `tests:` job of `cicd.yml`, add a `strategy:` block with
   `matrix: { tz: ["UTC", "Asia/Saigon", "America/Chicago"] }` and add
   `env: { TZ: ${{ matrix.tz }} }` at the job level so every step inherits it.
2. Add a `just test-tz` recipe that runs the suite three times, once per zone:
   `TZ=UTC {{python}} -m pytest -q`, then `TZ=Asia/Saigon {{python}} -m pytest -q`, then
   `TZ=America/Chicago {{python}} -m pytest -q`.
3. Create `tests/core_test/infra/scheduling/test_cron_next_run_time_zone_invariant.py`. In
   one test, build a `CronTrigger(hour=3, minute=0, timezone=UTC)` three times with
   `os.environ["TZ"]` set to each of the three zones and `time.tzset()` called between, and
   assert `trigger.get_next_fire_time(None, reference)` returns the same instant each time,
   for a fixed aware `reference`. Restore the original `TZ` in a `finally` block and call
   `time.tzset()` again.
4. Because the production assertion lives only in `main.py::lifespan` (Task 1.5 step 6), the
   full suite is expected to pass under all three zones without exclusions. If any test fails
   only under a non-UTC zone, that failure is a real finding — apply the Failure Protocol.

**Success criteria.** The full suite passes under all three zones and the cron invariance
test passes.

**Verify.** `TZ=Asia/Saigon uv run pytest tests/ -q` exits 0 and prints at least
`668 passed`, and `TZ=America/Chicago uv run pytest tests/ -q` exits 0 and prints at least
`668 passed`.

---

### Task 1.10 — Phase gate

**Goal.** Phase 1 is provably complete and the crypto path is unchanged.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, the import contracts and the linter.
2. Confirm the non-UTC refusal by hand.
3. Deploy to the VPS and confirm the `runtime.timezone` INFO line appears once at startup.

**Success criteria.** All three gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `668 passed, 1 skipped`;
`uv run lint-imports` exits 0 and prints `Contracts: 8 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`TZ=Asia/Saigon uv run uvicorn pocketquant.app.main:app --port 41999` exits non-zero and its
output contains `runtime timezone` (the assertion message from Task 1.5).

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
title: "Trading Calendar Port and Asset-Class Model"
status: pending
priority: P1
effort: "2d"
dependencies: [1]
---

## Context

This phase introduces the vocabulary the rest of the plan depends on: an `AssetClass` enum,
a `ContractSpec` value object, and an `ITradingCalendarPort` with two implementations. It
persists `asset_class`, `calendar_id` and `contract_spec` on the `Symbol` record so the
schedule is stored alongside the asset class exactly as required, while the schedule *rules*
stay in code behind the port (holidays and early closes change yearly, are shared by many
symbols, and a Mongo copy would need manual syncing against CME notices).

Nothing in this phase changes runtime behaviour. The calendars are built and tested, the
symbol schema is widened, but no consumer reads them yet — that is Phase 3.

Verified facts you are building on:
- `core/domain/shared/enums.py:5-13` holds `_PERIODS_PER_YEAR` (365-day crypto table) and
  `Interval.periods_per_year` at line 26 plus `Interval.periods_per_year_for` at line 34.
- `core/domain/symbol/entities.py:19` is `COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9_-]+:[A-Z0-9_-]+$")`
  and line 24 is `COMPOSITE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9._-]{1,32}:[A-Z0-9._-]{1,32}$")`.
  Neither accepts `!`.
- `Symbol.asset_type: str | None` is declared at `entities.py:38` and referenced at
  lines 67, 70, 84, 97, at `engine/market_data/symbols_service.py:20`, and in
  `web/src/types/market-data.ts:26`. Those six sites are the complete set (grep verified).
- `pandas>=2.1.0` is already a dependency (`pyproject.toml`). `pandas_market_calendars` is not.
- No `multiplier`, `contract_size`, `tick_size` or `point_value` symbol exists in `src/`.

---

### Task 2.1 — Add the `AssetClass` enum

**Goal.** A closed enum names the three asset classes the system supports.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py` — add `class AssetClass(str, Enum)` below
  the existing `Interval` class.

**Steps.**
1. Add `class AssetClass(str, Enum):` with members `CRYPTO_SPOT = "crypto_spot"`,
   `CRYPTO_PERP = "crypto_perp"`, `INDEX_FUTURE = "index_future"`.
2. Add a docstring stating that the asset class binds the annualization basis and the
   contract-spec shape, and that a new asset class is a new member plus a new calendar
   record, never new branching.
3. Do not touch `Interval`, `_PERIODS_PER_YEAR` or `_DAYS_PER_YEAR` in this task — they are
   moved in Phase 3, Task 3.7.

**Success criteria.** `AssetClass` is importable from `pocketquant.core.domain.shared.enums`.

**Verify.** `uv run python -c "from pocketquant.core.domain.shared.enums import AssetClass; print(sorted(m.value for m in AssetClass))"`
exits 0 and prints `['crypto_perp', 'crypto_spot', 'index_future']`.

---

### Task 2.2 — Add the `ContractSpec` value object

**Goal.** Contract economics (points-to-dollars, tick, lot step) become explicit data.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/symbol/value_objects.py` with a frozen Pydantic
  model `ContractSpec` and two module constants.

**Steps.**
1. Create `value_objects.py` in `core/domain/symbol/` with
   `class ContractSpec(BaseModel)` and `model_config = ConfigDict(frozen=True)`.
2. Fields: `multiplier: float = 1.0`, `tick_size: float = 0.01`, `lot_step: float | None = None`,
   `currency: str = "USD"`, `commission_kind: Literal["percent", "per_contract"] = "percent"`.
   Document `lot_step=None` as "continuous sizing" and any float value as "round the
   computed size down to this step" (`1.0` for integer contracts).
3. Add `LINEAR_CONTRACT_SPEC = ContractSpec()` as the crypto default (multiplier 1, no lot
   step, percent commission) so no caller has to spell it out.
4. Add a `to_mongo()` returning `self.model_dump()` and a `@classmethod from_mongo(doc)`
   returning `cls(**doc)` when `doc` is truthy and `LINEAR_CONTRACT_SPEC` otherwise.
5. Export `ContractSpec` and `LINEAR_CONTRACT_SPEC` from
   `src/pocketquant/core/domain/symbol/__init__.py`.

**Success criteria.** `ContractSpec` round-trips through Mongo shape and is immutable.

**Verify.** `uv run python -c "from pocketquant.core.domain.symbol import ContractSpec, LINEAR_CONTRACT_SPEC; s=ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0); assert ContractSpec.from_mongo(s.to_mongo())==s; assert LINEAR_CONTRACT_SPEC.multiplier==1.0; print('ok')"`
exits 0 and prints `ok`.

---

### Task 2.3 — Define `ITradingCalendarPort`

**Goal.** One domain-side contract expresses everything the pipeline needs to know about a
trading schedule.

**Target files and symbols.**
- New file `src/pocketquant/core/domain/market_data/trading_calendar_port.py` with
  `ITradingCalendarPort(ABC)` and two calendar-id constants.

**Steps.**
1. Create the file next to the existing `data_provider_port.py` and
   `realtime_quote_provider_port.py`, following the same header-docstring style.
2. Declare module constants `CALENDAR_CRYPTO_24_7 = "CRYPTO_24_7"` and
   `CALENDAR_CME_GLOBEX_EQUITY = "CME_GLOBEX_EQUITY"`.
3. Declare `class ITradingCalendarPort(ABC)` with:
   - `calendar_id: str` (abstract property),
   - `tz: ZoneInfo` (abstract property),
   - `is_open(self, instant: datetime) -> bool`,
   - `session_open(self, session_date: date) -> datetime` (returns UTC),
   - `session_close(self, session_date: date) -> datetime` (returns UTC),
   - `session_date_of(self, instant: datetime) -> date`,
   - `previous_close(self, instant: datetime) -> datetime` (returns UTC),
   - `sessions(self, start: datetime, end: datetime) -> list[date]`,
   - `trading_minutes(self, start: datetime, end: datetime) -> list[datetime]`,
   - `bar_open(self, instant: datetime, interval: Interval) -> datetime`,
   - `periods_per_year(self, interval: Interval) -> float`.
   Every method is `@abstractmethod`.
4. Document on the class that every returned datetime is timezone-aware UTC, that every
   input datetime must be timezone-aware, and that `session_date` is the exchange's own day
   label (for CME, the session opening Sunday 17:00 CT has `session_date` = the Monday).
5. Import `ZoneInfo` from `zoneinfo` and `Interval` from
   `pocketquant.core.domain.shared.enums`. No third-party imports — this file must stay
   domain-pure.

**Success criteria.** The port imports cleanly and the domain purity test still passes.

**Verify.** `uv run pytest tests/core_test/unit/domain/test_domain_purity.py -q` exits 0
and prints `1 passed`.

---

### Task 2.4 — Implement `Continuous24x7CalendarAdapter`

**Goal.** Crypto's schedule becomes an explicit calendar that reproduces today's numbers
exactly.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/calendars/` with `__init__.py` and
  `continuous_24x7_calendar_adapter.py` defining `Continuous24x7CalendarAdapter`.
- New test file `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py`.

**Steps.**
1. Create the package. `Continuous24x7CalendarAdapter` implements `ITradingCalendarPort`
   with `calendar_id = CALENDAR_CRYPTO_24_7` and `tz = ZoneInfo("UTC")`.
2. `is_open` returns `True` always. `session_open(d)` returns
   `datetime(d.year, d.month, d.day, tzinfo=UTC)`. `session_close(d)` returns
   `session_open(d) + timedelta(days=1)`. `session_date_of(instant)` returns
   `instant.astimezone(UTC).date()`. `previous_close(instant)` returns `instant` (a 24/7
   market is never closed, so the last expected bar close is now).
3. `sessions(start, end)` returns every calendar date in `[start.date(), end.date()]`.
   `trading_minutes(start, end)` returns every whole minute in `[start, end)`.
4. `bar_open(instant, interval)` must reproduce the current `get_bar_start` semantics
   exactly: `DAY_1` -> `instant.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)`;
   `WEEK_1` -> that midnight minus `timedelta(days=midnight.weekday())` (Monday 00:00 UTC,
   the Binance convention); everything else -> epoch floor by `INTERVAL_SECONDS[interval]`
   against `datetime(1970, 1, 1, tzinfo=UTC)`. Raise `ValueError` for a naive `instant`.
5. `periods_per_year(interval)` returns the values currently in
   `core/domain/shared/enums.py:5-13`: 1m 525600, 5m 105120, 15m 35040, 1h 8760, 4h 2190,
   1d 365, 1w 365/7. Copy the table into this adapter as `_PERIODS_PER_YEAR_24X7` with the
   comment that crypto trades every calendar day.
6. Write `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py` asserting:
   `bar_open` equals `get_bar_start` for a sample of 6 timestamps across all 7 intervals
   (import `get_bar_start` and compare directly — this is the parity proof);
   `periods_per_year` matches `Interval.periods_per_year` for all 7 intervals;
   `is_open` is `True` on a Saturday; `trading_minutes` over a 10-minute window has length 10;
   `bar_open` raises `ValueError` on a naive input.

**Success criteria.** The 24/7 calendar is numerically indistinguishable from today's
hardcoded behaviour.

**Verify.** `uv run pytest tests/core_test/infra/calendars/test_continuous_24x7_calendar.py -q`
exits 0 and prints `5 passed`.

---

### Task 2.5 — Add the `pandas_market_calendars` dependency and confirm the CME alias

**Goal.** The CME Globex equity schedule is available from a maintained library rather than
a hand-kept holiday table.

**Target files and symbols.**
- `pyproject.toml` — the `[project] dependencies` list (currently ends with `"dishka>=1.9.1",`).
- `uv.lock`.

**Steps.**
1. Run `uv add "pandas-market-calendars>=4.4.0"`. This updates both `pyproject.toml` and
   `uv.lock`.
2. Confirm the calendar alias and its parameters before writing any adapter code. The audit
   verified from source that `pandas_market_calendars/calendars/cme_globex_equities.py`
   defines `CMEGlobexEquitiesExchangeCalendar` with alias `"CME Globex Equity"`,
   `ZoneInfo("America/Chicago")`, `market_open = time(17)` offset -1 day, and
   `market_close = time(16)`. Re-confirm against the installed version.
3. If the alias string differs in the installed version, use the alias the installed library
   reports and record the difference in the phase notes. Do not invent an alias.

**Success criteria.** The library is installed and the CME Globex equity calendar resolves.

**Verify.** `uv run python -c "import pandas_market_calendars as mcal; c=mcal.get_calendar('CME Globex Equity'); print(c.name, c.tz, c.open_time, c.close_time)"`
exits 0 and prints a line containing `America/Chicago`, `17:00:00` and `16:00:00`.

---

### Task 2.6 — Implement `CmeGlobexEquityCalendarAdapter`

**Goal.** ES/NQ/YM get a correct, DST-aware, holiday-aware session calendar.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/calendars/cme_globex_equity_calendar_adapter.py`
  defining `CmeGlobexEquityCalendarAdapter`.

**Steps.**
1. Implement `ITradingCalendarPort` with `calendar_id = CALENDAR_CME_GLOBEX_EQUITY` and
   `tz = ZoneInfo("America/Chicago")`.
2. In `__init__`, call `mcal.get_calendar("CME Globex Equity")` once and store it. Build a
   `schedule` lazily per queried range and cache the resulting DataFrame keyed by
   `(start_date, end_date)` in a small `dict` bounded to the most recent 8 entries, so
   repeated cron calls do not rebuild it.
3. `session_open(session_date)` and `session_close(session_date)`: read `market_open` and
   `market_close` from the library schedule for that session and return them converted with
   `.astimezone(UTC)`. Never add a fixed offset; the library already localises via
   `America/Chicago`, which is what makes DST correct.
4. `is_open(instant)`: `True` when `instant` falls inside `[session_open, session_close)` of
   the session whose date is `session_date_of(instant)`. The 16:00-17:00 CT maintenance halt
   is simply the gap between one session's close and the next session's open, so no extra
   branch is needed.
5. `session_date_of(instant)`: the label of the session containing `instant`; when `instant`
   is inside the halt or the weekend, return the label of the session that most recently
   closed.
6. `previous_close(instant)`: the `session_close` of the most recent session that has
   already closed at `instant`; when the market is open, return `instant`.
7. `trading_minutes(start, end)`: for each session overlapping the range, emit every whole
   minute in `[max(start, session_open), min(end, session_close))`.
8. `bar_open(instant, interval)`: for `DAY_1` return `session_open(session_date_of(instant))`;
   for `WEEK_1` return the `session_open` of the first session of that session's ISO week
   (the Sunday 17:00 CT open); for intraday intervals return
   `session_open + floor((instant - session_open) / interval) * interval`, clipped so a bar
   never starts at or after `session_close`.
9. `periods_per_year(interval)`: derive it, do not hardcode. Compute
   `sessions_per_year = 252` and `minutes_per_session = 1380` (23 hours) as module constants
   with a comment naming their source, then return
   `sessions_per_year * minutes_per_session * 60 / INTERVAL_SECONDS[interval]` for intraday
   intervals, `sessions_per_year` for `DAY_1`, and `sessions_per_year / 5` for `WEEK_1`.
10. Raise `ValueError` on any naive datetime input, with the message naming the parameter.

**Success criteria.** Session boundaries come from `zoneinfo` conversion, never from a fixed
offset, and the halt is a gap rather than a special case.

**Verify.** `no verification needed` — Task 2.7 covers this adapter mechanically.

---

### Task 2.7 — Write the DST, holiday and UTC-midnight session test suite

**Goal.** The three timezone failure modes that would silently corrupt futures bars are
locked down by tests.

**Target files and symbols.**
- New test file `tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py`.

**Steps.**
1. Spring-forward: assert `session_open(date(2026, 3, 9)) == datetime(2026, 3, 8, 22, 0, tzinfo=UTC)`.
2. Fall-back: assert `session_open(date(2026, 11, 2)) == datetime(2026, 11, 1, 23, 0, tzinfo=UTC)`.
3. Sunday reopen: assert `is_open` is `False` at `2026-09-20T20:00:00Z` and `True` at
   `2026-09-20T22:30:00Z` (a Sunday evening, after the 17:00 CT open).
4. Weekend closure: assert `is_open` is `False` for `2026-09-19T12:00:00Z` (Saturday) and
   that `previous_close` for that instant equals the Friday 16:00 CT close in UTC.
5. Daily halt: assert `is_open` is `False` at a `16:30` CT instant on a normal weekday.
6. Juneteenth early close: pick the 2026 Juneteenth observance from the library schedule and
   assert `session_close` for that session is earlier than 16:00 CT, and that
   `len(trading_minutes(session_open, session_close))` is correspondingly smaller than 1380.
7. Session spanning UTC midnight: assert `session_date_of(datetime(2026, 9, 22, 1, 0, tzinfo=UTC))`
   equals `date(2026, 9, 22)` while the session's `session_open` is on `2026-09-21` in UTC.
8. `bar_open` anchoring: assert the `HOUR_4` bar open for an instant one hour into a session
   equals that session's `session_open`, and that it is `22:00` or `23:00` UTC, never
   `00:00` or `04:00` UTC.
9. `periods_per_year(Interval.DAY_1)` equals `252.0` and `periods_per_year(Interval.HOUR_1)`
   equals `252 * 23` (`5796.0`).

**Success criteria.** All nine scenarios pass against real library data.

**Verify.** `uv run pytest tests/core_test/infra/calendars/test_cme_globex_equity_calendar.py -q`
exits 0 and prints `9 passed`.

---

### Task 2.8 — Add `TradingCalendarFactory` and the import-linter containment contract

**Goal.** Callers resolve a calendar by id, and `pandas_market_calendars` can never leak out
of `core/infra`.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/calendars/trading_calendar_factory.py` defining
  `TradingCalendarFactory`.
- `pyproject.toml` — a ninth `[[tool.importlinter.contracts]]` block.

**Steps.**
1. `TradingCalendarFactory` takes no constructor arguments and builds both adapters once in
   `__init__`, storing them in `self._by_id: dict[str, ITradingCalendarPort]` keyed by
   `CALENDAR_CRYPTO_24_7` and `CALENDAR_CME_GLOBEX_EQUITY`.
2. `get(self, calendar_id: str) -> ITradingCalendarPort` returns the instance, raising
   `ValueError(f"Unknown calendar_id: {calendar_id!r}")` for anything else.
3. `default(self) -> ITradingCalendarPort` returns the 24/7 calendar.
4. Naming note: `Factory` is on the exempt list in `docs/code-standards.md` under
   "Infra factory/scheduler" (alongside `BrokerFactory`, `JobScheduler`), so this name is
   correct and must not be renamed to `*Adapter` or `*Service`.
5. Add the contract to `pyproject.toml`:
   `name = "Market-calendar library stays behind the calendar port"`, `type = "forbidden"`,
   `source_modules = ["pocketquant.core.domain", "pocketquant.engine", "pocketquant.app"]`,
   `forbidden_modules = ["pandas_market_calendars"]`.
6. Register the factory in DI: add
   `trading_calendar_factory = provide(TradingCalendarFactory, scope=Scope.APP)` to
   `InfrastructureProvider` in `src/pocketquant/app/di/infrastructure.py`.

**Success criteria.** Nine import contracts hold and the factory resolves both ids.

**Verify.** `uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`

---

### Task 2.9 — Widen both composite-symbol regexes to accept `!`

**Goal.** `ES1!:CME_MINI` is a valid composite symbol everywhere.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py:19` — `COMPOSITE_SYMBOL_RE`.
- `src/pocketquant/core/domain/symbol/entities.py:24` — `COMPOSITE_SYMBOL_PATTERN`.
- Callers of `COMPOSITE_SYMBOL_PATTERN` (complete list, grep verified):
  `src/pocketquant/app/common/symbol_validation.py:23`,
  `src/pocketquant/engine/market_data/tracked_symbols_backfill.py:65`,
  `src/pocketquant/engine/market_data/tracked_symbols_service.py:35`.
  Caller of `COMPOSITE_SYMBOL_RE`: `entities.py:48` inside `Symbol._validate_symbol`.
- New test file `tests/core_test/unit/domain/symbol/test_composite_symbol_regex.py`.

**Steps.**
1. Change line 19 to `COMPOSITE_SYMBOL_RE = re.compile(r"^[A-Z0-9!_-]+:[A-Z0-9!_-]+$")`.
2. Change line 24 to `COMPOSITE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.!_-]{1,32}:[A-Z0-9.!_-]{1,32}$")`.
3. Add a comment above line 19 explaining that `!` is required by TradingView continuous
   front-month symbology (`ES1!`), and that no other punctuation is admitted.
4. Do not change the three callers — they read the shared patterns and inherit the widening.
5. The SPA needs no change: `web/src/components/strategy/add-symbol-dialog.tsx:24` and
   `web/src/components/backtest/backtest-form.tsx:72` validate only with
   `trimmed.includes(':')`, which already accepts `!` (grep verified — there is no
   character-class regex on the frontend).
6. Write `tests/core_test/unit/domain/symbol/test_composite_symbol_regex.py` asserting
   `Symbol.create("ES1!:CME_MINI").symbol == "ES1!:CME_MINI"`, that `NQ1!:CME_MINI` and
   `YM1!:CBOT_MINI` are accepted, that `BTCUSDT:BINANCE` is still accepted, and that
   `ES1@:CME` and `ES1!CME` are both rejected with `ValueError`.

**Success criteria.** The three futures composites validate and malformed inputs still fail.

**Verify.** `uv run pytest tests/core_test/unit/domain/symbol/test_composite_symbol_regex.py -q`
exits 0 and prints `5 passed`.

---

### Task 2.10 — Extend `Symbol` with `asset_class`, `calendar_id` and `contract_spec`

**Goal.** The schedule and contract economics are persisted alongside the asset class on the
symbol record.

**Target files and symbols.**
- `src/pocketquant/core/domain/symbol/entities.py` — `Symbol.asset_type` at line 38, the
  `create` classmethod parameter at line 67 and its body at line 70, `to_mongo` at line 84,
  `from_mongo` at line 97.
- `src/pocketquant/engine/market_data/symbols_service.py:20` — the `"asset_type"` response key.
- `web/src/types/market-data.ts:26` — `asset_type: string` in `SymbolInfo`.

**Steps.**
1. Replace `asset_type: str | None = None` at line 38 with three fields:
   `asset_class: AssetClass = AssetClass.CRYPTO_SPOT`,
   `calendar_id: str = CALENDAR_CRYPTO_24_7`,
   `contract_spec: ContractSpec = Field(default_factory=lambda: LINEAR_CONTRACT_SPEC)`.
2. Replace the `asset_type` parameter of `create` (line 67) with `asset_class`, `calendar_id`
   and `contract_spec`, all with the same defaults, and pass them through at line 70.
3. In `to_mongo` (line 84), replace `"asset_type": self.asset_type` with
   `"asset_class": self.asset_class.value`, `"calendar_id": self.calendar_id`,
   `"contract_spec": self.contract_spec.to_mongo()`.
4. In `from_mongo` (line 97), read the three fields, defaulting a missing `asset_class` to
   `AssetClass.CRYPTO_SPOT`, a missing `calendar_id` to `CALENDAR_CRYPTO_24_7`, and a missing
   `contract_spec` to `LINEAR_CONTRACT_SPEC`. This keeps un-migrated documents loadable.
5. In `symbols_service.py:20`, replace the `"asset_type"` key with three keys:
   `"asset_class": s.asset_class.value`, `"calendar_id": s.calendar_id`,
   `"contract_spec": s.contract_spec.model_dump()`.
6. In `web/src/types/market-data.ts`, replace `asset_type: string` in `SymbolInfo` with
   `asset_class: string`, `calendar_id: string`. Verified: `asset_type` appears nowhere else
   in `web/src` — the field is declared but never rendered, so no component changes.
7. `grep -rn "asset_type" src tests scripts web/src` must return nothing when you are done.

**Success criteria.** The symbol schema carries asset class, calendar id and contract spec,
and no `asset_type` reference survives.

**Verify.** `grep -rn "asset_type" src tests scripts web/src` prints nothing and exits 1,
and `uv run pytest tests/ -q` exits 0 and prints at least `668 passed`.

---

### Task 2.11 — Add `session_date` and `calendar_id` to daily and weekly bars

**Goal.** Consumers get a stable day key while `datetime` keeps moving with DST.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/entities.py` — the `Bar` model, `to_mongo` (line ~63) and
  `from_mongo` (line ~78).
- `src/pocketquant/core/infra/persistence/repositories/bar_repository.py:284-290` —
  `ensure_indexes`, which today creates only
  `ix_ohlcv_symbol_interval_datetime` on `(symbol, interval, datetime)`.

**Steps.**
1. Add two optional fields to `Bar`: `session_date: date | None = None` and
   `calendar_id: str | None = None`. Document that they are populated only for `DAY_1` and
   `WEEK_1` bars of a session-based calendar and stay `None` for crypto and intraday bars.
2. Serialize both in `to_mongo`, storing `session_date` as an ISO date string (BSON has no
   date-only type, and a datetime would re-introduce the timezone ambiguity this field
   exists to remove).
3. Read both back in `from_mongo`, parsing the ISO string with `date.fromisoformat` when
   present.
4. In `ensure_indexes`, add a second, non-unique, sparse index named
   `ix_ohlcv_symbol_interval_session_date` on `[("symbol", 1), ("interval", 1), ("session_date", 1)]`
   with `sparse=True`. Keep the existing unique index untouched — `(symbol, interval, datetime)`
   remains the identity.
5. Do not populate these fields anywhere yet; Phase 5 populates them for futures bars.

**Success criteria.** The new fields round-trip and the new index exists alongside the old one.

**Verify.** `uv run pytest tests/core_test/infra/persistence/test_bar_repository.py tests/core_test/unit/domain/bar -q`
exits 0 and reports no failures.

---

### Task 2.12 — Expose calendar and contract lookup on `SymbolQueryService`

**Goal.** Any caller can resolve the calendar and contract spec for a composite symbol
without knowing the symbol's string shape.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/symbols_service.py` — `SymbolQueryService`
  (constructor at line 11 takes `symbol_repository: SymbolRepository`).
- `src/pocketquant/app/di/services.py:31` — `symbol_query_service = provide(SymbolQueryService, scope=Scope.APP)`.

**Steps.**
1. Add `calendar_factory: TradingCalendarFactory` as a second constructor parameter of
   `SymbolQueryService`. Dishka resolves it automatically from the APP-scoped provider added
   in Task 2.8; `services.py:31` needs no edit.
2. Add a private in-memory cache `self._by_symbol: dict[str, Symbol] = {}` plus
   `self._loaded_at: datetime | None = None`, refreshed from `find_all()` whenever it is
   empty or older than 300 seconds. The symbols collection is tiny and changes rarely, so a
   process-local TTL cache is the KISS choice and avoids a Mongo round-trip per bar filter.
   Note explicitly: this cache lives on an APP-scoped singleton, so it is shared across all
   requests and jobs in the single uvicorn worker. That is correct here because symbol
   records are global, not per-request, data.
3. Add `async def calendar_for(self, symbol: str) -> ITradingCalendarPort` returning
   `self._calendar_factory.get(record.calendar_id)` for a known symbol and
   `self._calendar_factory.default()` for an unknown one (so a symbol tracked but not yet
   present in `symbols` degrades to today's 24/7 behaviour rather than crashing the cron).
4. Add `async def contract_spec_for(self, symbol: str) -> ContractSpec` returning the
   record's spec or `LINEAR_CONTRACT_SPEC` when unknown.
5. Add `def invalidate(self) -> None` clearing the cache, and call it from
   `SymbolRepository`-writing paths is NOT required — the 300s TTL is sufficient and adding
   write-side invalidation would couple the repository to this service.
6. Write `tests/engine_test/market_data/test_symbol_query_service_calendar.py` with three
   tests using a stub repository: a crypto symbol resolves to the 24/7 calendar; a symbol
   with `calendar_id=CME_GLOBEX_EQUITY` resolves to the CME calendar; an unknown symbol
   resolves to the default calendar and `LINEAR_CONTRACT_SPEC`.

**Success criteria.** Calendar and contract resolution is a single call keyed by composite
symbol, with a safe default.

**Verify.** `uv run pytest tests/engine_test/market_data/test_symbol_query_service_calendar.py -q`
exits 0 and prints `3 passed`.

---

### Task 2.13 — Write and run the symbol migration

**Goal.** Every existing symbol document carries the new fields.

**Target files and symbols.**
- New file `scripts/migrate_symbol_asset_class.py`.
- `scripts/README.md` — the script inventory list.

**Steps.**
1. Write a script that reads `MONGODB_URL` and `MONGODB_DATABASE` from the environment (the
   convention documented in `scripts/README.md`: "All scripts read `MONGODB_URL` ... from
   environment — never CLI flags").
2. It must be dry-run by default and require `--apply` to write, matching the documented
   convention "explicit flag required for destructive writes".
3. For every document in the `symbols` collection missing `asset_class`, `$set`
   `asset_class: "crypto_spot"`, `calendar_id: "CRYPTO_24_7"` and `contract_spec` equal to
   `LINEAR_CONTRACT_SPEC.to_mongo()`, and `$unset` the legacy `asset_type` field.
4. Print the matched and modified counts to stdout in both modes.
5. Add a bullet for the script to `scripts/README.md` under the existing list.
6. Run it in dry-run against the local database, then with `--apply`.

**Success criteria.** No `symbols` document lacks `asset_class`, and none retains `asset_type`.

**Verify.** `uv run python scripts/migrate_symbol_asset_class.py` exits 0 and prints a line
containing `remaining_without_asset_class=0` after the `--apply` run.

---

### Task 2.14 — Phase gate

**Goal.** Phase 2 is complete with zero behaviour change.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, the import contracts and the linter.
2. Confirm the DST assertions specifically, since they are the single highest-value check in
   this phase.

**Success criteria.** All four gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `668 passed, 1 skipped`;
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`uv run pytest tests/core_test/infra/calendars/ -q` exits 0 and prints `14 passed`.

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
title: "Calendar Threading with Crypto Parity"
status: pending
priority: P1
effort: "2d"
dependencies: [2]
---

## Context

Five places in the pipeline hardcode the 24/7 calendar. Each one fires on day one of a
session-scheduled asset class, and together they would drop, mis-bucket, and thrash from the
first cron cycle. This phase threads `ITradingCalendarPort` through all five **using the
24/7 calendar only**, so the refactor is proven on the crypto path while no futures symbol
exists yet. Nothing about crypto output may change.

The five verified P0 sites:
1. **Alignment** — `bar_builder_domain_service.py:10-32` defines 1d as `replace(hour=0)` and
   1w as Monday 00:00; `bar_filters.py:72-82` drops anything else on every sync
   (called from `sync_service.py:79-81`); `SYNC_INTERVALS` at `sync_jobs.py:54-62` includes
   both. A CME daily bar opening 17:00 CT would be 100% dropped.
2. **Cascade** — `cascade_aggregator.py:98-137` (`compute_boundaries`) floors to a fixed UTC
   epoch grid; `_TF_EXPECTED_BARS[DAY_1] = 1440` at line 46.
3. **Integrity** — `integrity_jobs.py:62-63` builds `expected = {start + i*step}`; the
   docstring at lines 46-47 admits it is 24/7-only. `repair_integrity` at lines 79-116 then
   resyncs 5000 bars per symbol/interval every 12 hours.
4. **Freshness** — `sync_status_service.py:62-69` (`_is_stuck`),
   `sync_internals/anomaly_log.py:35-40,52-59` (`emit_no_progress`), and
   `web/src/lib/datetime.ts:88-97` (`ageColorClass`) all measure `now - last_bar`.
5. **Annualization** — `core/domain/shared/enums.py:5-13` and
   `performance_calculator_domain_service.py:13-14` hardcode 365 x 24.

Complete caller list for the alignment functions (grep verified, no others exist):
`get_bar_start` — `bar_app_service.py:88`, `integrity_jobs.py:51`,
`bar_builder_domain_service.py:125` (inside `create_for_tick`).
`is_bar_aligned` — `bar_alignment.py:7`, `integrity_jobs.py:57`,
`bar_builder_domain_service.py:38` (inside `filter_aligned_bars`).
`filter_aligned_bars` — `bar_filters.py:74`. `has_aligned_bar` — `provider_fetch.py:61`.

---

### Task 3.1 — Capture the golden-file baseline BEFORE any refactor

**Goal.** A byte-comparable record of current crypto behaviour exists, so the refactor can be
proven neutral rather than assumed neutral.

**Target files and symbols.**
- New test file `tests/app_test/market_data/test_calendar_refactor_golden.py`.
- New fixture file `tests/app_test/market_data/fixtures/crypto_golden_baseline.json`.

**Steps.**
1. Write a generator function inside the test module, `build_golden_payload()`, that with no
   database and no network computes, for `BTCUSDT:BINANCE` and a fixed synthetic 1m bar
   series spanning `2026-05-04T00:00:00Z` to `2026-05-11T00:00:00Z`:
   - `get_bar_start(ts, interval)` for every interval at 12 sampled timestamps;
   - `compute_boundaries(tf, range_start, range_end)` for every tf in `CASCADE_TFS` over a
     100-minute lookback ending at `2026-05-07T12:34:00Z`;
   - `aggregate_ohlcv(...)` output for three fixed buckets;
   - `_TF_EXPECTED_BARS` as a dict;
   - `Interval.periods_per_year` for all seven intervals;
   - `PerformanceCalculatorDomainService.sharpe_ratio` and `.sortino_ratio` over a fixed
     50-point equity curve at `periods_per_year` for `1m`, `1h` and `1d`.
2. Serialize the payload to JSON with `sort_keys=True, indent=2` and datetimes rendered via
   `to_utc_iso`.
3. Run the generator once now and write the result to
   `tests/app_test/market_data/fixtures/crypto_golden_baseline.json`. Commit it.
4. Add `test_crypto_behaviour_is_byte_identical()` that rebuilds the payload and asserts it
   equals the committed JSON exactly (compare the serialized strings, not the dicts, so key
   order and float formatting are also locked).
5. Run the test now, before any other Phase 3 edit, and confirm it passes. If it does not
   pass on the very first run, the generator is non-deterministic — fix that before
   proceeding.

**Success criteria.** The golden test passes against unmodified code.

**Verify.** `uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q`
exits 0 and prints `1 passed`, and
`test -s tests/app_test/market_data/fixtures/crypto_golden_baseline.json` exits 0.

---

### Task 3.2 — Make alignment calendar-aware

**Goal.** Bar alignment is decided by the symbol's calendar, not by a hardcoded UTC grid.

**Target files and symbols.**
- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py` —
  `get_bar_start` (lines 10-28), `is_bar_aligned` (lines 31-32),
  `filter_aligned_bars` (lines 35-42), `BarBuilderDomainService.create_for_tick` (line 125).
- `src/pocketquant/core/domain/bar/services/__init__.py:3,6` — the `get_bar_start` export.
- `src/pocketquant/engine/market_data/sync_internals/bar_alignment.py:6-7` — `has_aligned_bar`.
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py:72-82` —
  `drop_misaligned_bars`.
- `src/pocketquant/engine/market_data/sync_service.py:80` — the `drop_misaligned_bars` call.
- `src/pocketquant/engine/market_data/sync_internals/provider_fetch.py:31-61` —
  `fetch_with_retry`.
- `src/pocketquant/engine/market_data/app_services/bar_app_service.py:88` — the
  `get_bar_start(tick.timestamp, interval)` call.
- `tests/core_test/unit/domain/bar/services/test_bar_builder.py` (10 tests today).

**Steps.**
1. Change the signature to
   `def get_bar_start(timestamp: datetime, interval: Interval, calendar: ITradingCalendarPort) -> datetime`
   and make the body a single line: `return calendar.bar_open(timestamp, interval)`. Delete
   the `DAY_1`, `WEEK_1` and epoch-floor branches — they now live in
   `Continuous24x7CalendarAdapter.bar_open` (Task 2.4 step 4), which is already proven
   identical by `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py`.
   Make `calendar` a required positional parameter. Do NOT give it a default: a default
   would leave two live code paths and defeat the point of the refactor.
2. Change `is_bar_aligned(timestamp, interval, calendar)` to
   `return timestamp == get_bar_start(timestamp, interval, calendar)`.
3. Change `filter_aligned_bars(bars, interval, calendar)` to pass the calendar through.
4. Change `BarBuilderDomainService.create_for_tick(symbol, interval, timestamp, calendar)`
   to pass the calendar to `get_bar_start` at line 125.
5. Change `has_aligned_bar(records, interval, calendar)` in `bar_alignment.py`.
6. Change `drop_misaligned_bars(records, interval, calendar)` in `bar_filters.py`.
7. Change `fetch_with_retry(provider, symbol, interval, n_bars, calendar)` in
   `provider_fetch.py` and pass the calendar into `has_aligned_bar` at line 61.
8. In `sync_service.py`, add `symbol_query_service: SymbolQueryService` as a constructor
   parameter of `SyncService` (it currently takes provider, cache, bar_repository,
   symbol_repository, sync_status_repository at lines 37-49). At the top of `sync_one`
   (after line 54) resolve `calendar = await self._symbol_query_service.calendar_for(symbol)`
   and pass it into `fetch_with_retry` at line 66 and `drop_misaligned_bars` at line 80.
   `SyncService` is provided at `app/di/market_data.py` line "sync_service = provide(SyncService, scope=Scope.APP)";
   Dishka resolves the new parameter automatically because `SymbolQueryService` is already
   APP-scoped at `app/di/services.py:31`. Confirm `ServicesProvider` is registered in the
   same container as `MarketDataProvider` before relying on this — if it is not, move the
   `SymbolQueryService` provide into `MarketDataProvider`.
9. In `bar_app_service.py`, add a `symbol_query_service` constructor parameter, resolve the
   calendar for the tick's symbol, and pass it into `get_bar_start` at line 88. Update the
   `get_bar_manager` factory in `app/di/market_data.py` to pass it.
10. Update `tests/core_test/unit/domain/bar/services/test_bar_builder.py`: pass a
    `Continuous24x7CalendarAdapter()` instance into every `get_bar_start` and
    `is_bar_aligned` call (lines 111, 117, 118, 123, 127 and the rest). Assertions must not
    change — only the call shape.

**Success criteria.** Alignment is a calendar call everywhere, no default calendar exists,
and every existing alignment assertion still holds.

**Verify.** `uv run pytest tests/core_test/unit/domain/bar tests/app_test/unit/handlers/sync tests/engine_test/market_data/test_sync_service.py -q`
exits 0 and reports no failures, and
`grep -n "def get_bar_start" src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py`
prints a signature containing `calendar: ITradingCalendarPort`.

---

### Task 3.3 — Make the cascade session-anchored

**Goal.** Cascade buckets start at session opens, and expected bar counts come from the
calendar.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py` —
  `_TF_EXPECTED_BARS` (lines 40-47), `compute_boundaries` (lines 98-137),
  `cascade_for_symbol` (lines 140-200), the `cascade.partial_aggregate` WARN (lines ~185-195).
- `tests/app_test/market_data/test_cascade_aggregator.py` (18 tests today).

**Steps.**
1. Change `compute_boundaries(tf, range_start, range_end, calendar)`. For `DAY_1` and
   `WEEK_1`, produce `calendar.session_open(d)` for each session date in
   `calendar.sessions(range_start, range_end)`. For intraday tfs, produce
   `calendar.bar_open(b, tf)` walking forward from `calendar.bar_open(range_start, tf)` in
   `tf_seconds(tf)` steps, dropping any candidate that is not inside a session
   (`calendar.is_open(candidate)` is `False`).
2. Keep the existing overlap contract documented at lines 106-113: a bucket is included when
   `B < range_end` and `B + tf_seconds > range_start`. Do not change that rule — it is what
   lets a just-closed 4h bucket get a clean post-close aggregation pass under the 100-minute
   `sync_1m` lookback.
3. Replace the `_TF_EXPECTED_BARS` lookup at line ~168 with a per-bucket count derived from
   the calendar: `expected_count = len(calendar.trading_minutes(boundary, bucket_end))`.
   Delete `_TF_EXPECTED_BARS` entirely — a fixed table cannot express an early-close day.
4. Keep the `cascade.partial_aggregate` WARN, but only emit it when `actual_count < expected_count`
   using the calendar-derived count. For a 24/7 calendar this reproduces exactly today's
   thresholds (5, 15, 60, 240, 1440).
5. Update the `find(...)` call's `limit=expected_count + 5` to use the new value.
6. Update `cascade_for_symbol(symbol, lookback_minutes, bar_repo, calendar)` to accept the
   calendar and pass it to `compute_boundaries`. Update its callers in
   `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (search for
   `cascade_for_symbol(` — resolve the calendar there from `SymbolQueryService`).
7. Update `tests/app_test/market_data/test_cascade_aggregator.py` to pass a
   `Continuous24x7CalendarAdapter()` into every `compute_boundaries` and `cascade_for_symbol`
   call. Expected values must not change.

**Success criteria.** Cascade output for a crypto symbol is unchanged and the expected-bar
count is calendar-derived.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_aggregator.py -q` exits 0
and prints `18 passed`, and
`grep -c "_TF_EXPECTED_BARS" src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`
prints `0`.

---

### Task 3.4 — Make the integrity grid calendar-derived

**Goal.** Weekends, halts and holidays stop reading as gaps, so `sync_repair` stops thrashing.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py` —
  `check_integrity` (signature at lines 36-42, the naive-`now` line 50 already fixed in
  Task 1.6, `get_bar_start` at line 51, `is_bar_aligned` at line 57, the arithmetic grid at
  lines 62-63, the docstring caveat at lines 46-47), and `repair_integrity` (lines 79-116).
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:302` — the
  `check_integrity(ts.symbol, interval, bar_repo)` call inside `_run_integrity`, and the
  corresponding `repair_integrity` call inside `_run_repair` (starts line 329).

**Steps.**
1. Add `calendar: ITradingCalendarPort` as a parameter of `check_integrity`, after
   `bar_repo` and before `days_back`.
2. Replace `end = get_bar_start(now, interval)` with
   `end = calendar.bar_open(now, interval)` and pass the calendar into `is_bar_aligned` at
   line 57.
3. Replace the arithmetic grid at lines 62-63 with a calendar-derived expected set:
   for `MINUTE_1`, `expected = set(calendar.trading_minutes(start, end))`;
   for `DAY_1`, `expected = {calendar.session_open(d) for d in calendar.sessions(start, end)}`;
   for every other interval, walk `calendar.bar_open(start, interval)` forward by
   `INTERVAL_SECONDS[interval]` and keep only candidates where `calendar.is_open(candidate)`.
4. Rewrite the docstring caveat at lines 46-47: it now reads correctly for any calendar, and
   note that the 24/7 calendar reproduces the previous dense grid exactly.
5. In `repair_integrity`, skip `WEEK_1` entirely when
   `calendar.calendar_id != CALENDAR_CRYPTO_24_7`, returning a report with
   `"skipped": "weekly_convention_pending"`. Rationale to record in a comment: no weekly
   repair convention exists yet for session calendars, and a wrong one would delete good bars.
6. Add `calendar` to `repair_integrity`'s signature and pass it through to both
   `check_integrity` calls (line 92 and the post-repair verify near line 116).
7. In `sync_jobs.py`, resolve `calendar = await symbol_query_service.calendar_for(ts.symbol)`
   inside the tracked-symbol loops of `_run_integrity` (around line 300) and `_run_repair`,
   and pass it into the calls.

**Success criteria.** For a crypto symbol the integrity report is unchanged; for a session
calendar, closed minutes are not counted as missing.

**Verify.** `uv run pytest tests/app_test/integration/test_sync_backfill_gap_fill.py tests/app_test/test_sync_jobs_phase.py -q`
exits 0 and reports no failures.

---

### Task 3.5 — Make freshness and anomaly gating session-aware

**Goal.** A closed market reads as "closed", not "stuck", and emits no log per closed minute.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_status_service.py:62-69` — `_is_stuck`;
  `SyncStatusResult` dataclass at lines 46-59; `SyncStatusQueryService` at line 87.
- `src/pocketquant/engine/market_data/sync_internals/anomaly_log.py:20-61` —
  `emit_no_progress`, `last_bar_age_seconds` at lines 36-40, the threshold at lines 52-59.
- `src/pocketquant/engine/market_data/sync_service.py:102-111` — the `emit_no_progress` call.
- `src/pocketquant/app/routes/market_data_status.py:22-35` — the `/sync-status` response dict.
- `web/src/types/market-data.ts:88` — `is_stuck?: boolean`.
- `web/src/components/monitor/data-health-row.tsx:50,55,72` and
  `web/src/components/monitor/format-helpers.ts:19` — the stuck badge and row status.
- `web/src/lib/datetime.ts:88-97` — `ageColorClass`.

**Steps.**
1. Change `_is_stuck(latest_bar_dt, interval, calendar)` to measure age against
   `calendar.previous_close(datetime.now(UTC))` instead of `datetime.now(UTC)`. For the 24/7
   calendar `previous_close` returns `now`, so crypto behaviour is unchanged by construction.
2. Add `is_market_open: bool = True` to `SyncStatusResult` and populate it from
   `calendar.is_open(datetime.now(UTC))` in both `get_sync_status` and
   `get_symbol_sync_status`. Inject `SymbolQueryService` into `SyncStatusQueryService`'s
   constructor (it currently takes `sync_status_repository` and `bar_repository`).
3. Add `is_market_open` to both response dicts in `market_data_status.py` (the list endpoint
   at lines 22-35 and the per-symbol endpoint at lines 48-56).
4. In `emit_no_progress`, add a `calendar: ITradingCalendarPort` parameter and return
   immediately (emitting nothing) when `calendar.is_open(datetime.now(UTC))` is `False`.
   Add a comment recording the reason: a futures symbol would otherwise emit roughly 2,900
   `no_progress` WARNs per symbol per weekend, which violates the CLAUDE.md rule that log
   level is frequency plus audience.
5. Compute `age_s` against `calendar.previous_close(...)` in `emit_no_progress` too, so the
   `last_bar_age_seconds` field and the `stuck_threshold_crossed` ERROR both respect the
   session.
6. Pass the already-resolved `calendar` from `sync_one` into the `emit_no_progress` call at
   `sync_service.py:102`.
7. In `web/src/types/market-data.ts`, add `is_market_open?: boolean` next to `is_stuck` at
   line 88.
8. In `web/src/components/monitor/format-helpers.ts:19`, return `'neutral'` when
   `s.is_market_open === false`, before the `is_stuck` check.
9. In `web/src/components/monitor/data-health-row.tsx`, render a `Closed` badge instead of
   the `StuckBadge` at line 72 when `s.is_market_open === false`, and suppress the stuck
   title text at lines 50 and 55 in that case.
10. In `web/src/lib/datetime.ts:88-97`, add an optional third parameter
    `isMarketOpen?: boolean` to `ageColorClass` and return `'age-neutral'` when it is
    explicitly `false`. Update the call site in `data-health-row.tsx` to pass
    `s.is_market_open`.

**Success criteria.** The sync-status payload carries `is_market_open`, and no anomaly log is
emitted while a calendar reports closed.

**Verify.** `uv run pytest tests/app_test/unit/handlers/status/test_sync_status_service.py tests/app_test/unit/handlers/sync/test_no_progress_tracking.py -q`
exits 0 and reports no failures, and
`grep -c "is_market_open" src/pocketquant/app/routes/market_data_status.py` prints `2`.

---

### Task 3.6 — Gate the sync loop on the calendar

**Goal.** While a market is closed, the cron skips the provider call entirely instead of
retrying into a wall.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:130` — `_sync_by_intervals`,
  whose per-symbol / per-interval loop runs at lines 164-226 and whose completion log is at
  line 228.
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:253` and `:398` — the two
  `_sync_by_intervals` call sites.
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:54-62` — `SYNC_INTERVALS`.

**Steps.**
1. Inside the `for symbol in symbols:` loop at line 164, before the interval loop, resolve
   `calendar = await symbol_query_service.calendar_for(symbol)`.
2. Compute `now = datetime.now(UTC)` and a grace instant
   `grace_cutoff = calendar.previous_close(now) + timedelta(seconds=INTERVAL_SECONDS[interval])`.
   Skip the symbol/interval pair when `not calendar.is_open(now) and now > grace_cutoff`.
   The one-interval grace exists so the bar that closed exactly at the session close is still
   fetched on the following cron tick.
3. When skipping, increment a `skipped` counter and, if `doc_id` is set, call
   `history_repo.record_detail(...)` with `status="skipped"` and `error="closed"`, mirroring
   the existing detail-recording block at lines 176-194. Do not log per skip: at 3 symbols x
   7 intervals x 1440 minutes this would flood. Log the aggregate only.
4. Add `skipped_count=skipped` to the existing
   `logger.info(f"market_data.{job_name}.completed", ...)` call at line 228.
5. Do not add a new job, a new cron entry, or a futures branch. `SYNC_INTERVALS` stays
   exactly as it is at lines 54-62 — including `DAY_1` and `WEEK_1`, which are now kept
   rather than dropped because Task 3.2 made alignment calendar-aware.

**Success criteria.** A closed calendar produces `status="skipped"` job-history details and
zero provider calls, while a 24/7 calendar never skips.

**Verify.** `uv run pytest tests/app_test/test_sync_jobs_phase.py tests/app_test/unit/market_data/test_sync_jobs_catchup.py -q`
exits 0 and reports no failures.

---

### Task 3.7 — Move annualization off `Interval` onto the calendar

**Goal.** Periods-per-year is owned by the calendar, so a second calendar cannot silently
inherit crypto's 365 x 24.

**Target files and symbols.**
- `src/pocketquant/core/domain/shared/enums.py:1-13` — `_DAYS_PER_YEAR` and
  `_PERIODS_PER_YEAR`; `Interval.periods_per_year` (line 26) and
  `Interval.periods_per_year_for` (line 34).
- `src/pocketquant/core/domain/trading/performance_calculator_domain_service.py:13-14` —
  `TRADING_DAYS_PER_YEAR = 365`, consumed at line 52 (`years = days / TRADING_DAYS_PER_YEAR`).
- `src/pocketquant/engine/backtest/backtest_report_app_service.py:368-369,387` — the
  `Interval.periods_per_year_for(self._config.interval)` call.
- `src/pocketquant/engine/live/live_metrics_query_service.py:64` — passes
  `periods_per_year=None` deliberately (documented at lines 16-18); leave it alone.
- `src/pocketquant/core/domain/backtest/config.py` — `BacktestConfig` (lines 26-36).
- `src/pocketquant/engine/backtest/backtest_dispatch.py:42-54` — `_config_from_dict`.
- `tests/core_test/unit/domain/shared/test_interval.py` (12 tests today).
- `tests/backtest_test/domain/test_performance_calculator_annualization.py` (9 tests today).

**Steps.**
1. Delete `_DAYS_PER_YEAR`, `_PERIODS_PER_YEAR`, `Interval.periods_per_year` and
   `Interval.periods_per_year_for` from `enums.py`. The values already live in
   `Continuous24x7CalendarAdapter._PERIODS_PER_YEAR_24X7` (Task 2.4 step 5).
2. Add `calendar_id: str = CALENDAR_CRYPTO_24_7` to `BacktestConfig` (after `commission_bps`
   at line 33, before `replay_speed`). Document it as the id used to annualize and to anchor
   bars for this run.
3. Read it in `_config_from_dict` at `backtest_dispatch.py:42-54` with
   `calendar_id=payload.get("calendar_id", CALENDAR_CRYPTO_24_7)`.
4. In `backtest_report_app_service.py`, replace lines 368-369 with
   `calendar = self._calendar_factory.get(self._config.calendar_id)` then
   `periods_per_year = calendar.periods_per_year(Interval(self._config.interval))`.
   Wrap the `Interval(...)` construction in a `try/except ValueError` that logs the existing
   "unknown interval ... skipping Sharpe/Sortino annualization" warning at lines 370-373 and
   sets `periods_per_year = None`, preserving today's behaviour for a stale queued request.
   Add `calendar_factory: TradingCalendarFactory` to the service's constructor and thread it
   from wherever `BacktestReportAppService` is constructed.
5. Replace `TRADING_DAYS_PER_YEAR = 365` at `performance_calculator_domain_service.py:13-14`
   with a `sessions_per_year: float` keyword-only parameter on the method that uses it at
   line 52 (`years = days / sessions_per_year`), defaulting to `365.0`. Keep the default so
   the pure-domain calculator stays callable without a calendar; the backtest path passes
   `calendar.periods_per_year(Interval.DAY_1)`.
6. Move the annualization assertions out of
   `tests/core_test/unit/domain/shared/test_interval.py` into
   `tests/core_test/infra/calendars/test_continuous_24x7_calendar.py`, where the same numbers
   are already asserted in Task 2.4 step 6. Keep the remaining `Interval` tests (enum values,
   string coercion) in place.
7. Update `tests/backtest_test/domain/test_performance_calculator_annualization.py` to pass
   `periods_per_year` explicitly from a `Continuous24x7CalendarAdapter()` instead of from
   `Interval.periods_per_year`. Expected values must not change.

**Success criteria.** `Interval` no longer owns a calendar, and crypto annualization numbers
are identical.

**Verify.** `grep -rn "periods_per_year" src/pocketquant/core/domain/shared/enums.py` prints
nothing and exits 1, and
`uv run pytest tests/backtest_test/domain/test_performance_calculator_annualization.py tests/core_test/unit/domain/shared/test_interval.py tests/core_test/infra/calendars/ -q`
exits 0 and reports no failures.

---

### Task 3.8 — Phase gate: prove crypto is byte-identical

**Goal.** The refactor changed structure, not output.

**Target files and symbols.**
- `tests/app_test/market_data/test_calendar_refactor_golden.py` — the generator must be
  updated to pass a `Continuous24x7CalendarAdapter()` into the now-calendar-aware functions.
  The committed fixture JSON must NOT be regenerated.

**Steps.**
1. Update only the call shapes in `build_golden_payload()` — add the calendar argument to
   `get_bar_start` and `compute_boundaries`, and read `periods_per_year` from the calendar
   rather than from `Interval`.
2. Do not touch `tests/app_test/market_data/fixtures/crypto_golden_baseline.json`. If the
   test fails, the refactor changed crypto behaviour and the Failure Protocol applies.
3. Run the full suite, the import contracts and the linter.
4. Deploy to the VPS and compare one complete `sync_1m` cron cycle against the previous day:
   `synced_count`, `bars_inserted` and the latest bar values for BTC/ETH/SOL must match.

**Success criteria.** All five gates below hold.

**Verify.** All of the following:
`uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q` exits 0 and
prints `1 passed` against the unregenerated fixture;
`uv run pytest tests/ -q` exits 0 and prints at least `668 passed, 1 skipped`;
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`TZ=America/Chicago uv run pytest tests/ -q` exits 0 and prints at least `668 passed`.

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
title: "Provider Routing Layer"
status: pending
priority: P1
effort: "1d"
dependencies: [3]
---

## Context

Today DI binds exactly one `IDataProviderPort` (`BinanceAdapter`, at
`app/di/infrastructure.py::InfrastructureProvider.get_data_provider`) and exactly one
`IRealtimeQuoteProviderPort` (`BinanceWebSocketAdapter`, at
`app/di/market_data.py::MarketDataProvider.get_realtime_quote_provider`). This phase replaces
both with routing adapters that resolve the provider per symbol from the symbol's asset class
plus an optional per-symbol override.

Because the routing adapters implement the same ports, `SyncService`, `fetch_with_retry`,
`WsSubscriptionAppService` and `QuoteAppService` need no edits. That is G4, and it is the
whole point of doing this before TradingView exists.

This phase ships with **Binance as the only registered provider**. Nothing about crypto may
change.

Verified consumer surface:
- `WsSubscriptionAppService` (`engine/market_data/app_services/ws_subscription_app_service.py`)
  calls `self._provider.subscriptions` (line 68), `subscribe(...)` (line 78) and
  `unsubscribe(symbol=...)` (line 93).
- `QuoteAppService` (`engine/market_data/app_services/quote_app_service.py`) holds
  `self.provider` (line 32) and calls `self.provider.run_forever()` (line 104).
- `IRealtimeQuoteProviderPort` is a `@runtime_checkable` Protocol with 9 members:
  `last_tick_at`, `connect`, `disconnect`, `subscribe`, `unsubscribe`, `run_forever`,
  `is_connected`, `subscription_count`, `subscriptions`.

---

### Task 4.1 — Add the provider-map settings

**Goal.** Provider selection is configuration, not code.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — the `Settings` class (fields end at
  `reconcile_interval_seconds: float = 5.0`, line 74).

**Steps.**
1. Add a `# Market-data provider routing` comment block after line 74.
2. Add `market_data_providers: dict[str, list[str]] = Field(default_factory=lambda: {"crypto_spot": ["binance"], "crypto_perp": ["binance"], "index_future": []})`.
   Keys are `AssetClass` values; the list is an ordered primary-then-fallback chain of
   provider ids. Pydantic Settings parses a JSON object from the env var
   `MARKET_DATA_PROVIDERS` for a `dict` field, so no custom parser is needed.
3. Add `symbol_provider_overrides: dict[str, list[str]] = Field(default_factory=dict)`,
   keyed by composite symbol, parsed from `SYMBOL_PROVIDER_OVERRIDES`.
4. Import `Field` from `pydantic` in `config.py` (it currently imports `MongoDsn`,
   `RedisDsn`, `SecretStr`).
5. Document both field names in `README.md` under the `## Run` section's `.env` sanity
   bullet list. Names only — never values.

**Success criteria.** Both settings parse from JSON env strings and default to Binance-only
crypto.

**Verify.** `MARKET_DATA_PROVIDERS='{"crypto_spot":["binance","tradingview"]}' uv run python -c "from pocketquant.core.config import Settings; import os; print(Settings().market_data_providers['crypto_spot'])"`
exits 0 and prints `['binance', 'tradingview']`.

---

### Task 4.2 — Implement `RoutingDataProviderAdapter`

**Goal.** REST history fetches resolve a provider chain per symbol and fall through on
failure.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/market_data/` with `__init__.py` and
  `routing_data_provider_adapter.py` defining `RoutingDataProviderAdapter(IDataProviderPort)`.

**Steps.**
1. Constructor takes `providers: dict[str, IDataProviderPort]` (keyed by provider id),
   `settings: Settings`, and `symbol_query_service: SymbolQueryService`.
2. Add `async def _chain_for(self, symbol: str) -> list[IDataProviderPort]`:
   - if `symbol.upper()` is in `settings.symbol_provider_overrides`, use that id list;
   - otherwise look up the symbol's `AssetClass` via `symbol_query_service` and use
     `settings.market_data_providers.get(asset_class.value, [])`;
   - map ids to instances, skipping ids with no registered instance and logging one
     WARNING per unknown id per process (keep a `set` of already-warned ids so the warning
     cannot repeat per bar);
   - when the resulting list is empty, fall back to the single registered provider if there
     is exactly one, else raise `ValueError` naming the symbol and the unresolved ids.
3. `fetch_ohlcv(symbol, interval, n_bars)`: try each provider in order. Advance to the next
   provider on an exception or on an empty result. Log the fall-through at WARNING with the
   failed provider id and the reason. Return the first non-empty result; return `[]` when
   every provider is exhausted.
4. `search_symbols(query)`: fan out to every registered provider with
   `asyncio.gather(..., return_exceptions=True)`, drop exception results, and concatenate.
5. `close()`: `await` `close()` on every registered provider, swallowing and logging
   individual failures so one bad provider cannot block shutdown.
6. Log level discipline: per-symbol fetch outcomes are hot-path, so DEBUG. Only the
   fall-through (a degraded condition) is WARNING.

**Success criteria.** A two-provider chain falls through on exception and on empty result,
and returns the first non-empty list.

**Verify.** `no verification needed` — Task 4.5 covers this adapter mechanically.

---

### Task 4.3 — Implement `RoutingRealtimeQuoteProviderAdapter`

**Goal.** WS subscriptions are delegated to the right child provider per symbol, with no
fallback chain.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/market_data/routing_realtime_quote_provider_adapter.py`
  defining `RoutingRealtimeQuoteProviderAdapter`.

**Steps.**
1. Constructor takes the same three arguments as Task 4.2.
2. Implement all nine Protocol members:
   - `last_tick_at`: the maximum non-`None` `last_tick_at` across children, else `None`.
   - `connect()` / `disconnect()`: `asyncio.gather` over children.
   - `subscribe(symbol, callback)`: resolve the **first** provider of the symbol's chain,
     delegate, and record `self._owner[symbol_key] = provider_id`. Return the child's key.
   - `unsubscribe(symbol)`: delegate to the recorded owner; no-op with a DEBUG log when the
     symbol is unknown.
   - `run_forever()`: `await asyncio.gather(*(c.run_forever() for c in children))`.
   - `is_connected()`: `True` when every child with at least one subscription reports
     connected.
   - `subscription_count`: the sum across children.
   - `subscriptions`: a merged dict across children.
3. Add an explicit comment: realtime must NOT use the fallback chain. Two WS providers
   streaming the same symbol would double-count ticks in `BarBuilderDomainService` and
   corrupt the in-progress bar. Only the first id in the chain is used.
4. Add `assert isinstance(instance, IRealtimeQuoteProviderPort)` in the constructor for each
   registered child. The Protocol is `@runtime_checkable`, so this catches a child missing
   one of the nine members at wiring time instead of at first tick.

**Success criteria.** The adapter satisfies `isinstance(x, IRealtimeQuoteProviderPort)` and
delegates per symbol without duplicating streams.

**Verify.** `no verification needed` — Task 4.5 covers this adapter mechanically.

---

### Task 4.4 — Bind the routing adapters in DI

**Goal.** The container yields routing adapters while registering only Binance.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` —
  `InfrastructureProvider.get_data_provider` (currently
  `return BinanceAdapter(settings=settings)`).
- `src/pocketquant/app/di/market_data.py` —
  `MarketDataProvider.get_realtime_quote_provider` (currently
  `return BinanceWebSocketAdapter()  # type: ignore[return-value]`).

**Steps.**
1. In `infrastructure.py`, change `get_data_provider` to build
   `{"binance": BinanceAdapter(settings=settings)}` and return
   `RoutingDataProviderAdapter(providers=..., settings=settings, symbol_query_service=...)`.
   Add `symbol_query_service: SymbolQueryService` to the provider method's parameters so
   Dishka injects it.
2. In `market_data.py`, change `get_realtime_quote_provider` the same way with
   `{"binance": BinanceWebSocketAdapter()}` and
   `RoutingRealtimeQuoteProviderAdapter(...)`. Keep the existing
   `# type: ignore[return-value]  # Protocol satisfied structurally` comment style if pyright
   still needs it.
3. Do not register any second provider in this phase. The `index_future` entry in
   `market_data_providers` stays `[]` until Phase 5.
4. Do not edit `SyncService`, `fetch_with_retry`, `WsSubscriptionAppService` or
   `QuoteAppService`. If any of them requires a change, that is a design regression — stop
   and apply the Failure Protocol.

**Success criteria.** The container resolves both ports to routing adapters and the app boots.

**Verify.** `uv run pytest tests/app_test/integration/test_app_standalone_runtime.py -q`
exits 0 and reports no failures.

---

### Task 4.5 — Test the resolver, the fallback chain, and G4

**Goal.** Routing behaviour is pinned, including the "new provider with zero caller edits"
guarantee.

**Target files and symbols.**
- New test file `tests/core_test/infra/market_data/test_routing_data_provider.py`.
- New test file `tests/core_test/infra/market_data/test_routing_realtime_quote_provider.py`.

**Steps.**
1. In the REST test file, build two stub providers (`stub_a` raising, `stub_b` returning one
   bar) and assert `fetch_ohlcv` returns `stub_b`'s bar and that `stub_b` was called exactly
   once.
2. Add a test where `stub_a` returns `[]`: assert the chain still advances to `stub_b`.
3. Add a test where both fail: assert `fetch_ohlcv` returns `[]` and does not raise.
4. Add a test where `symbol_provider_overrides` names `stub_b` first for one symbol and the
   asset-class map names `stub_a` first: assert the override wins for that symbol and the
   asset-class order applies to a different symbol.
5. **G4 test.** Register a third stub provider `"mock_third"` purely through the settings
   dict and an override entry, with no change to any production module. Assert it receives
   the fetch. Then assert mechanically that the change surface is config-only by keeping this
   test self-contained: it must import nothing from `pocketquant.engine` or `pocketquant.app`.
   Add a module-level comment stating that requirement so a future edit does not silently
   break the guarantee.
6. In the realtime test file, assert `isinstance(adapter, IRealtimeQuoteProviderPort)` is
   `True`; assert `subscribe` on a symbol whose chain is `["stub_a", "stub_b"]` calls only
   `stub_a`; assert `unsubscribe` routes to the same child; assert `subscription_count` sums
   across children; assert a child missing a Protocol member raises at construction.

**Success criteria.** Ten routing tests pass and the G4 test touches no engine or app module.

**Verify.** `uv run pytest tests/core_test/infra/market_data/ -q` exits 0 and prints
`10 passed`, and
`grep -c "pocketquant.engine\|pocketquant.app" tests/core_test/infra/market_data/test_routing_data_provider.py`
prints `0`.

---

### Task 4.6 — Phase gate

**Goal.** The routing layer is in place and the crypto path is untouched.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, the import contracts and the linter.
2. Deploy to the VPS and compare one complete `sync_1m` cron cycle with the pre-deploy day:
   `synced_count` and `bars_inserted` for BTC/ETH/SOL must match, and the WS feed must show
   the same `subscription_count`.

**Success criteria.** All four gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `678 passed, 1 skipped`
(the Phase 1-3 baseline plus the 10 new routing tests);
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q` exits 0 and
prints `1 passed`.

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

=== FILE: phase-05-tradingview-history-and-seed.md ===
---
phase: 5
title: "TradingView History Adapter and Symbol Seed"
status: pending
priority: P1
effort: "2d"
dependencies: [4]
---

## Context

This phase adds the first non-Binance provider and the first non-crypto symbols. The scraper
library is isolated behind an internal client interface so it can be swapped for a different
TradingView transport (or a different vendor entirely) without touching the adapter, the
mappers or any caller. Entitlement — credentials, bar cap, delay flag — is configuration;
there is no branching on TradingView plan tier anywhere.

**Credential rule (hard).** No TradingView username, password or auth token may appear in
this repository, in tests, in docs, in an example env file, or in a log line. Values live
only in `../pocketquant-config/vps/*.env` (prod) and `../pocketquant-config/local/all-local.env`
(dev). The repo carries field names only.

**Timestamp rule (hard).** `tvdatafeed` builds its DataFrame index with naive **local** time
at `tvDatafeed/main.py:143`. Never read timestamps from the DataFrame index. Map from the raw
epoch field with `datetime.fromtimestamp(ts, tz=UTC)`.

Note for the executor: `LIMIT_TVDATAFEED_MAX_BARS = 5000` at
`src/pocketquant/core/common/constants.py:35` is a fossil of an earlier migration away from
this library. It is consumed by `engine/market_data/sync_dtos.py` at lines 9, 22, 24, 51, 53
as a generic bar-count bound. Leave it alone — it is not the TradingView bar cap, and
renaming it would churn the sync DTOs for nothing.

---

### Task 5.1 — Add the TradingView settings

**Goal.** Credentials, bar cap, poll cadence and the delay flag are typed configuration.

**Target files and symbols.**
- `src/pocketquant/core/config.py` — `Settings`, after the provider-routing block added in
  Task 4.1.

**Steps.**
1. Add a `# TradingView (values live only in ../pocketquant-config)` comment block.
2. Add these fields:
   `tradingview_username: str | None = None`,
   `tradingview_password: SecretStr | None = None`,
   `tradingview_auth_token: SecretStr | None = None`,
   `tradingview_max_bars: int = 5000`,
   `tradingview_poll_seconds: int = 60`,
   `tradingview_delayed_data: bool = True`.
3. Use `SecretStr` for both secrets, matching the existing `admin_token: SecretStr | None`
   at line 67 — `SecretStr` prevents accidental logging or serialisation of the value.
4. Default `tradingview_poll_seconds` to `60`, not `10`. CME data is 10-minute delayed on
   every plan until the non-professional add-on is bought, so polling faster only raises ban
   risk without producing fresher data. Record that reason in a comment.
5. Add the six field names (names only) to the `README.md` `## Run` section.
6. Coordinate with the operator to place the values in `../pocketquant-config`. Do not create
   or edit any file inside that directory from this repository's tooling without being asked.

**Success criteria.** The settings load with all-`None` credentials and no exception.

**Verify.** `uv run python -c "from pocketquant.core.config import Settings; s=Settings(); print(s.tradingview_max_bars, s.tradingview_poll_seconds, s.tradingview_delayed_data)"`
exits 0 and prints `5000 60 True`, and
`git grep -i "tradingview_.*=" -- ':!*.md'` prints only field declarations from
`src/pocketquant/core/config.py`.

---

### Task 5.2 — Define the internal TradingView client interface and the mappers

**Goal.** The scraper library is swappable behind one small interface, and timestamps are
built from epochs.

**Target files and symbols.**
- New package `src/pocketquant/core/infra/tradingview/` with `__init__.py`.
- New file `tradingview_client_port.py` defining `ITradingViewClientPort` and a `RawBar`
  dataclass.
- New file `tradingview_mappers.py`.

**Steps.**
1. `RawBar` is a frozen dataclass with `epoch_seconds: float`, `open: float`, `high: float`,
   `low: float`, `close: float`, `volume: float`.
2. `ITradingViewClientPort` is a `Protocol` with
   `async def fetch_bars(self, code: str, exchange: str, interval: Interval, n_bars: int, fut_contract: int | None) -> list[RawBar]`
   and `def is_authenticated(self) -> bool`.
3. In `tradingview_mappers.py`, add `INTERVAL_TO_TRADINGVIEW: dict[Interval, str]` covering
   all seven intervals, mirroring the shape of `INTERVAL_TO_BINANCE` in
   `core/infra/binance/binance_mappers.py`.
4. Add `def split_composite(symbol: str) -> tuple[str, str, int | None]` returning
   `(code, exchange, fut_contract)`. For `"ES1!:CME_MINI"` it returns `("ES", "CME_MINI", 1)`;
   for a code not ending in a digit plus `!` it returns `(code, exchange, None)`. Implement
   the continuous-contract suffix with a compiled regex `^(?P<root>[A-Z0-9]+?)(?P<n>\d)!$`
   so `ES1!` and a hypothetical `ES2!` both work. Do not string-match on `"1!"`.
5. Add `def raw_bar_to_bar(raw: RawBar, symbol: str, interval: Interval) -> Bar` building
   `datetime=datetime.fromtimestamp(raw.epoch_seconds, tz=UTC)`. Add a comment naming
   `tvDatafeed/main.py:143` as the reason the DataFrame index must not be used.
6. Add `def raw_bars_to_bars(raws, symbol, interval) -> list[Bar]` preserving ascending order.

**Success criteria.** `ES1!:CME_MINI` maps to `("ES", "CME_MINI", 1)` and epochs map to aware
UTC datetimes.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_mappers.py -q`
exits 0 (test written in Task 5.5).

---

### Task 5.3 — Implement `TvDatafeedClientAdapter`

**Goal.** The synchronous scraper library is wrapped so it never blocks the event loop and
never crashes the process on a login failure.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tvdatafeed_client_adapter.py` defining
  `TvDatafeedClientAdapter`.
- `pyproject.toml` — dependencies.

**Steps.**
1. Add the library with `uv add "tvdatafeed"`. If the package name on the index differs from
   the import name, record the resolved distribution name in a comment next to the import.
2. In `__init__`, attempt a login using `settings.tradingview_username` and
   `settings.tradingview_password.get_secret_value()` when both are present, otherwise
   construct the no-login client.
3. On a login exception, catch it, log one `logger.warning("provider.tradingview.auth_degraded", reason=...)`
   (never the credential), set `self._authenticated = False`, and continue in no-login mode.
   Login failure must never raise out of the constructor.
4. `is_authenticated()` returns `self._authenticated`.
5. `fetch_bars(...)` calls the library's `get_hist` inside `asyncio.to_thread(...)` because
   the library is synchronous and thread-based.
6. Read each row's raw epoch value and build `RawBar` from it. Do not read the DataFrame
   index. If the library exposes the epoch only through the index, convert with
   `int(idx.value // 10**9)` on the underlying pandas Timestamp and add a comment explaining
   that this reads the epoch, not the localised wall time.
7. `fetch_bars` must never return a naive datetime; it returns `RawBar` (epochs only), so
   this is structural rather than a runtime check.
8. Log per-fetch outcomes at DEBUG (hot path). Log one INFO at construction naming the mode
   (`authenticated` or `anonymous`).

**Success criteria.** The client is constructible with no credentials, reports
`is_authenticated() is False`, and does not raise.

**Verify.** `no verification needed` — Task 5.5 covers this with an offline fixture.

---

### Task 5.4 — Implement `TradingViewAdapter`

**Goal.** A second `IDataProviderPort` implementation that clamps to the configured bar cap
and never emits an in-progress bar.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_adapter.py` defining
  `TradingViewAdapter(IDataProviderPort)`.

**Steps.**
1. Constructor takes `client: ITradingViewClientPort`, `settings: Settings` and
   `symbol_query_service: SymbolQueryService`.
2. `fetch_ohlcv(symbol, interval, n_bars)`:
   - clamp `n_bars` to `min(n_bars, settings.tradingview_max_bars)` and log one DEBUG when
     the clamp bites;
   - split the composite with `split_composite`;
   - call `client.fetch_bars(...)` with the mapped interval and `fut_contract`;
   - map to `Bar` objects with `raw_bars_to_bars`;
   - resolve `calendar = await symbol_query_service.calendar_for(symbol)` and drop any bar
     whose `datetime >= calendar.bar_open(datetime.now(UTC), interval)` — that is the
     in-progress bar. This reuses the same alignment function the sync filter uses, so the
     adapter and the filter can never disagree;
   - for `DAY_1` and `WEEK_1`, populate `session_date = calendar.session_date_of(bar.datetime)`
     and `calendar_id = calendar.calendar_id` on each bar (the fields added in Task 2.11);
   - return the bars in ascending datetime order.
3. `search_symbols(query)` returns `[]` with a DEBUG log. The scraper's search endpoint is
   not part of the agreed scope and the routing adapter already tolerates an empty result.
4. `close()` is a no-op that logs at DEBUG.
5. Do not branch on any plan tier, entitlement level or `tradingview_delayed_data` value
   inside this adapter. The delay flag is a UI and threshold concern only.

**Success criteria.** The adapter clamps, filters the in-progress bar, stamps `session_date`
on daily and weekly bars, and returns aware UTC timestamps.

**Verify.** `no verification needed` — Task 5.5 covers this mechanically.

---

### Task 5.5 — Offline-fixture tests for the TradingView pair

**Goal.** Mapper and adapter behaviour is pinned without any network call.

**Target files and symbols.**
- New test file `tests/core_test/infra/tradingview/test_tradingview_mappers.py`.
- New test file `tests/core_test/infra/tradingview/test_tradingview_adapter.py`.
- New fixture file `tests/core_test/infra/tradingview/fixtures/es1_1h_raw.json` containing
  about 20 synthetic `RawBar` rows for a CME session spanning UTC midnight.

**Steps.**
1. Build the fixture by hand from known session instants: start at the 2026-09-21 session
   open (`2026-09-20T22:00:00Z`, which is Sunday 17:00 CT during DST) and step by one hour.
   Store epoch seconds as integers plus OHLCV floats. Never call the network to produce it.
2. Mapper tests: `split_composite("ES1!:CME_MINI") == ("ES", "CME_MINI", 1)`;
   `split_composite("NQ1!:CME_MINI") == ("NQ", "CME_MINI", 1)`;
   `split_composite("BTCUSDT:BINANCE") == ("BTCUSDT", "BINANCE", None)`;
   `INTERVAL_TO_TRADINGVIEW` has exactly 7 entries;
   `raw_bar_to_bar(...).datetime.tzinfo is UTC` and equals the expected instant.
3. Adapter tests, using a stub `ITradingViewClientPort` that replays the fixture:
   `n_bars=99999` is clamped to `settings.tradingview_max_bars`;
   the most recent, still-open bar is dropped while the closed ones survive;
   `DAY_1` bars carry `session_date` and `calendar_id`;
   every returned `Bar.datetime` is timezone-aware;
   a client that raises propagates the exception so the routing chain can fall through.
4. Mark none of these `@pytest.mark.integration` — they must run in the default suite.

**Success criteria.** Ten offline tests pass with no network access.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/ -q` exits 0 and prints
`10 passed`.

---

### Task 5.6 — Register TradingView in the provider map and DI

**Goal.** `INDEX_FUTURE` symbols route to TradingView; crypto still routes to Binance.

**Target files and symbols.**
- `src/pocketquant/app/di/infrastructure.py` — `get_data_provider`, the providers dict built
  in Task 4.4.
- `../pocketquant-config/local/all-local.env` and `../pocketquant-config/vps/*.env` —
  `MARKET_DATA_PROVIDERS` (operator action, not a repo edit).

**Steps.**
1. In `get_data_provider`, add `"tradingview": TradingViewAdapter(client=TvDatafeedClientAdapter(settings=settings), settings=settings, symbol_query_service=symbol_query_service)`
   to the providers dict.
2. Construct the client lazily or guard it so a missing library or a failed login cannot
   break container construction for a crypto-only deployment: wrap the construction in
   `try/except Exception`, log one WARNING, and omit the `"tradingview"` key when it fails.
   The routing adapter already handles an unregistered id.
3. Ask the operator to set `MARKET_DATA_PROVIDERS` in the config repo to
   `{"crypto_spot":["binance"],"crypto_perp":["binance"],"index_future":["tradingview"]}`.
   Do not commit that value here; the repo default for `index_future` stays `[]`.
4. Add `provider.tradingview` state to the health payload in Task 7.4; do not do it here.

**Success criteria.** With `index_future` mapped to `tradingview`, a futures symbol resolves
to the TradingView adapter and a crypto symbol still resolves to Binance.

**Verify.** `uv run pytest tests/app_test/integration/test_app_standalone_runtime.py -q`
exits 0 and reports no failures.

---

### Task 5.7 — Seed the three futures symbols

**Goal.** `ES1!:CME_MINI`, `NQ1!:CME_MINI` and `YM1!:CBOT_MINI` exist in `symbols` and in
`tracked_symbols`.

**Target files and symbols.**
- New file `scripts/seed_index_future_symbols.py`.
- `scripts/README.md` — the script inventory list.

**Steps.**
1. Follow the conventions in `scripts/README.md`: read `MONGODB_URL` and `MONGODB_DATABASE`
   from the environment, dry-run by default, `--apply` to write.
2. Upsert three `Symbol` records through `SymbolRepository.upsert` with:
   - `ES1!:CME_MINI`, name "E-mini S&P 500 continuous", `asset_class=INDEX_FUTURE`,
     `calendar_id=CME_GLOBEX_EQUITY`, `ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, currency="USD", commission_kind="per_contract")`;
   - `NQ1!:CME_MINI`, name "E-mini Nasdaq-100 continuous", same calendar,
     `ContractSpec(multiplier=20.0, tick_size=0.25, lot_step=1.0, ...)`;
   - `YM1!:CBOT_MINI`, name "E-mini Dow continuous", same calendar,
     `ContractSpec(multiplier=5.0, tick_size=1.0, lot_step=1.0, ...)`.
3. Upsert the same three composites into `tracked_symbols` through
   `TrackedSymbolRepository`, with `seeded_from="admin"`.
4. Print the three composites and the resulting counts.
5. Add a bullet to `scripts/README.md`.
6. Run with `--apply` against the target database.

**Success criteria.** All three symbols are present in both collections with the correct
multipliers.

**Verify.** `curl -s localhost:41921/api/v1/symbols | uv run python -c "import sys,json; d=json.load(sys.stdin); m={s['symbol']: s['contract_spec']['multiplier'] for s in d if s['asset_class']=='index_future'}; print(m)"`
exits 0 and prints `{'ES1!:CME_MINI': 50.0, 'NQ1!:CME_MINI': 20.0, 'YM1!:CBOT_MINI': 5.0}`.

---

### Task 5.8 — Run the initial backfill to the configured cap

**Goal.** Each futures symbol holds the maximum history the provider allows for every
interval, and the cron accumulates forward from there.

**Target files and symbols.**
- The existing tracked-symbol backfill route:
  `src/pocketquant/app/routes/tracked_symbols.py` and
  `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`
  (`BackfillTrackedSymbolCommand`, `TrackedSymbolBackfillService.run`).

**Steps.**
1. For each of the three symbols and each interval in
   `1m, 5m, 15m, 1h, 4h, 1d, 1w`, invoke the backfill endpoint in **direct** mode (not
   cascade mode) with `n_bars = settings.tradingview_max_bars`.
   `_CASCADE_DEFAULT_INTERVALS` in `tracked_symbols_backfill.py` (lines 30-36) defaults 5m
   through 1d to cascade mode — you must override `mode` to `direct` for these symbols.
2. Record the rationale in the phase notes: do NOT backfill futures 1d bars by cascading 1m
   across UTC midnight, even temporarily. The daily bars would never match the TradingView
   chart the user compares against. Fetch 1d and 1w natively, exactly as the code already
   does for Binance weekly klines (`sync_jobs.py:51-53`).
3. After each call, record the resulting bar count per symbol and interval.
4. Expect roughly 1,380 1m bars per CME trading day, so a 5,000-bar cap is about 3.6 trading
   days of 1m history. That is the accepted trade-off, not a defect.

**Success criteria.** Every symbol/interval pair has a non-zero bar count, and 1m equals
`min(tradingview_max_bars, available)`.

**Verify.** `curl -s "localhost:41921/api/v1/market-data/sync-status/ES1%3ACME_MINI?interval=1m"`
returns HTTP 200 with a JSON body whose `bar_count` is greater than `1000`. (Use the
URL-encoded composite; `!` needs no encoding but `:` must be `%3A`.)

---

### Task 5.9 — Phase gate: one full week of quiet operation

**Goal.** The futures pipeline produces correct bars and no anomaly noise across a weekend.

**Target files and symbols.** None (observation only).

**Steps.**
1. Deploy and let the cron run for seven consecutive days, including one weekend.
2. Each day, query the logs for these event names scoped to `ES1!:CME_MINI`:
   `market_data.sync.misaligned_bars_dropped`, `integrity.issues_found`,
   `market_data.sync.no_progress`, `market_data.sync.stuck_threshold_crossed`,
   `cascade.partial_aggregate`.
3. Confirm `sync_verify_cascade` — which already compares provider 5m against cascaded 5m
   for one symbol per hour (`sync_jobs.py:696-701`, `"0 * * * *"`) — runs against ES for at
   least 24 consecutive hours. Point it at ES for that window.
4. Confirm the 4h bar `datetime` values are session-open anchored (22:00 or 23:00 UTC) and
   never 00:00 or 04:00 UTC.
5. Confirm G1: during a live CME session, the newest 1m bar is within 2 minutes of now
   (within 12 minutes while `tradingview_delayed_data` is `true`).

**Success criteria.** All five gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `688 passed, 1 skipped`;
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
a log query over the seven-day window returns zero events for `ES1!:CME_MINI` across all five
event names listed in step 2;
`sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0` for 24
consecutive runs;
`curl -s "localhost:41921/api/v1/market-data/ohlcv/ES1%3ACME_MINI/1m?limit=1"` returns HTTP 200
during a session with a `datetime` within 12 minutes of `date -u +%FT%TZ`.

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
title: "Realtime Quotes and Contract Math"
status: pending
priority: P1
effort: "1.5d"
dependencies: [5]
---

## Context

Two independent pieces land here. First, a polling realtime quote adapter so a paper ES
strategy can run a live session. Second, contract-aware PnL: today every PnL path computes
`price x quantity`, which is correct for crypto and wrong by a factor of 50 for ES.

**Keep the margin accounting.** `PaperBrokerAdapter` was already migrated to futures/margin
accounting (1x leverage, only close or reduce touches balance) in plan `260628-2013`; see
`docs/journals/2026-06-28-paper-broker-futures-accounting.md` and
`tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py`. That is **margin**
accounting, not a contract spec. Do not redo it. This phase adds only the unit conversion.

Verified PnL sites:
- `PositionAggregate._calculate_pnl_per_unit` (`core/domain/position/entities.py:214-218`)
  returns a per-unit price delta.
- `reduce_quantity` (line 127) computes `realized = pnl_per_unit * quantity` at line 149 and
  emits `TradeClosedEvent(pnl=realized, ...)`.
- `unrealized_pnl` (property, line 224) returns `self._calculate_pnl_per_unit(self.current_price) * self.quantity`.
- `PaperBrokerAdapter._can_afford` (`core/infra/brokers/paper/paper_broker_adapter.py:487-500`)
  compares `fill_price * order.quantity + commission <= self._balance`.
- `PaperBrokerAdapter.get_balance` (line 418) sums `p.unrealized_pnl`.
- `PositionAggregate.market_value` returns `self.quantity * self.current_price`.

Putting the multiplier on `PositionAggregate` is the single smallest change that makes
realized PnL, unrealized PnL, the trade event and the equity curve all correct at once.

---

### Task 6.1 — Implement `TradingViewQuoteAdapter`

**Goal.** A realtime quote provider that polls bar closes during session hours and satisfies
the nine-member Protocol.

**Target files and symbols.**
- New file `src/pocketquant/core/infra/tradingview/tradingview_quote_adapter.py` defining
  `TradingViewQuoteAdapter`.
- Reference for the quote-dict contract: `core/infra/binance/binance_mappers.py`
  (`aggtrade_to_quote_dict`) and the consumer `QuoteAppService.on_quote_update`
  (`engine/market_data/app_services/quote_app_service.py:37`).

**Steps.**
1. Constructor takes `client: ITradingViewClientPort`, `settings: Settings` and
   `symbol_query_service: SymbolQueryService`.
2. Implement all nine Protocol members. Hold `self._subscriptions: dict[str, Callable]`,
   `self._tasks: dict[str, asyncio.Task]`, `self._last_close: dict[str, float]` and
   `self.last_tick_at: datetime | None`.
3. `subscribe(symbol, callback)` registers the callback and starts one polling task for the
   symbol. `unsubscribe(symbol)` cancels the task and awaits it with
   `contextlib.suppress(asyncio.CancelledError)`.
4. Each polling task loops: resolve the calendar for the symbol; when
   `calendar.is_open(datetime.now(UTC))` is `False`, sleep `settings.tradingview_poll_seconds`
   and continue without any fetch; otherwise fetch the latest 2 bars at `Interval.MINUTE_1`,
   and when the newest closed bar's close differs from `self._last_close[symbol]`, emit a
   quote dict through the callback and update `self.last_tick_at`.
5. The emitted dict must match the shape `QuoteAppService.on_quote_update` already consumes.
   Read that function before writing the dict and mirror its keys exactly. Set the per-tick
   volume delta to the bar's volume and `tick_count` to 1 — per-tick volume is unavailable
   from a polling source, and `BarBuilderDomainService.add_tick` requires a delta, not a
   cumulative total.
6. `run_forever()` awaits `asyncio.gather(*self._tasks.values())` and returns when there are
   no tasks. `is_connected()` returns `client.is_authenticated() or bool(self._tasks)` — a
   degraded anonymous client that is still polling counts as connected.
7. Wrap each poll iteration in `try/except Exception` that logs at WARNING and continues.
   A scraper hiccup must never kill the task.
8. Log per-poll activity at DEBUG only. The loop runs once per symbol per
   `tradingview_poll_seconds`, which is per-tick frequency by the CLAUDE.md rule.

**Success criteria.** The adapter satisfies the Protocol, polls only while the calendar
reports open, and emits only on a close change.

**Verify.** `uv run pytest tests/core_test/infra/tradingview/test_tradingview_quote_adapter.py -q`
exits 0 and prints `5 passed` (tests: Protocol isinstance; no fetch while closed; emit on
close change; no emit on unchanged close; `unsubscribe` cancels the task).

---

### Task 6.2 — Loosen the staleness thresholds for the polling provider

**Goal.** A 60-second polling cadence does not trip a watchdog tuned for a per-trade WS feed.

**Target files and symbols.**
- `src/pocketquant/engine/market_data/sync_status_service.py:29-30` —
  `_STUCK_MULTIPLIER = 3`.
- `src/pocketquant/engine/market_data/sync_internals/anomaly_log.py:17` —
  `_STUCK_STREAK_THRESHOLD = 3`.
- `src/pocketquant/app/di/market_data.py` — the realtime provider registration.

**Steps.**
1. Do not change either constant globally — that would weaken the crypto watchdog.
2. Instead, in `_is_stuck` (already calendar-aware after Task 3.5), add the poll cadence as a
   floor: a symbol cannot be stuck until `age > max(_STUCK_MULTIPLIER * cadence, 3 * settings.tradingview_poll_seconds)`
   when its calendar is not the 24/7 one. Pass `settings` into `SyncStatusQueryService`.
3. Record in a comment that a delayed, polled provider makes `last_tick_at` semantics
   coarser: `tick_count` is 1 per poll and per-tick volume deltas are unavailable.
4. Register the quote adapter in `app/di/market_data.py::get_realtime_quote_provider`'s
   providers dict as `"tradingview"`, guarded by the same `try/except` pattern used in
   Task 5.6 step 2.

**Success criteria.** A futures symbol at a 60-second cadence is not flagged stuck, and crypto
thresholds are unchanged.

**Verify.** `uv run pytest tests/app_test/unit/handlers/status/test_sync_status_service.py -q`
exits 0 and reports no failures.

---

### Task 6.3 — Add `PerContractCommissionModel`

**Goal.** Futures commission is charged per contract, not as a percentage of notional.

**Target files and symbols.**
- `src/pocketquant/core/domain/trading/commission_model.py` — the `CommissionModel` Protocol
  (lines 4-5) and `PercentageCommissionModel` (lines 8-13).
- `src/pocketquant/core/domain/trading/__init__.py` — the export list.
- `tests/core_test/unit/domain/trading/test_commission_model.py`.

**Steps.**
1. Add `class PerContractCommissionModel:` with `__init__(self, usd_per_contract: float)` and
   `def compute(self, price: float, quantity: float) -> float: return abs(quantity) * self._usd_per_contract`.
   The `price` parameter is unused but required by the `CommissionModel` Protocol at line 5 —
   keep the signature identical and note why in a one-line comment.
2. Export it from `core/domain/trading/__init__.py` next to `PercentageCommissionModel`.
3. Add two tests to `test_commission_model.py`: `compute(4500.0, 2) == 2 * usd_per_contract`
   regardless of price, and `compute(4500.0, -2)` returns the same positive value.

**Success criteria.** Commission for 2 ES contracts is price-independent.

**Verify.** `uv run pytest tests/core_test/unit/domain/trading/test_commission_model.py -q`
exits 0 and reports no failures with at least 2 more tests than before.

---

### Task 6.4 — Put the contract multiplier on `PositionAggregate`

**Goal.** Realized PnL, unrealized PnL, the trade event and the equity curve all convert
points to dollars in one place.

**Target files and symbols.**
- `src/pocketquant/core/domain/position/entities.py` — the `PositionAggregate` fields
  (lines 27-44), `open` classmethod (line 47), `reduce_quantity` (line 127, realized at
  line 149, `TradeClosedEvent` at lines ~160-180), `unrealized_pnl` property (line 224),
  `market_value` property (line ~234), `to_mongo` (line ~250) and `from_mongo` (line ~265).
- `tests/core_test/unit/domain/position/test_position_trade_emission.py`.

**Steps.**
1. Add the field `contract_multiplier: float = 1.0` after `entry_commission` at line 43.
   Document it as "points-to-currency conversion; 1.0 for linear instruments (all crypto),
   50.0 for ES, 20.0 for NQ, 5.0 for YM".
2. Add `contract_multiplier: float = 1.0` as a keyword parameter of the `open` classmethod
   and pass it into the constructed instance.
3. In `reduce_quantity`, change line 149's calculation to
   `realized = pnl_per_unit * quantity * self.contract_multiplier`. Do not change
   `_calculate_pnl_per_unit` — it must stay a pure price delta so the multiplier is applied
   exactly once.
4. In the `unrealized_pnl` property, change the return to
   `self._calculate_pnl_per_unit(self.current_price) * self.quantity * self.contract_multiplier`.
5. In `market_value`, change the return to
   `self.quantity * self.current_price * self.contract_multiplier`.
6. Serialize `contract_multiplier` in `to_mongo` and read it in `from_mongo` with a default
   of `1.0`, so existing position documents load unchanged.
7. Add two tests to `test_position_trade_emission.py`: a LONG of 2 contracts with
   `contract_multiplier=50.0`, entry 4500.00, exit 4500.25, asserts
   `TradeClosedEvent.pnl == 25.0` exactly; the same position with the default multiplier
   asserts `0.5`, proving the crypto path is unchanged.

**Success criteria.** `(4500.25 - 4500.00) x 50 x 2 == 25.00` and the default path is
byte-identical.

**Verify.** `uv run pytest tests/core_test/unit/domain/position/ -q` exits 0 and reports no
failures with at least 2 more tests than before.

---

### Task 6.5 — Thread `ContractSpec` through the paper broker

**Goal.** The paper broker opens positions with the right multiplier, charges the right
commission model, and sizes affordability on margin rather than notional.

**Target files and symbols.**
- `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py` — `__init__`
  (lines 108-143), `_open_position` (line 561, sets `quantity=order.quantity` at line 575),
  `_can_afford` (lines 487-500), `_commission` (lines 484-485).
- `src/pocketquant/core/infra/brokers/broker_factory.py` — `BrokerFactory.create`, the
  `"paper"` branch at lines 32-44.
- `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:111-131` —
  `create_broker`.

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` as the last constructor parameter of
   `PaperBrokerAdapter` and store
   `self._contract_spec = contract_spec or LINEAR_CONTRACT_SPEC`.
2. In `_open_position`, pass `contract_multiplier=self._contract_spec.multiplier` into
   `PositionAggregate.open(...)`.
3. In `_can_afford` (line 500), change the comparison to
   `fill_price * order.quantity * self._contract_spec.multiplier + commission <= self._balance`
   **only when** `self._contract_spec.multiplier == 1.0`. For a multiplier greater than 1,
   the notional exceeds any sane paper balance, and the margin model that shipped in plan
   `260628-2013` already governs balance movement — so for contract instruments compare
   `commission <= self._balance` and add a comment naming that plan. Do not redesign the
   margin model here.
4. In `BrokerFactory.create`, read `contract_spec = config.get("contract_spec")` and
   `commission_per_contract = config.get("commission_per_contract")`. When
   `contract_spec` has `commission_kind == "per_contract"`, build
   `PerContractCommissionModel(commission_per_contract or 2.5)` instead of
   `PercentageCommissionModel(bps=commission_bps)`. Pass `contract_spec` to the adapter.
   Keep the existing bps path exactly as it is for crypto.
5. In `BacktestSandboxAppService.create_broker`, add a `contract_spec: ContractSpec | None = None`
   parameter and a `commission_per_contract: float | None = None` parameter, select the
   commission model the same way, and pass both to `PaperBrokerAdapter`.
6. Default everything to the linear spec so every existing caller keeps today's behaviour
   without edits.

**Success criteria.** A paper broker constructed with no `contract_spec` behaves exactly as
before; one constructed with the ES spec produces 50x PnL.

**Verify.** `uv run pytest tests/core_test/infra/brokers/ tests/backtest_test/engine/test_paper_broker_limit_orders.py tests/backtest_test/engine/test_paper_broker_order_events.py tests/backtest_test/engine/test_paper_broker_trade_emission.py -q`
exits 0 and reports no failures, including the existing
`paper_broker_futures_accounting_test.py`.

---

### Task 6.6 — Make position sizing contract-aware

**Goal.** Sizing returns whole contracts for futures and is unchanged for crypto.

**Target files and symbols.**
- `src/pocketquant/core/domain/risk/services/position_calculator_domain_service.py` —
  `calculate` (lines 17-46), specifically `cap` at line 40, `size` at line 41,
  `notional` at line 42, `est` at line 43.

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` as the last keyword parameter of
   `calculate`, defaulting to the linear spec inside the body.
2. Multiply the price-risk conversion by the multiplier: change line 41 to
   `size = min(risk_amount / (price_risk * spec.multiplier), cap)` and line 40 to
   `cap = (account_balance * max_exposure) / (entry_price * spec.multiplier)`.
   With `multiplier == 1.0` both expressions are arithmetically identical to today's.
3. After computing `size`, when `spec.lot_step` is not `None`, floor it:
   `size = math.floor(size / spec.lot_step) * spec.lot_step`. Return the existing
   zero-result `PositionCalculation(0.0, 0.0, 0.0, 0.0)` when the floored size is `0`, so a
   sub-one-contract signal produces no order rather than a fractional contract.
4. Change `notional = size * entry_price * spec.multiplier`.
5. Write `tests/core_test/unit/domain/risk/test_position_calculator_contract_spec.py` with
   three tests: default spec reproduces the existing numbers for a known input; an ES spec
   with `lot_step=1.0` returns an integer size; an account too small for one ES contract
   returns size `0.0`.

**Success criteria.** Crypto sizing is unchanged and futures sizing is whole contracts.

**Verify.** `uv run pytest tests/core_test/unit/domain/risk/ -q` exits 0 and prints
`3 passed`.

---

### Task 6.7 — Thread the contract spec into the backtest run

**Goal.** A 1h ES backtest reports dollar PnL and Sharpe consistent with the contract spec.

**Target files and symbols.**
- `src/pocketquant/core/domain/backtest/config.py` — `BacktestConfig` (lines 26-36; already
  gained `calendar_id` in Task 3.7).
- `src/pocketquant/engine/backtest/backtest_dispatch.py:42-54` — `_config_from_dict`;
  lines 91-95 — the `sandbox.create_broker(...)` call.
- `src/pocketquant/engine/backtest/backtest_command_service.py:74-78` — the payload dict.
- `src/pocketquant/engine/backtest/backtest_strategy_loader.py:54-62` —
  `build_backtest_config`.

**Steps.**
1. Add `contract_spec: ContractSpec | None = None` and
   `commission_per_contract: float | None = None` to `BacktestConfig`.
2. In `BacktestCommandService`, resolve the symbol's `calendar_id` and `contract_spec` from
   `SymbolQueryService` when building the payload at lines 74-78, and include both keys.
   Inject `SymbolQueryService` into the command service constructor.
3. In `_config_from_dict`, read both keys back, rebuilding `ContractSpec` with
   `ContractSpec.from_mongo(payload["contract_spec"])` when present.
4. In `run_single`, pass `contract_spec=config.contract_spec` and
   `commission_per_contract=config.commission_per_contract` into
   `sandbox.create_broker(...)` at lines 91-95.
5. In `build_backtest_config`, accept and forward `calendar_id` and `contract_spec` so the
   strategy-driven backtest path matches the ad-hoc path.
6. `BacktestReportAppService` already reads `config.calendar_id` for annualization after
   Task 3.7 — no further change is needed there.

**Success criteria.** An ES backtest annualizes on the CME calendar and reports dollar PnL
using the multiplier.

**Verify.** `no verification needed` — Task 6.8 covers this end to end.

---

### Task 6.8 — Prove G2 and G3

**Goal.** A live paper session and a backtest both produce contract-correct USD results.

**Target files and symbols.**
- New test file `tests/backtest_test/engine/test_es_contract_backtest.py`.
- Live observation on the VPS (no file).

**Steps.**
1. **G3 (automated).** Write a backtest test using a synthetic ES 1h bar series and the ES
   contract spec. Assert that a one-round-trip strategy entering at 4500.00 and exiting at
   4500.25 with 2 contracts reports `total_pnl == 25.0` minus commission, and that the
   reported `periods_per_year` used for Sharpe is `252 * 23 == 5796.0`, not `8760`.
   Read `periods_per_year` from the persisted run's config snapshot or expose it through the
   metrics payload — do not re-derive it in the test.
2. **G2 (manual observation).** During one live CME session, run a paper ES strategy for the
   full session. Confirm: a round trip of 2 contracts entering 4500.00 and exiting 4500.25
   records realized PnL of 25.00 USD minus per-contract commission; the equity curve shows no
   jump at fill time other than commission (that is the margin model from plan `260628-2013`
   behaving correctly).
3. Record both results in the completion report produced in Phase 7.

**Success criteria.** G3 is proven by a test; G2 is proven by a recorded live session.

**Verify.** `uv run pytest tests/backtest_test/engine/test_es_contract_backtest.py -q` exits
0 and prints `2 passed`.

---

### Task 6.9 — Phase gate

**Goal.** Contract math is correct everywhere and crypto is untouched.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite, the import contracts and the linter.
2. Re-run the golden-file test to confirm the crypto performance metrics are still identical.

**Success criteria.** All four gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `702 passed, 1 skipped`;
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`uv run pytest tests/app_test/market_data/test_calendar_refactor_golden.py -q` exits 0 and
prints `1 passed`.

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
title: "UI, Docs and Success-Metric Run-Through"
status: pending
priority: P2
effort: "1d"
dependencies: [6]
---

## Context

The functional work is done. This phase removes the Binance-only assumptions left in the SPA
copy, surfaces provider and session state on `/health`, updates the two documents that
describe where things live, and records the eighteen success metrics against a live run.

Verified UI facts:
- Symbol selection is data-driven: `SymbolSelector`
  (`web/src/components/controls/symbol-selector.tsx`) renders whatever `/api/v1/symbols`
  returns and already splits the composite into a code plus an `exchange-badge` span at
  lines 46-47. Seeding the three symbols in Phase 5 made them selectable with no code change.
- Frontend symbol validation is `trimmed.includes(':')` only
  (`add-symbol-dialog.tsx:24`, `backtest-form.tsx:72`), so `!` already passes.
- What remains is copy: eleven `BTCUSDT:BINANCE` occurrences across `web/src`, of which three
  are user-visible.

---

### Task 7.1 — Replace the user-visible Binance-only placeholders

**Goal.** No input placeholder or default value implies the platform is crypto-only.

**Target files and symbols.**
- `web/src/components/strategy/add-symbol-dialog.tsx` — the placeholder at line 72
  (`placeholder="e.g. BTCUSDT:BINANCE"`) and the two error strings at lines 23 and 24.
- `web/src/components/backtest/backtest-form.tsx` — the `useState('BTCUSDT:BINANCE')` default
  at line 44 and the error string at line 72.
- `web/src/routes/__root.tsx:17` and `web/src/routes/index.tsx:21` — the
  `'BTCUSDT:BINANCE'` route-search fallbacks.

**Steps.**
1. Change the `add-symbol-dialog.tsx` placeholder to `"e.g. BTCUSDT:BINANCE or ES1!:CME_MINI"`
   and update the two error strings at lines 23-24 to use `CODE:EXCHANGE` without naming a
   venue.
2. Change the `backtest-form.tsx` error string at line 72 the same way. Leave the
   `useState` default at line 44 as `'BTCUSDT:BINANCE'` — a default must be a real, populated
   symbol, and changing it would alter the first-load behaviour for existing users.
3. Leave the route-search fallbacks in `__root.tsx:17` and `index.tsx:21` unchanged for the
   same reason.
4. Leave the eight `BTCUSDT:BINANCE` occurrences that are JSDoc examples
   (`ticker-widget.tsx:6`, `trading-chart.tsx:38`, `symbol-selector.tsx:6`,
   `symbol-format.ts:2`, `strategy-api.ts:11`, `backtest-api.ts:284`,
   `use-available-intervals.ts:29`, `use-ohlcv.ts:13`, `types/market-data.ts:20`,
   `types/quote.ts:3`) unchanged. They document the composite *format*, and a format example
   should be the most familiar one.
5. Confirm the exchange badge renders correctly by loading the chart with each futures
   symbol selected.

**Success criteria.** The two user-facing placeholders and three error strings are
venue-neutral, and the badge shows `CME_MINI` and `CBOT_MINI`.

**Verify.** `grep -c "BTCUSDT:BINANCE" web/src/components/strategy/add-symbol-dialog.tsx`
prints `1` (the widened placeholder only), and `cd web && npm run build` exits 0.

---

### Task 7.2 — Ship the "closed" session state in the monitor

**Goal.** A closed market reads as closed in the UI, not as a red stuck badge.

**Target files and symbols.**
- `web/src/components/monitor/data-health-row.tsx` — lines 50, 55, 72.
- `web/src/components/monitor/format-helpers.ts:19`.
- `web/src/lib/datetime.ts:88-97` — `ageColorClass`.
- `web/src/types/market-data.ts:88` — `is_stuck?: boolean`.

**Steps.**
1. Confirm the `is_market_open` field added in Phase 3, Task 3.5 is present in the
   `/api/v1/market-data/sync-status` response.
2. Confirm the four frontend edits from Task 3.5 steps 7-10 are in place and rendering:
   the `Closed` badge replaces `StuckBadge`, `format-helpers.ts` returns `'neutral'`, and
   `ageColorClass` returns `'age-neutral'` when `is_market_open` is `false`.
3. If any of them was deferred in Phase 3, complete it now. Do not duplicate the logic.
4. Observe the monitor over one weekend and confirm the three futures rows show `Closed`
   with a neutral age colour for the whole weekend and zero stuck badges.

**Success criteria.** Futures rows show `Closed` over the weekend; crypto rows are unaffected.

**Verify.** `grep -c "is_market_open" web/src/components/monitor/data-health-row.tsx web/src/components/monitor/format-helpers.ts`
prints a non-zero count for both files, and `cd web && npm run build` exits 0.

---

### Task 7.3 — Update the documentation

**Goal.** The two documents an agent reads to orient itself describe the new shape.

**Target files and symbols.**
- `docs/system-architecture.md` — the "Where Does X Live?" table (starts line 479), the
  "Dependencies" section (line 777), the "External Services" line under "Ops Context"
  (line ~795), and the "Configuration" env-var list (line 775).
- `README.md` — the `## Run` section `.env` bullets.

**Steps.**
1. Add four rows to the "Where Does X Live?" table:
   trading calendar port -> `core/domain/market_data/trading_calendar_port.py`;
   calendar implementations and factory -> `core/infra/calendars/`;
   provider routing adapters -> `core/infra/market_data/`;
   TradingView client, mappers and adapters -> `core/infra/tradingview/`.
2. In "Dependencies" (line 777), add `pandas-market-calendars` (CME session calendar) and
   `tvdatafeed` (TradingView history and quotes) to the prose list.
3. In "External Services" under "Ops Context", add TradingView beside Binance and OKX, and
   note that credentials live only in `pocketquant-config`.
4. In "Configuration" (line 775), add the env-var **names** `MARKET_DATA_PROVIDERS`,
   `SYMBOL_PROVIDER_OVERRIDES`, `TZ`, and the six `TRADINGVIEW_*` names. Names only.
5. Add a short "Asset classes and trading calendars" subsection under "Bounded Contexts"
   (line 800) stating: the asset class binds the annualization basis and contract-spec shape;
   the calendar id on the symbol record names the schedule; the schedule rules live in code
   behind `ITradingCalendarPort`; adding an asset class is a new enum member plus a new
   calendar adapter, never new branching.
6. In `README.md`, add the new env-var names to the `.env` bullets under `## Run`, and add
   `just test-tz` to the `## Tests & Gates` block. While there, fix the stale
   "7 import-linter contracts" comment in that block — the real count is 9 after Task 2.8.
7. Do not add a new document. Both of these already own the relevant surface.

**Success criteria.** Both documents describe the calendar, routing and TradingView layers,
and the import-contract count is accurate.

**Verify.** `grep -c "trading_calendar_port\|core/infra/calendars\|core/infra/tradingview\|core/infra/market_data" docs/system-architecture.md`
prints at least `4`, and `grep -c "7 import-linter contracts" README.md` prints `0`.

---

### Task 7.4 — Surface provider and session state on `/health`

**Goal.** "Why are there no ES bars" becomes a glance instead of a log hunt.

**Target files and symbols.**
- `src/pocketquant/app/main_extensions.py:267-270` — `register_health_checks`, which today
  registers only `database` and `redis` on the `HealthCoordinator`.
- `src/pocketquant/core/common/health/coordinator.py:11` — `HealthCoordinator.register`.
- `src/pocketquant/app/main_extensions.py:364-372` — the `/health` route.

**Steps.**
1. Add a `check_market_data_providers` coroutine in a new file
   `src/pocketquant/core/infra/market_data/provider_health_check.py`. It takes the
   `RoutingDataProviderAdapter` and returns a dict with, per registered provider id:
   `registered: true`, `authenticated` (for TradingView, from
   `client.is_authenticated()`; `true` for Binance), and
   `last_success_at` (an ISO string via `to_utc_iso`, tracked by the routing adapter on each
   successful `fetch_ohlcv`).
2. Add a `last_success_at: dict[str, datetime]` attribute to `RoutingDataProviderAdapter`
   and update it on each successful fetch. This is a process-local, APP-scoped singleton
   attribute and therefore shared across all requests — correct here, because provider health
   is global state, not per-request state.
3. Add a `sessions` block listing, for every tracked symbol, its `calendar_id` and the
   current `is_open` boolean.
4. Register it in `register_health_checks` as
   `hc.register("market_data_providers", partial(check_market_data_providers, provider))`,
   resolving the provider from the container exactly as `database` and `redis` are resolved.
5. Keep the payload bounded: provider ids and booleans only, no bar arrays and no
   `model_dump()` of large models. The CLAUDE.md rule forbids unbounded payloads above DEBUG,
   and this one is served on every health poll.

**Success criteria.** `/health` reports per-provider auth state and per-symbol session state.

**Verify.** `curl -s localhost:41921/health | uv run python -c "import sys,json; d=json.load(sys.stdin); print(sorted(d['market_data_providers']['providers']))"`
exits 0 and prints a list containing `'binance'` and `'tradingview'`.

---

### Task 7.5 — Run the success metrics and write the completion report

**Goal.** Every stated metric is measured against a live run and recorded.

**Target files and symbols.**
- New file `plans/260921-1436-asset-class-index-futures/completion-report.md`.

**Steps.**
1. Run and record each of these on the VPS during a live CME session, one line per metric
   with the measured value:
   1. `TZ=Asia/Saigon` startup exits non-zero with the timezone assertion; `TZ=UTC` starts.
   2. Every cron job reports the same `next_run_time` under all three zones; `sync_backfill`
      fires at 03:00 UTC.
   3. On a Thursday-to-Sunday run, the latest `1w` bar for `BTCUSDT:BINANCE` opens on the
      previous Monday 00:00 UTC.
   4. Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`,
      `stuck_threshold_crossed` and `partial_aggregate` events for `ES1!:CME_MINI` across one
      week including a weekend and one early-close holiday.
   5. Futures 1d bars open 17:00 CT and close 16:00 CT with `session_date` populated, on both
      sides of a DST transition.
   6. The golden-file test passes against the unregenerated fixture.
   7. `uv run ruff check src tests` passes with `DTZ`; `uv run pytest` passes with zero added
      skips; the test count is at or above `702 passed, 1 skipped`.
   8. The DST suite passes:
      `session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
      `session_open(2026-11-02) == 2026-11-01T23:00:00Z`.
   9. **G1** — a 1m ES bar within 2 minutes of now (12 while delayed).
   10. Over one weekend, `job_history` shows `sync_1m` details with `status="skipped"` and
       `error="closed"` for the three futures symbols, and zero `no_progress` entries.
   11. `sync_verify_cascade` on `ES1!:CME_MINI` reports `divergent_fraction = 0.0` for 24
       consecutive runs, and the 4h `datetime` values are 22:00 or 23:00 UTC.
   12. `bars` count for `ES1!:CME_MINI` at 1m equals `min(tradingview_max_bars, available)`
       after backfill and grows by about 1,380 per trading day.
   13. **G2** — the live paper round trip from Phase 6 Task 6.8 step 2.
   14. **G3** — the backtest result from Phase 6 Task 6.8 step 1.
   15. **G4** — the mock-third-provider test from Phase 4 Task 4.5 step 5.
   16. **G5** — `sync_1m` for BTC/ETH/SOL produces the same `synced_count` and bar values as
       before the change over one full cron cycle.
   17. **G6** — the non-UTC refusal plus the DST suite, both already covered above.
   18. Secrets — `git grep -i "tradingview_.*=" -- ':!*.md'` finds only field declarations.
2. Write the report with one section per metric, the command used, and the measured value.
   Record any metric that could not be measured (for example, an early-close holiday that
   does not fall inside the observation window) as explicitly deferred, with the date it can
   next be measured. Do not mark a deferred metric as passed.
3. Link the report from `plan.md`'s Success criteria section.

**Success criteria.** All eighteen metrics are recorded with measured values or an explicit,
dated deferral.

**Verify.** `test -s plans/260921-1436-asset-class-index-futures/completion-report.md` exits 0
and `grep -c "^## " plans/260921-1436-asset-class-index-futures/completion-report.md` prints
at least `18`.

---

### Task 7.6 — Final gate

**Goal.** The whole plan is provably complete.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run every automated gate one final time on a clean checkout of the branch.
2. Confirm no secret value entered the repository at any point.

**Success criteria.** All five gates below hold.

**Verify.** All of the following:
`uv run pytest tests/ -q` exits 0 and prints at least `702 passed, 1 skipped`;
`TZ=Asia/Saigon uv run pytest tests/ -q` exits 0 with the same count;
`uv run lint-imports` exits 0 and prints `Contracts: 9 kept, 0 broken.`;
`uv run ruff check src tests scripts` exits 0 and prints `All checks passed!`;
`cd web && npm run build` exits 0.

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
