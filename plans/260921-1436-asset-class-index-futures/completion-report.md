---
title: Success-metric run-through
date: 2026-09-24
status: partial — 11 metrics pass, 2 fail, 5 open with a dated measurement
---

# Success-metric run-through

Measured on 2026-09-24 (Thursday), 05:50-07:10 UTC, during a CME session. Production
ran `f101f4e`, deployed by CI/CD run `35963033181`. Local commands ran at the same
commit. Prod queries ran read-only inside `pocketquant-app`, using `docker exec` with a
Python probe against the API and Mongo.

Each deploy recreates the app container and clears its logs. So any metric that counts
log events covers only the time since the latest restart. The windows are stated where
they matter.

## Summary

| # | Metric | Result |
|---|--------|--------|
| 1 | Non-UTC startup refuses; UTC starts | **Pass** |
| 2 | Cron `next_run_time` identical under three zones; `sync_backfill` at 03:00 UTC | **Pass** |
| 3 | Thu-Sun latest `1w` BTC bar opens on a Monday 00:00 UTC | **Pass** (see note) |
| 4 | Zero anomaly events for ES over a week with a weekend and an early close | **Fail**; the full week is open until 2026-11-30 |
| 5 | Futures 1d bars session-anchored across DST, with `session_date` populated | **Partial**: anchoring passes, `session_date` fails on history |
| 6 | Golden files: crypto bars, cascade output, metrics unchanged | **Pass** |
| 7 | Ruff with `DTZ`, and pytest with no added skips | **Pass** |
| 8 | DST suite: `session_open` at both 2026 transitions | **Pass** |
| 9 | G1: fresh futures bars during a session | **Pass**, within the free plan's delay |
| 10 | Weekend quiet in `job_history` | **Open**: first weekend is 2026-09-26/27, measure 2026-09-28 |
| 11 | `divergent_fraction = 0.0` for 24 runs; 4h bars session-anchored | Anchoring **passes**; 24 runs **open** (measure 2026-09-25) |
| 12 | 1m depth `min(max_bars, available)`, growing about 1,380 a day | **Pass** |
| 13 | G2: paper ES full session, USD PnL | **Open**: needs a risk-policy decision |
| 14 | G3: 1h ES backtest in dollars, Sharpe on the session calendar | **Pass** (measured in Session 9) |
| 15 | G4: a third provider reached by config only | **Pass** with one qualification |
| 16 | G5: crypto `sync_1m` and bar values unchanged; `periods_per_year(1m) = 525600` | **Pass** |
| 17 | G6: non-UTC refuses; DST suite passes | **Pass** |
| 18 | Secrets: only field declarations | **Pass**, on a corrected gate (Correction 34) |

## Measurements

### 1. UTC startup guard

```
TZ=Asia/Ho_Chi_Minh uv run python -c "from pocketquant.app.main_extensions import assert_utc_runtime; assert_utc_runtime()"
→ RuntimeError: Process timezone must be UTC, got TZ='Asia/Ho_Chi_Minh' tzname=('+07', '+07'). Set TZ=UTC.
TZ=UTC  (same command) → returns normally
```

### 2. Cron triggers under three zones

`TZ=<zone> uv run pytest tests/core_test/infra/scheduling/test_cron_trigger_timezone.py -q`
gave `3 passed` under UTC, Asia/Ho_Chi_Minh and America/Chicago. The suite includes
`test_next_run_time_identical_across_host_zones`. On prod, `GET /api/v1/system/jobs`
reports `sync_backfill next_run 2026-09-25T03:00:00+00:00`.

### 3. Weekly BTC bar

On Thursday 2026-09-24, the newest stored `1w` bar for `BTCUSDT:BINANCE` opens
`2026-09-14T00:00:00+00:00 Monday`. The week before it opens `2026-09-07 Monday`.

**Note on the wording.** The metric says "the previous Monday". The in-progress week
opened Monday 2026-09-21 and is correctly *not* stored. Storing it mid-week was the
original bug: a partial bar persisted from Thursday to Sunday. So the latest *closed*
week opens on the Monday before that, and the Monday alignment holds.

### 4. Anomaly events for `ES1!:CME_MINI`

Counted in the prod log window 06:02:58-06:06:48 UTC, right after a deploy:

| Event | All symbols | ES |
|-------|-------------|----|
| `misaligned_bars_dropped` | 0 | 0 |
| `integrity.issues_found` | 0 | 0 |
| `no_progress` | 1 (not ES) | 0 |
| `stuck_threshold_crossed` | 0 | 0 |
| `partial_aggregate` | 68 | 11 (NQ 11, YM 46, crypto 0) |

