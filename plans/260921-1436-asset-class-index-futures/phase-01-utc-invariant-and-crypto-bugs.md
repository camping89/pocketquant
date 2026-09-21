---
phase: 1
title: "UTC Invariant and Live Crypto Bug Fixes"
status: completed
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
6. Install the IANA timezone database in the runtime image. `ENV TZ=UTC` alone does
   NOT provide zone data, and Phase 2 needs `ZoneInfo("America/Chicago")` to resolve.
   Verified facts: the pip `tzdata` package is locked with marker
   `sys_platform == 'emscripten' or sys_platform == 'win32'`, so it is NOT installed
   on Linux, and the `runtime` stage of `deploy/Dockerfile` currently installs only
   `curl`. In that stage's existing `apt-get install -y --no-install-recommends`
   list, add `tzdata` next to `curl`. Do not add the pip `tzdata` package; the OS
   package is what `zoneinfo` reads.

**Success criteria.** All four files carry a UTC pin, and the runtime image installs
the OS timezone database.

**Verify.** Both of these exit 0:
- `grep -l 'TZ=UTC\|TZ: "UTC"\|TZ: UTC' deploy/Dockerfile deploy/compose.prod.yml justfile .github/workflows/cicd.yml | wc -l` prints `4`.
- `grep -A4 'apt-get install' deploy/Dockerfile | grep -q tzdata` exits 0.

After Phase 2 builds the image, `docker run --rm <image> python -c "from zoneinfo import ZoneInfo; print(ZoneInfo('America/Chicago'))"` must print a zone and exit 0, not raise `ZoneInfoNotFoundError`.

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
   `"UTC"`, `"Asia/Ho_Chi_Minh"`, `"America/Chicago"`, set `TZ`, call `time.tzset()`,
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

**Verify.** `uv run python -c "import os,time; os.environ['TZ']='Asia/Ho_Chi_Minh'; time.tzset(); from pocketquant.app.main_extensions import assert_utc_runtime; 
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
3. `test_non_utc_host_raises`: set `TZ=Asia/Ho_Chi_Minh`, `time.tzset()`, assert
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

**Success criteria.** The full suite still passes, no naive datetime is produced by
`get_bar_start`, and all four files land in ONE commit.

**Verify.** Both must hold:
- `uv run pytest tests/core_test/unit/domain/test_mongo_datetime_normalization.py tests/core_test/unit/domain/bar/services/test_bar_builder.py tests/core_test/infra/persistence/test_bar_repository.py -q` exits 0.
- After committing, `git show --stat HEAD --name-only` lists `mongodb.py`,
  `integrity_jobs.py` and `bar_builder_domain_service.py` in the SAME commit. If any
  of them is missing, the commit is wrong: `git reset --soft HEAD~1`, restage all of
  them together, and commit again. Do not proceed to Task 7 until this passes —
  splitting these files across commits leaves a revision in which the integrity check
  reports every bar missing and triggers a full resync of every symbol.

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

**Goal.** `uv run ruff check src tests scripts` passes with the `DTZ` rule family enabled.

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

**Verify.** `uv run ruff check src tests scripts ` exits 0 and prints `All checks passed!`.

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
       tz: ["UTC", "Asia/Ho_Chi_Minh", "America/Chicago"]
   ```
   and change the job-level `env:` added in Task 1 to `TZ: ${{ matrix.tz }}`.
2. Leave `build-app`'s `needs: [tests]` as is; GitHub waits for all matrix legs.
3. Add to `justfile`:
   ```
   # Run the unit suite under three host timezones — catches host-zone leakage.
   test-tz:
       TZ=UTC {{python}} -m pytest -q
       TZ=Asia/Ho_Chi_Minh {{python}} -m pytest -q
       TZ=America/Chicago {{python}} -m pytest -q
   ```

**Success criteria.** The suite passes under all three zones locally.

**Verify.** `TZ=Asia/Ho_Chi_Minh uv run pytest tests/ -q` exits 0.

---

### Task 13 — Phase gate: prove the invariant end to end

**Goal.** Phase 1 is provably complete before Phase 2 starts.

**Target files and symbols.** None (verification only).

**Steps.**
1. Run the full suite under the three zones.
2. Run ruff, `pyright src` and the import contracts.
3. Record the outputs in the phase completion note.

**Success criteria.** All four commands exit 0.

