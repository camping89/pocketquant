# Phase 3 completion — Calendar-Threaded Pipeline on the 24/7 Calendar

Plan: `plans/260921-1436-asset-class-index-futures/`
Phase file: `phase-03-calendar-threaded-pipeline.md`
Date: 2026-09-22
Status: complete. All 11 tasks done; shipped to production and verified on the VPS.

## Outcome

The five day-one P0s — alignment, cascade, integrity, freshness and annualization —
now take the trading calendar as a parameter instead of assuming a market that never
closes. Every one of them runs on the 24/7 calendar only, and crypto comes out
unchanged: the golden snapshot captured before the first production edit is
byte-identical ten commits later, and the first post-deploy cron cycles report the
same counts as the pre-deploy ones.

The pipeline can now express a market that is shut. It skips fetching for it, does not
warn that it is stuck, does not count its closed hours as missing bars, and annualizes
its returns on sessions rather than on 365 days.

## Verification

Task 11 phase gate, chained, exit 0:

| Command | Result |
|---------|--------|
| `uv run pytest tests/ -q` | `751 passed, 1 skipped` (baseline 709) |
| `uv run pytest ...test_cascade_calendar_golden.py -q` | `3 passed`, no regeneration |
| `uv run ruff check src tests scripts` | `All checks passed!` |
| `uv run lint-imports` | `Contracts: 9 kept, 0 broken` |
| `uv run pyright src` | `0 errors, 0 warnings` |
| `just test-tz` | `751 passed` under all three zones, exit 0 |
| `npx tsc --noEmit` (SPA) | exit 0 |

The golden files have not changed since the commit that created them:
`git diff bd0c963 HEAD -- tests/app_test/market_data/golden/` is empty, and
`git log -- tests/app_test/market_data/golden/` lists exactly one commit. That is
stronger than the comparison test alone, which could in principle have been satisfied
by regenerating.

Stated precisely, because it is easy to overclaim: the snapshot pins bucket boundaries,
alignment decisions and periods-per-year — the *inputs* to a bar's value, not the
aggregated OHLCV itself. That is the right guard for this refactor, because the bucket
walk is the only thing that could change which 1m bars feed a bucket and
`aggregate_ohlcv` was not touched. The production check on aggregated values is the
hourly `sync_verify_cascade`, below.

## What the phase's own Verify steps did not catch

Every task's prescribed Verify passed. That proved less than it appears to, because
with only the 24/7 calendar registered most of the new behaviour was unobservable:
`is_bar_aligned` could ignore its calendar argument entirely and all 712 tests still
passed, since `Continuous24x7Calendar.bar_start` delegates to the very helper it
replaced.

Fourteen behaviours were in that state — the alignment threading, the cascade's
non-advancing-step guard, its calendar-derived expected-bar count, `calendar_id` and
`session_date` on both the cascade and sync write paths, the integrity grid, the weekly
short-circuit and the repair that honours it, session-aware staleness, the closed-market
no-progress silence, the `is_market_open` field, the closed-market sync skip, its grace
window, `cascade_tfs`, and the report service's annualization source. Each now has a
test that was confirmed to fail when the behaviour is removed, by removing it.

The discriminator throughout is the real `CmeGlobexCalendarAdapter` rather than a stub:
its sessions open at 22:00 UTC the evening before, so a daily bar stamped at UTC
midnight is aligned on one calendar and misaligned on the other, and the hour
21:00–22:00 UTC holds sixty trading minutes on one and zero on the other.

One guard needed more than an assertion. Removing `compute_boundaries`' non-advancing
fallback makes the loop spin forever, so the obvious test hangs CI rather than failing
it. It runs the call on a daemon thread with a five-second deadline, which turns the
mutation into a red test in 13 seconds and lets the rest of the suite finish.

## Deviations from the plan, and why

Three defects in the plan were found by executing it, recorded in full in `plan.md`'s
Session 4 log as Corrections 11, 12 and 13.

1. **Two Verify greps cannot pass on correct code.** Task 2's and Task 4's call-site
   greps count `def` lines as call sites and cannot see an argument on a continuation
   line, and ruff's 100-character limit forces two of those signatures to wrap.
   Satisfying them literally would mean violating the project's own line length. Both
   now use `uv run pyright src`, which enforces the stated criterion across all of
   `src/` and which Task 4 already used for exactly this purpose.
2. **The CME annualization band assumed the wrong exchange.** Task 10 asserts 245–255
   sessions a year, citing "23h x 252 sessions". The adapter returns 259, and 259 is
   correct: CME Globex equity futures close early on US holidays rather than skipping
   the session, so 2025 has 261 weekdays less only two full closures. 245–255 is the
   NYSE cash-session figure. Both CME assertions are now exact equalities, because the
   adapter measures over a fixed reference year specifically so the value is stable,
   and the original bands accepted every wrong answer worth catching.