**Fail.** `cascade.partial_aggregate` still fires about 17 times a minute across the
three futures symbols. The cause is the one Session 8 observed: the feed is about 12
minutes behind, so a bucket our clock considers closed has not received its last
minutes yet. YM also skips untraded minutes. The stored buckets converge as the feed
catches up. The warning does not. Crypto logs none. This needs a delay-aware
closed-bucket rule in the cascade, or an absent-minute rule for untraded minutes. It
cannot be fixed by measuring.

The full-week measurement stays open until **2026-11-30**. That week has a weekend and
the Thanksgiving early close on 2026-11-26 (18:00 UTC, the next one
`pandas_market_calendars` lists). It also needs a log window that no deploy
interrupts, or the events counted somewhere that survives a restart.

### 5. Futures daily bars across DST

Stored `ES1!:CME_MINI` 1d bar opens, UTC:

| Transition | Before | After |
|------------|--------|-------|
| 2025-11-02, back to CST | 10-29 22:00, 10-30 22:00 | 11-02 23:00, 11-03 23:00 |
| 2026-03-08, forward to CDT | 03-04 23:00, 03-05 23:00 | 03-08 22:00, 03-09 22:00 |

Every bar opens at 17:00 Chicago on both sides. The 16:00 close, with the hour's break
before the next 17:00 open, is pinned by `test_cme_globex_calendar.py` (18 passed with
the golden tests under all three zones).

**`session_date` fails on history.** Only 1 of 5000 stored 1d ES bars has it, the
2026-09-22 22:00 bar with `session_date = 2026-09-23`. That bar was written by the
scheduled sync. The other 4999 came from the tracked-symbol backfill, which upserted
provider bars without stamping the calendar. The write path is fixed in `f101f4e`
(Correction 36). Rows already stored are not repaired. Nothing reads `session_date`
yet: it is serialized and indexed only. The repair is a follow-up: re-run a direct
1d/1w backfill per futures symbol after a `bars` dump.

### 6. Golden files

`uv run pytest tests/app_test/market_data/test_cascade_calendar_golden.py` is part of
the 18 passed above under each zone. It covers `test_cascade_boundaries_match_golden`,
`test_aligned_bars_match_golden` and `test_periods_per_year_match_golden`.

### 7. Lint and suite

| Command | Result |
|---------|--------|
| `uv run ruff check src tests scripts` (`DTZ` enabled) | `All checks passed!` |
| `uv run pytest tests/ -q` | `877 passed, 1 skipped` |

The one skip is `test_sync_backfill_gap_fill.py:130`. It already existed, and its reason
is a known real-Mongo `find_datetimes` gap. This phase added no skips.

### 8. DST suite

`tests/core_test/infra/calendars/test_cme_globex_calendar.py:27,32` asserts
`session_open(2026-03-09) == 2026-03-08T22:00:00Z` and
`session_open(2026-11-02) == 2026-11-01T23:00:00Z`. It passes under all three zones.

### 9. G1: fresh futures bars in session

At 06:04 UTC, the newest stored 1m bar was 666 s old for ES and 786 s for NQ and YM.
`sync_1m` inserts one futures bar a minute. The age is the free TradingView plan's
delayed feed, not a sync lag: the latest-quote stamps run about 12 minutes behind too
(Session 9). **Pass**, read as "bars land every cycle, as fresh as the entitlement
allows". A real-time feed needs `TRADINGVIEW_PLAN=cme_non_pro`.

### 10. Weekend quiet

`job_history` holds 59 `sync_1m` runs with a futures detail of
`status: skipped, error: closed`. The latest is `2026-09-23T21:59:02Z`, inside the
daily 21:00-22:00 UTC maintenance break. The closed-market skip therefore works on the
daily break. Futures were first tracked on Wednesday 2026-09-23, so no weekend has
passed yet. **Measure on 2026-09-28**, after the weekend of 09-26/27.

### 11. Cascade verification and 4h anchoring

The latest ES 4h bars open at 02:00, 22:00, 18:00, 14:00, 10:00, 06:00 and 02:00 UTC.
That is session-anchored at the 22:00 UTC (17:00 CDT) open, not at the UTC epoch
grid. **Pass.**

`sync_verify_cascade` writes its result only to the log. `job_history` records 31 runs
since 2026-09-23, but their results were cleared by today's three deploys. The
07:00 UTC run after the final deploy is recorded in the addendum below. The 24
consecutive runs need a deploy-free day: **measure on 2026-09-25 after 07:00 UTC**, or
earlier from a run log that survives restarts.

### 12. 1m backfill depth and growth

Seeded on 2026-09-23 at 4998-4999 bars per symbol, which is
`min(tradingview max_bars = 5000, available)`. On 2026-09-24 the counts are ES 6132,
NQ 6126 and YM 6100. Bars in the last 24 hours: ES 1369, NQ 1369, YM 1345. A full
Globex day is 23 hours, or 1380 minutes. YM's shortfall is its untraded minutes.
**Pass.**