**Verify.** `uv run pytest tests/ -q && uv run ruff check src tests scripts && uv run lint-imports && TZ=Asia/Ho_Chi_Minh uv run pytest tests/ -q` exits 0.

---

### Task 14 — Ship Phase 1 to production on its own

**Goal.** The two live crypto bugs are fixed in production before Phase 2 begins, and
the UTC invariant is proven on the real VPS rather than only in CI.

**Why this phase ships alone.** Tasks 2 and 8 fix defects that are live right now and
have nothing to do with futures: the cron triggers run in the host timezone, and a
partial Binance weekly bar is persisted from Thursday to Sunday. Holding them behind
six more phases of futures work leaves them in production for roughly eleven days.
Phase 1 also touches no futures code, so it carries none of that risk.

**Target files and symbols.** None (release only).

**Steps.**
1. Confirm Task 13 passed. Do not ship on a red gate.
2. Commit the phase on `develop` in conventional-commit form, keeping the Task 6
   single-commit constraint intact — that commit stays as it is; do not squash it
   into others. Do not mention plan ids, phase numbers or AI tooling in any commit
   message; describe the behaviour, for example
   `fix(scheduling): pin cron triggers to UTC instead of the host timezone`.
3. `git push origin develop`. Per `docs/deployment.md`, that push IS the entire
   deploy: `.github/workflows/cicd.yml` runs `tests` (which gates the build), builds
   the app and web images, then SSHes to the VPS and runs `10-deploy.sh` and
   `11-verify.sh`. There is no deploy script to run by hand.
4. Watch the run to completion:
   `RUN_ID=$(gh run list --branch develop --limit 1 --json databaseId -q '.[0].databaseId')`
   then `gh run watch "$RUN_ID" --exit-status`.
5. Confirm the container came up on the new image and that the startup assertion did
   NOT reject production. Credentials for this are in the sibling config repo:
   `HOST="$(cat ../pocketquant-config/vps/default/host)"`,
   `KEY="../pocketquant-config/vps/default/id_rsa"`, then
   `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app curl -s -o /dev/null -w 'HTTP %{http_code}' http://localhost:41921/health"`.
   Never copy any credential value into this repo, a commit, a log or a report.
6. Confirm the UTC invariant on the live container:
   `ssh -i "$KEY" "$HOST" "docker exec pocketquant-app python -c \"import time; from zoneinfo import ZoneInfo; print(time.timezone, ZoneInfo('America/Chicago'))\""`.
   This is the first real proof that both the `TZ=UTC` pin and the `tzdata` install
   from Task 1 work in the deployed image, which Phase 2 depends on.
7. Confirm the scheduler picked up UTC triggers by checking one job's next run time in
   the application log or via the jobs surface, and note it in the completion report.

**Success criteria.** The Actions run is green, the app container is `(healthy)` on a
fresh image, the startup assertion did not fire, `ZoneInfo('America/Chicago')`
resolves inside the container, and `time.timezone` is `0`.

**Verify.** `gh run watch "$RUN_ID" --exit-status` exits 0, AND the health check
prints `HTTP 200`, AND the container prints `0` for `time.timezone` and a
`zoneinfo.ZoneInfo(key='America/Chicago')` repr rather than raising
`ZoneInfoNotFoundError`.

**If the startup assertion fires in production**, that is the assertion doing its job,
not a regression to work around: the deployed container is not on UTC. Follow the
Failure Protocol rather than weakening or removing the assertion.

## Todo

- [x] Task 1 — Pin `TZ=UTC` in every runtime surface
- [x] Task 2 — Pass `timezone=UTC` to both `CronTrigger` constructors
- [x] Task 3 — Regression test for cron trigger timezone
- [x] Task 4 — Startup assertion that the runtime timezone is UTC
- [x] Task 5 — Unit test for the startup assertion
- [x] Task 6 — Make the Mongo client tz-aware and fix the integrity naive site IN ONE COMMIT
- [x] Task 7 — `Bar.datetime` becomes an aware UTC field; DTO and serialization cleanup
- [x] Task 8 — Fix the Binance weekly in-progress cutoff
- [x] Task 9 — Regression test for the weekly cutoff
- [x] Task 10 — Replace `date.today()` in the backtest strategy loader
- [x] Task 11 — Enable ruff `DTZ` and clear every finding
- [x] Task 12 — CI timezone matrix
- [x] Task 13 — Phase gate: prove the invariant end to end
- [x] Task 14 — Ship Phase 1 to production on its own

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

