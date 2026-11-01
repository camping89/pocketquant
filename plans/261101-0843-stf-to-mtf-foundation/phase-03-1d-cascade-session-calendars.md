---
phase: 3
title: "1d cascade for session calendars"
status: completed
priority: P1
effort: 0.5d + D-1 deploy
dependencies: [2]
---

# Phase 03: 1d cascade for session calendars

## Goal

Every calendar, Exness session calendars included, gets its 1d bar from the 1m cascade, and this ships to prod as deploy D-1 so the one-week comparison clock starts.

## Context

- C5 and advice item 6 (a)-(c) (`plans/reports/advise-261101-0847-stf-to-mtf-migration.md:35-40`): cascade 1d for session calendars, 1w stays REST, no hourly job. REST 1d stays in `SYNC_INTERVALS` as the backfill for history older than the stored 1m bars.
- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`: `CASCADE_TFS` `:18-24` already holds `DAY_1`; `_INTRADAY_CASCADE_TFS` `:26-31`; comment `:34-37`; `cascade_tfs(calendar)` `:38-41`; `CALENDAR_CRYPTO_24_7` import `:10`; `cascade_for_symbol` loops `cascade_tfs(calendar)` at `:132`, bounds the 1m read with `limit=expected_count + 5` from `calendar.trading_minutes` (`:141-149`) and sets `session_date` for `DAY_1` (`:173`).
- `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`: `CALENDAR_CRYPTO_24_7` import `:10`; `_CASCADE_DEFAULT_TFS` `:22-29` already holds `DAY_1`; the DAY_1 direct override with its comment `:80-102`.
- `src/pocketquant/engine/market_data/app_services/sync_jobs.py:48-56`: the comment above `SYNC_INTERVALS` (`:57`) that says 1d is REST-only for calendar markets.
- Calendars: `EXNESS_CALENDARS` unpacks to the FX, XAUUSD and EXNESS_CRYPTO calendars (`tests/app_test/market_data/test_cascade_aggregator.py:26`). The XAUUSD daily bucket starts at 00:00Z and `session_date` is the UTC date. Measured by the planner on this HEAD: `len(XAUUSD.trading_minutes(day, day + 1d))` is `1378` for Monday 2026-06-08 and `119` for Sunday 2026-06-07, so the cascade's `find` limit is `1383` and `124`. `BTCUSD:EXNESS` uses `EXNESS_CRYPTO`, not `CRYPTO_24_7`, so it gains the 1d cascade too.
- Tests: `tests/app_test/market_data/test_cascade_aggregator.py` imports `cascade_tfs` (`:20`) and holds `TestCascadeTimeframesDependOnTheCalendar` (`:511-544`); `TestCascadedBarsCarryTheirCalendar._upserted` (`:472-497`) shows how to force one boundary by patching `compute_boundaries`. `tests/engine_test/market_data/test_backfill_daily_mode.py`: header `:1-3`, override tests `:73`, `:97`, `:114`, kept test `:84`, import `CALENDAR_EXNESS_FX` `:16`. The golden test `tests/app_test/market_data/test_cascade_calendar_golden.py` uses only `CASCADE_TFS` and the 24/7 calendar, so it does not change.
- Writer order on prod: `upsert_bar` writes only when OHLCV differ and the last writer sets `source` (`core/infra/persistence/repositories/bar_repository.py:42-98`), so after D-1 the stored 1d bar of a day is the cascade's. Exness REST never stores today's partial bar (`core/infra/exness/exness_adapter.py:39-43,60`), so today's 1d bar after the deploy can only come from the cascade.
- Phase 17 reads `d1_deployed_at=` from this phase's report to time the one-week comparison.

## Entry gate

Run from `D:/w/_me/algotrading/pocketquant`:

1. `git fetch -q origin && echo "dirty=$(git status --porcelain -- src web deploy tests scripts docs .github | wc -l | tr -d ' ') synced=$(test "$(git rev-parse HEAD)" = "$(git rev-parse origin/develop)" && echo yes || echo no)"` prints `dirty=0 synced=yes`. On a resume, `dirty` may count only files from this phase's Files list, and `synced=no` passes only when `git rev-list --count HEAD..origin/develop` prints `0`.
2. `tail -1 plans/261101-0843-stf-to-mtf-foundation/reports/phase-02-spike-b-money-path-and-ui.md` prints `Result: PASS`.
3. `grep -c -E "^\| S(2|3|5|6|10) [^|]*\| (go|owner-go) \|" plans/261101-0843-stf-to-mtf-foundation/reports/spike-go-no-go.md` prints `5`.
4. `git rev-list --count origin/develop..origin/master` prints `0` (master is an ancestor of develop).
5. `docker ps > /dev/null 2>&1 && echo docker-ok` prints `docker-ok`.

On a miss, edit nothing and end with exactly:
```
Status: BLOCKED
NOT_YET: <gate line and its output>
Resume: /eve:cook-plan D:/w/_me/algotrading/pocketquant/plans/261101-0843-stf-to-mtf-foundation --from 03 after <UTC time>
```

## Files

- Modify: `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py`, `src/pocketquant/engine/market_data/tracked_symbols_backfill.py`, `src/pocketquant/engine/market_data/app_services/sync_jobs.py` (comment only).
- Modify tests: `tests/app_test/market_data/test_cascade_aggregator.py`, `tests/engine_test/market_data/test_backfill_daily_mode.py`.
- Create (scratch, ignored): `.cache/f.py`, `.cache/ssh/vps_key`; report `plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-1d-cascade-session-calendars.md`.

## Tasks

### Task 03.1 — Tests for the session-calendar daily cascade

**Goal:** tests state that a session calendar cascades its daily bar at UTC midnight and that every calendar cascades the same timeframes.

**Target files and symbols:** `tests/app_test/market_data/test_cascade_aggregator.py` (`TestCascadeTimeframesDependOnTheCalendar`, the `cascade_tfs` import); `tests/engine_test/market_data/test_backfill_daily_mode.py`.

**Steps:**
1. In `test_cascade_aggregator.py`, delete `cascade_tfs` from the import (`:20`) and replace the class `:511-544` with `TestEveryCalendarCascadesTheDailyBar`. A helper patches `compute_boundaries` (as `_upserted` does) to return `[day]` for `Interval.DAY_1` and `[]` otherwise, feeds one 1m bar at `day`, and returns the `find` and `upsert_bar` mocks. Tests:
   - `test_a_session_calendar_cascades_its_daily_bar_at_utc_midnight`: XAUUSD, `day = 2026-06-08T00:00Z` (Monday); one upserted bar with `interval is Interval.DAY_1`, `datetime == day`, `session_date == date(2026, 6, 8)`, `calendar_id == XAUUSD.calendar_id`; `find.await_args.kwargs["limit"] == 1383`.
   - `test_a_short_session_day_bounds_the_daily_read`: XAUUSD, Sunday `2026-06-07T00:00Z`; `limit == 124`.
   - `test_every_calendar_cascades_the_same_timeframes_in_order`: for `CALENDAR` and `XAUUSD`, patch `compute_boundaries` to return `[calendar.bar_start(datetime(2026, 6, 10, 12, tzinfo=UTC), tf)]` per `tf`; the upserted intervals equal `CASCADE_TFS` in order.
2. In `test_backfill_daily_mode.py`: delete the header `:1-3` and the tests at `:73`, `:97`, `:114`; keep `test_crypto_daily_backfill_still_cascades`; add `test_a_session_calendar_daily_auto_backfill_cascades` (calendar `CALENDAR_EXNESS_FX`, symbol `EURUSD:EXNESS`, `DAY_1`, `n=10`: `mode_used == "cascade"`, `provider.requested == [Interval.MINUTE_1]`); delete only the imports `uv run ruff check tests` reports unused.
3. Run `uv run python -m pytest tests/app_test/market_data/test_cascade_aggregator.py tests/engine_test/market_data/test_backfill_daily_mode.py -q 2>&1 | tail -1`; expected red: `4 failed` (the two daily cascade tests, the order test on XAUUSD, the session backfill test).

**Success criteria:** the new tests exist and fail only for the missing behaviour.

**Verify:** no verification needed (Task 03.2's Verify covers it).

### Task 03.2 — Cascade 1d for every calendar

**Goal:** the cascade and the backfill no longer special-case session calendars.

**Target files and symbols:** `cascade_aggregator.py` (`_INTRADAY_CASCADE_TFS`, `cascade_tfs`, `cascade_for_symbol`, the import); `tracked_symbols_backfill.py` (`TrackedSymbolBackfillService.run`, the import); `sync_jobs.py:48-56`.

**Steps:**
1. `cascade_aggregator.py`: delete `_INTRADAY_CASCADE_TFS` (`:26-31`), the comment and `cascade_tfs` (`:34-41`) and the `CALENDAR_CRYPTO_24_7` import (`:10`); `cascade_for_symbol` loops `for tf in CASCADE_TFS:`.
2. `tracked_symbols_backfill.py`: delete the DAY_1 override block with its comment (`:80-102`) and the `CALENDAR_CRYPTO_24_7` import (`:10`).
3. `sync_jobs.py`: replace the comment `:48-56` with: `# 1m comes from REST; 5m-1d are cascaded from stored 1m bars for every calendar.` / `# 1w stays REST: Binance weeks open on Monday and Exness weeks on Sunday, and no` / `# cascade convention exists. REST 1d stays listed as the backfill for history older` / `# than the stored 1m bars.`
4. Run the Task 03.1 command again; all pass.