### 13. G2: paper ES full session

**Open.** Session 9 found that the prescribed exposure cap applies to contract
notional. One ES contract at about 7800 is about 390,000 USD, so the default
`paper_initial_balance = 10_000` sizes every signal to zero contracts. The PnL
arithmetic is pinned end to end by tests. A live full-session round trip needs a
risk-policy decision first: cap margin rather than notional, or fund futures paper
accounts with more. That decision belongs to the user, not to this run-through.

### 14. G3: ES backtest

Measured in Session 9. An `engulfing` 1h run
`01a0ce20-2ce0-744b-b4a6-eec0641b861d` closed 132 whole-contract trades, each equal to
`(exit - entry) x 50 x contracts` to the cent. Its Sharpe of 0.527017 matches a
recomputation at 5910 periods a year to 12 digits; 8760 would give 0.641627. The code
has not changed since.

### 15. G4: a third provider

`test_a_third_provider_serves_only_the_symbol_overridden_to_it` registers a third mock
provider beside `tradingview` and `binance`. It names that provider in one
`SYMBOL_PROVIDER_OVERRIDES` entry. Only the overridden symbol reaches it, and a
same-class symbol stays on its mapped provider. The test fails when the resolver
ignores overrides. `git diff 3eb2fee -- src/pocketquant/engine` shows only the
calendar-stamp fix from metric 5, which is unrelated to routing.

**Qualification.** Registering a real adapter takes one entry in the `providers` dict
in `app/di/infrastructure.py`, the composition root. G4 says "zero edits in `app/`".
Taken literally, one file there changes. No route, service or engine module does.

### 16. G5: crypto unchanged

The last nine completed prod `sync_1m` runs each inserted exactly one bar for each of
BTC, ETH and SOL. Eleven stored BTC 1m bars matched Binance's
`/api/v3/klines?symbol=BTCUSDT&interval=1m` on OHLCV exactly: `compared 11 mismatched 0`.
`periods_per_year(1m) == 525600` is pinned in `test_interval.py:38` and in the golden
`periods_per_year.json`.

### 17. G6

Metrics 1 and 8.

### 18. Secrets

The prescribed gate prints 20. None of the 20 matches is a credential (Correction 34).
The replacement measurement is two checks, both mutation-tested:

```
git grep -nE "tradingview_(username|password|auth_token)\s*:" -- src | grep -vcE "= None$"
→ 0   (three declarations, config.py:93, 94, 98, all "= None"; a planted SecretStr("x") default prints 1)

git grep -nIiE "tradingview_(username|password|auth_token)\s*[:=]\s*[\"'A-Za-z0-9]" -- ':!tests/' ':!plans/' \
  | grep -vE "=\s*None\b|(SecretStr|str) \| None" | wc -l
→ 0   (a planted TRADINGVIEW_AUTH_TOKEN=... line in docs/deployment.md prints 1)
```

The one test literal, `"supplied-token"` in `test_tvdatafeed_client.py:283`, was
reviewed. It is the assertion target for the token-injection path and is not a
credential. `../pocketquant-config` holds no `TRADINGVIEW_*` key: production scrapes
anonymously, so no value exists that could leak.

## Addendum: the 07:00 UTC `sync_verify_cascade` run

The first run after the final deploy started at `2026-09-24T07:00:00Z`:

| Symbol | Compared | Divergent | Divergent bucket |
|--------|----------|-----------|------------------|
| `ES1!:CME_MINI` | 11 | **0** | — |
| `NQ1!:CME_MINI` | 11 | 1 | 06:45 (volume) |
| `YM1!:CBOT_MINI` | 11 | 1 | 06:45 (close, volume) |
| `BTCUSDT:BINANCE` | 12 | 1 | 06:55 (close, volume) |
| `ETHUSDT:BINANCE` | 12 | 1 | 06:55 (close) |
| `SOLUSDT:BINANCE` | 12 | 1 | 06:55 (close, volume) |

ES reports `divergent_fraction = 0.0`, which is what metric 11 asks for. That is one
run of the 24 required.

Every other symbol has exactly one divergence, always in its newest compared bucket:
06:55 for crypto, and 06:45 for the delayed futures feed. The job fires at :00:00, and
`sync_1m` runs at :00:02, so the bucket's last minute may not be stored yet when the
comparison runs. That is consistent with every divergence here, but not proven.
Crypto shows it too, so this plan did not introduce it. If the 2026-09-25 measurement
confirms the pattern, the fix is to exclude the newest bucket from the comparison, or
to offset the job past `sync_1m`.
