# Asset Classes and the Trading Calendar: Why UTC Is an Invariant and Schedules Live in Code

**Date**: 2026-09-21 to 2026-09-23
**Severity**: High
**Component**: Core (scheduling, persistence, calendars, market-data routing, TradingView client); engine (sync, integrity)
**Status**: Resolved (week-long observation metrics still open; see the plan's `completion-report.md`)

---

## What Happened

Plan `260921-1436-asset-class-index-futures` made CME index futures (`ES1!`, `NQ1!`, `YM1!`) a second asset class beside crypto spot. Every hardcoded assumption in the pipeline matched Binance by coincidence: UTC-midnight days, Monday-midnight weeks, a dense 1m grid, continuous trading. The work split into a UTC invariant, a trading-calendar port threaded through the pipeline, provider routing, a TradingView history and quote source, and this closing phase of UI, docs and metrics.

This journal records the reasoning behind five decisions. The code states *what* each one does; the *why* lives here, so source comments never need to cite plan ids or phase numbers.

---

## The Brutal Truth

Production had been correct only because the container set no `TZ`. Nothing in the code enforced UTC, and two live bugs had been waiting for a host with a different zone. Futures would have been that host in effect: a session calendar anchored at 17:00 Chicago surfaces every place where "now" or "midnight" was computed in the wrong zone.

---

## Technical Details

### 1. The `CronTrigger` host-zone bug, and how it was found

`scheduler.py` sets `timezone="UTC"` on the `AsyncIOScheduler`, which looks sufficient. It is not. APScheduler applies the scheduler's zone only when `add_job` builds the trigger from a string alias. A pre-built `CronTrigger(...)` with no `timezone=` falls back to `tzlocal`, and the host zone is pickled into the Mongo jobstore with the job. On a `TZ=Asia/Ho_Chi_Minh` host, `sync_backfill` would have fired at 03:00 Saigon (20:00 UTC).

It was found while reading the scheduler during planning, not from an incident: the scheduler-level `timezone="UTC"` sat 140 lines above two trigger constructors that ignored it. The fix pins `timezone=UTC` on both constructors. The regression test only proved anything after a mutation check showed that the test as first written still passed with the fix removed. `tzlocal` memoizes the zone, and `time.tzset()` does not clear that cache. That same check exposed `Asia/Saigon` as an unresolvable `tzdata-legacy` alias, which glibc silently degrades to UTC.

Belt and braces: `assert_utc_runtime()` now refuses to start on any non-UTC process zone, and CI runs the suite under three zones.

### 2. `tz_aware` and `integrity_jobs` must ship in one commit

Making the Mongo client `tz_aware=True` changes every datetime read from naive to aware UTC. `integrity_jobs` computed `now` as a naive datetime and compared it against the stored bar datetimes.

The check builds an expected grid of bar datetimes from `now` and matches it against the stored ones. A naive datetime never compares equal to an aware one, so a revision carrying either half alone yields a grid in which no expected bar matches. It does not matter which half lands first: the client fix alone makes stored bars aware against a naive grid, and the clock fix alone makes the grid aware against naive reads. Either way every bar reads as missing, and the repair job resyncs every symbol from scratch against Binance's rate limits.

Neither half is safe alone. Both land in one commit with the naive-epoch branch in `bar_builder_domain_service.get_bar_start`. The deploy was verified with an integrity query in the first minute, which returned `total 1440, missing 0`.

### 3. Calendar rules live in code; `calendar_id` lives on the symbol

The symbol record stores a `calendar_id` **reference** (`CRYPTO_24_7`, `CME_GLOBEX_EQUITY`). The schedule **rules** stay in code behind `ITradingCalendarPort`, via `Continuous24x7Calendar` and `CmeGlobexCalendarAdapter` over `pandas_market_calendars`.

CME holidays and early closes change every year. A copy of the schedule in Mongo would have to be synchronised by hand against CME notices and would drift silently. A library release gets the new year's calendar from its maintainers and is pinned by the lockfile. The reference belongs on the record because *which* calendar a symbol follows is data about that symbol. An unknown `calendar_id` falls back to 24/7 with a one-time warning rather than crashing the sync path.

### 4. Realtime routing has no fallback chain

History routing tries each provider in order: `RoutingDataProviderAdapter` falls through on an exception or an empty answer. Realtime routing deliberately does not. `RoutingRealtimeQuoteAdapter` subscribes a symbol through its primary provider only.

The reason is double counting. Two live feeds for one symbol both reach `BarBuilderDomainService`, and every tick is counted twice into volume and into the in-progress bar. That failure is silent and corrupts data. A missing feed is loud: the quote goes stale and freshness monitoring reports it. A missing feed is the better failure.

### 5. The TradingView mapper recovers the epoch through `.timestamp()`

`tvdatafeed` builds its DataFrame index with `datetime.fromtimestamp(...)` and no timezone. The index is therefore **naive host-local time**, and the raw epoch is discarded. Treating that index as UTC would shift every bar by the host offset, and every bar would then look correct on the UTC VPS and wrong on any developer machine or CI zone.

`TvDatafeedClient._to_raw_bar` calls `.timestamp()` on the naive value. Python interprets a naive datetime in the host zone, the same zone the library used to build it, so the round trip recovers the true instant on any host. That is what lets the three-zone CI matrix pass. An aware index entry, if a future library version produces one, is converted instead of reinterpreted.

---

## Lessons

- **A zone setting on a container is not an invariant.** Assert it at startup.
- **A test that has never failed has not been tested.** Mutating the fix away caught both the memoized-`tzlocal` false pass and the unresolvable zone alias.
- **Prefer the loud failure.** No realtime fallback, a 24/7 default with a warning, and a startup refusal on a non-UTC host all trade a silent wrong answer for a visible gap.