**Success criteria:** no reference to the deleted names remains; the cascade and backfill tests and the golden test pass.

**Verify:** `echo "refs=$(git grep -n -E "cascade_tfs|_INTRADAY_CASCADE_TFS" -- src tests scripts | wc -l | tr -d ' ') tests=$(uv run python -m pytest tests/app_test/market_data/test_cascade_aggregator.py tests/engine_test/market_data/test_backfill_daily_mode.py tests/app_test/market_data/test_cascade_calendar_golden.py -q 2>&1 | tail -1)"` prints `refs=0 tests=` followed by a line containing `passed` and not `failed`.

### Task 03.3 — CLOSE

**Goal:** the change is on `develop` with green gates and CI.

**Target files and symbols:** the files above.

**Steps:**
1. GATES (plan.md Conventions): `uv run lint-imports` prints `Contracts: 6 kept, 0 broken.`; `uv run python scripts/code_metrics.py --ratchet` exits 0 (raise the ceiling only by the Conventions rule); `uv run ruff check src tests scripts` exits 0.
2. FULLSUITE (plan.md Conventions).
3. `git add -A src tests && git commit -m "feat(market-data): cascade the daily bar for session calendars"`; push with the Ops recipe; wait for CI.

**Success criteria:** CI on the pushed sha concludes `success`.

