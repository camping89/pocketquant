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
- `src/pocketquant/app/routes/integrity.py` — `integrity_check` (calls
  `check_integrity` at line 33) and `integrity_repair` (calls `repair_integrity` at
  line 45). These HTTP routes are callers too; changing the function signatures
  without updating them is a runtime `TypeError` on the first request.

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
7. Update the two HTTP routes in `src/pocketquant/app/routes/integrity.py` the same
   way. Add `calendar_factory: FromDishka[TradingCalendarFactory]` to the
   `integrity_check` and `integrity_repair` signatures (use `FromDishka`, never
   `Depends()`, per the repo convention), resolve the calendar from the validated
   symbol, and forward it to `check_integrity` / `repair_integrity`.

**Success criteria.** For a crypto symbol the missing-bar counts are unchanged; for a
`WEEK_1` interval the check short-circuits; and no caller of either function is left
on the old signature.

**Verify.** All three exit 0:
- `uv run pytest tests/app_test/integration/test_sync_backfill_gap_fill.py -q`
- `uv run pyright src` (catches any caller still passing the old argument list)
- `test "$(grep -rn 'check_integrity(\|repair_integrity(' --include=*.py src/ | grep -vc 'calendar')" = "0"` — every call site now passes a calendar.

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
3. Run ruff, `pyright src` and the import contracts.
4. Deploy to the VPS and watch one full `sync_1m` cycle plus the hourly
   `sync_verify_cascade`. Compare the `synced_count` and `cascade` counts in
   `job_history` with the previous day's run for the same hour. Record the numbers in
   the phase completion note.

**Success criteria.** The golden files match unmodified, the suite is green under all
three zones, and one prod cron cycle produces the same counts as before.

**Verify.** `uv run pytest tests/app_test/market_data/test_cascade_calendar_golden.py -q && uv run pytest tests/ -q && TZ=America/Chicago uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run lint-imports` exits 0.

## Todo

- [ ] Task 1 — Capture golden files BEFORE any refactor
- [ ] Task 2 — Thread the calendar through bar alignment
- [ ] Task 3 — Thread the calendar through the cascade aggregator
- [ ] Task 4 — Thread the calendar through the integrity check
- [ ] Task 5 — Make freshness and anomaly gating session-aware
- [ ] Task 6 — Populate `session_date` and `calendar_id` on the sync write path
- [ ] Task 7 — Gate the sync job on the calendar
- [ ] Task 8 — Fetch 1d and 1w natively for calendar-based asset classes
- [ ] Task 9 — Move annualization onto the calendar
- [ ] Task 10 — Calendar annualization test
- [ ] Task 11 — Phase gate: crypto must be byte-identical

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