3. **Task 9 routed a session count into CAGR.** The step prescribed feeding
   `calendar.periods_per_year(DAY_1)` into `cagr`, but `cagr` divides wall-clock
   calendar days, so 259 stretches one real year into 1.41 and reports a doubling as
   63.5% growth. CAGR stays on 365 days for every instrument; Sharpe and Sortino, which
   count return observations rather than elapsed time, keep the calendar's figure.
   Crypto cannot detect this — 365/365 is the identity — so the golden files and this
   phase's own byte-identical gate would both have passed over a wrong futures CAGR.

Correction 13 was found by advisory review of the Correction 12 failure, not by any
test. It is the one defect in this phase that no gate would ever have caught.

Two smaller deviations, both inside the spirit of their task:

- Task 2 left a two-line temporary calendar at the integrity call site so that every
  commit stayed green; Task 4 removed it, and the phase gate greps for it.
- Task 5's `is_market_open` was added to the single-symbol status endpoint as well as
  the list endpoint. The plan says "both route response dicts"; the single-symbol one
  does not currently expose `is_stuck`, and that was left alone.

## Commits

```
bd0c963 test(market-data): snapshot crypto bucket, alignment and annualization arithmetic
b3d6e87 refactor(market-data): let the symbol's calendar decide bar alignment
9aea804 refactor(market-data): derive cascade buckets and bucket sizes from the calendar
8b7b2d9 fix(market-data): take the integrity grid from the calendar instead of arithmetic
8656dd0 feat(market-data): report a closed market as closed rather than stuck
5296535 feat(market-data): stamp synced bars with their calendar and session day
787f81b feat(market-data): skip the REST sync for symbols whose market is shut
e3ddc10 feat(market-data): fetch daily bars natively for session-based markets
ebc2a12 feat(backtest): annualize Sharpe on the symbol's calendar, keep CAGR on the clock
9a291fc docs(plans): record phase 3 corrections to the verify greps and annualization
```

All ten are on `origin/develop`.

## Deployment

Actions run `35676862535` green on every job, including all three timezone legs.
Both running images were tagged `pre-phase3-20260922` on the VPS before the push, and
both survived the deploy's `docker image prune`. The pre-Phase-1 `pre-utc-20260922`
tags are still there as well.

Pre-deploy baseline, ten consecutive `sync_1m` runs: `details=3, fetched=300,
inserted=3` every time, duration 4.4–6.1s.

Verified on the VPS after deploy:

| Check | Result |
|-------|--------|
| Startup assertion | `runtime.timezone tz=UTC tzlocal=UTC tzname=('UTC','UTC')` |
| Containers | `pocketquant-app` and `-web` healthy on a fresh image; Mongo/Redis untouched |
| Health endpoint | `HTTP 200` |
| `sync_1m`, five post-deploy cycles | `details=3, fetched=300, inserted=3, skipped=0` — identical to baseline |
| `sync_1m` failures since deploy | 0 |
| `integrity/check` BTC 1m, 1 day | `total 1440, misaligned 0, missing 0, gaps []` |
| `integrity/check` BTC 1d, 7 days | `total 8, misaligned 0, missing 0` — the `session_open` branch |
| `integrity/check` ETH 1h, 7 days | `total 168` (7 x 24 exactly), `missing 0` — the `trading_minutes` branch |
| `integrity/check` BTC 1w, 30 days | `skipped_reason: weekly_convention`, `missing 0` |
| `sync_verify_cascade` 02:00 UTC | `completed, details=0, 374ms` — same as the four prior hourly runs; zero divergence alerts |
| `GET /sync-status` | carries `is_market_open: true` on every row |
| Errors since start | zero `Traceback`, `TypeError`, `AttributeError`, `offset-naive` |
| `misaligned_bars_dropped` / `no_progress` / `boundary_step_fallback` / `stuck_threshold_crossed` / `integrity.issues_found` | zero of each |

The integrity result is the one that mattered most. The check now derives its expected
grid from `calendar.trading_minutes` instead of `start + N*interval`, and for a crypto
symbol it returns exactly what the arithmetic grid returned: 1440 of 1440, no gaps.
Both HTTP routes also exercise the `FromDishka[TradingCalendarFactory]` parameter added
in Task 4, which would have been a runtime `TypeError` on the first request if the
wiring were wrong.