**Verify:** `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch develop --limit 1 --json headSha,status,conclusion -q '.[0] | "\(.status) \(.conclusion) \(.headSha)"'` prints `completed success <sha>` where `<sha>` equals `git rev-parse HEAD` (poll until `completed`).

### Task 03.4 — Deploy D-1 [ASK]

**Goal:** the cascade runs on prod and today's Exness 1d bars come from it.

**Target files and symbols:** `master` on origin; prod `bars`; the phase report.

**Steps:**
1. SSH key per the Ops recipe; record `free -m` on the VPS (`ssh -i .cache/ssh/vps_key "$HOST" 'free -m'`) in the report.
2. [ASK] in Vietnamese. Intent: "Deploy D-1 now: push develop to master. It ships <`git log --oneline origin/master..develop` list>; the only runtime change is the 1d cascade for Exness symbols; no strategy, schema or index change. Recommended: yes, because it is independent of the rest and starts the one-week comparison." Only an explicit yes counts.
3. On yes: `git push "https://x-access-token:$(gh auth token --user camping89)@github.com/camping89/pocketquant.git" develop:master && git fetch origin`; `sleep 15`; poll `GH_TOKEN=$(gh auth token --user camping89) gh run list --branch master --limit 1 --json headSha,status,conclusion` until `completed`; it must be `success` with `headSha` = `git rev-parse origin/master`. Record `d1_deployed_at=<UTC ISO of the run's completion>` as its own line in the report.
4. Record `free -m` again in the report.
5. Five minutes after the run completed, write `.cache/f.py` and run it with PRODPY:
```python
from datetime import UTC, datetime

from pymongo import MongoClient

from pocketquant.core.config import get_settings

s = get_settings()
db = MongoClient(str(s.mongodb_url), tz_aware=True)[s.mongodb_database]
today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
checked = bad = 0
for ts in db.tracked_symbols.find({}, {"symbol": 1}):
    sym = ts["symbol"]
    if not sym.endswith(":EXNESS"):
        continue
    m1 = db.bars.count_documents({"symbol": sym, "interval": "1m", "datetime": {"$gte": today}})
    if m1 == 0:
        print(f"{sym} m1_today=0 skipped")
        continue
    d1 = db.bars.find_one({"symbol": sym, "interval": "1d", "datetime": today}, {"source": 1, "updated_at": 1})
    source = d1.get("source") if d1 else None
    checked += 1
    bad += source != "cascade"
    print(f"{sym} m1_today={m1} d1_source={source} d1_updated_at={d1.get('updated_at') if d1 else None}")
print(f"checked={checked} bad={bad}")
```
   If it prints `checked=0` (no Exness symbol has traded since 00:00Z), end with the `NOT_YET` block (`NOT_YET: no Exness symbol traded today yet`), resuming after the next session open; the resume reruns only steps 5-6.
6. Write the report, commit it (`docs(plans): record the daily cascade deploy`) and push `develop`; `rm -f .cache/ssh/vps_key`.

**Success criteria:** the master run concluded `success`; every Exness symbol that traded today has a cascaded 1d bar for today.

**Verify:** `f=plans/261101-0843-stf-to-mtf-foundation/reports/phase-03-1d-cascade-session-calendars.md; echo "d1=$(grep -c -E "^d1_deployed_at=20[0-9-]+T" $f) smoke=$(grep -E "^checked=[1-9][0-9]* bad=0$" $f | wc -l | tr -d ' ') key=$(test -f .cache/ssh/vps_key && echo present || echo gone)"` prints `d1=1 smoke=1 key=gone` (the report holds the script's last line verbatim).

## Rollback

`git revert <cascade sha>`, CLOSE, then a `develop:master` push as an [ASK]. The cascaded 1d bars already stored equal the vendor bars (advice Prod checks) and stay; `sync_repair` refills only missing 1d bars, and REST 1d is still synced. No prod data needs deleting.

## Report

`reports/phase-03-1d-cascade-session-calendars.md`: the commit sha and CI run id; the [ASK] text and the owner's answer; the master run id and conclusion; the line `d1_deployed_at=<ISO>`; `free -m` before and after; the smoke script output verbatim ending with `checked=<n> bad=0`; any ratchet raise. Last line `Result: PASS`.

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