The one cycle that differs is the first after the restart: `01:48` inserted 6 rather
than 3, catching up the minute the container was down, and `01:49` onward is back to 3.
Thirteen post-deploy cycles completed, none failed.

`sync_verify_cascade` is the check that matters most for G5, because it is the only
production comparison of cascaded bar *values* against the provider rather than of grid
shape. Its first post-deploy run reported `details=0` — no divergence — matching every
prior hourly run.

**Not production-verified, and deliberately so.** The closed-market behaviours — the
sync skip and its grace window, the silent `emit_no_progress`, the `CLOSED` badge — got
no production exercise at all, because the only calendar in production is the 24/7 one
and it is never shut. Their evidence is the mutation tests against the real CME adapter,
which is the strongest available until Phase 5 seeds a futures symbol. Likewise the
three-zone suite proves the tests are zone-invariant, not that production is; production
is pinned to `TZ=UTC` by the Phase 1 startup guard.

### One warning that is expected, explained because the count looks alarming

`cascade.partial_aggregate` fired 57 times in the first four minutes. Every one is an
in-progress bucket: at `01:51` the hourly bucket opened at `01:00` holds 51 of its 60
minutes, the 4h bucket 111 of 240, the daily 111 of 1440. The `expected` values are
60, 240 and 1440 — exactly the `_TF_EXPECTED_BARS` constants this phase deleted, which
is the evidence that `calendar.trading_minutes` reproduces them for the 24/7 calendar.
The lines now also carry `calendar_id=CRYPTO_24_7`.

This is pre-existing behaviour, not a Phase 3 regression, but it is worth flagging: a
WARNING once per symbol per cascade timeframe per minute scales with the symbol count,
and `CLAUDE.md` puts per-cascade events at DEBUG for exactly that reason. Three symbols
already produce roughly 14 warnings a minute. See the follow-ups.

## Follow-ups, not done and not in Phase 3 scope

- **`calendar_id` and `session_date` are effectively write-once on cascaded bars.**
  `BarRepository.upsert_bar`'s update branch sets only OHLCV, `tick_count`,
  `updated_at` and `source`, and its third branch returns early when OHLCV is
  unchanged. A bucket that already existed before the deploy therefore never gets
  stamped however many times it is re-aggregated, and a symbol whose calendar is later
  reclassified would keep a stale `calendar_id`. Measured 15 minutes after deploy: 18
  1m bars (the sync path, which uses `insert_many`) and 3 5m bars (newly created
  buckets) carry the fields; no 15m, 1h, 4h or 1d bar does. Nothing reads these fields
  before Phase 5, and futures buckets will all be new inserts, so this is not urgent —
  but closing it properly means a backfill, which is a migration and needs its own
  backup step, so it belongs in Phase 7 or after the plan. Confirmed safe to defer:
  nothing in `src/` filters or sorts on either field — every reference is a write, a log
  payload or `Bar.from_mongo` hydration — the sparse `session_date` index has no reader,
  and Phases 4 through 6 never read either field off a stored bar. This is the Phase 1
  lesson again: a fix to a write path is not a fix to the data that path already
  wrote.
- **`cascade.partial_aggregate` is a WARNING on a per-minute hot path.** Worth
  demoting to DEBUG for in-progress buckets, or suppressing when the bucket has not
  closed yet. Not done here because Phase 3 did not ask for it and the behaviour
  predates the phase, but it should land before Phase 5: with a session calendar every
  4h bucket spanning the daily halt is legitimately "partial", so futures will multiply
  today's ~14 warnings a minute rather than merely add to them.
- **Phase 4 carries a nested-loop risk that its own gate cannot show.**
  `fetch_with_retry` already retries on an empty or all-misaligned response; Phase 4's
  routing adapter adds a second loop that treats an empty list as "try the next
  provider". With Binance as the only registered provider the two are
  indistinguishable, so Phase 4's crypto gate will pass while proving nothing. It bites
  in Phase 5, where a legitimately empty result during a CME halt would drive
  retries x providers scrape calls a minute. Phase 4 should pin, with a test, that this
  phase's closed-market skip sits upstream of both loops.
- **Job-history flake, third sighting.** `test_get_latest_by_job_ids_awaits_aggregate`
  failed once more in a full-suite run and passed on re-run. Same same-millisecond
  `$sort`/`$first` tie with no secondary key at `job_history_repository.py:193-197`.
  It is now recurring rather than isolated.
- Carried from Phase 1 and untouched here: the serialization sweep of roughly twenty
  remaining JSON `.isoformat()` emitters proposed for Phase 7, and `docs/deployment.md`
  still documenting an emergency rollback that could not have worked.
