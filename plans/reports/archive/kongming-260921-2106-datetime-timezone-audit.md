# Datetime / timezone audit — market-data sync pipeline

Date: 2026-09-21. Scope: datetime and timezone correctness only (sync, cascade, integrity, storage, query, scheduler, deploy, backtest date handling, frontend display). Provider sourcing for futures is out of scope (owned by the concurrent `advisor` run).

Evidence convention: **[V]** = verified by reading code at the cited `file:line` in this repo or the installed package; **[B]** = reasoned belief, not executed or observed at runtime.

## TL;DR

The pipeline is *UTC-by-convention, not UTC-by-construction*. Crypto never exposed this because every convention (UTC-midnight days, Monday-midnight weeks, dense 1-minute grid, "3x cadence = stuck") happens to be Binance's convention. Three things must change before a session-based asset class ships: (1) pin and assert the process timezone (the APScheduler cron triggers currently run in the *host* timezone, not the scheduler's declared UTC); (2) make every timestamp tz-aware end to end (Mongo client `tz_aware=True`, one naive site in `integrity_jobs.py` removed, `AwareDatetime` on the `Bar` entity); (3) introduce a per-symbol trading calendar and route alignment, cascade bucketing, integrity grids, freshness checks, and annualization through it. Persist UTC instants only; compute session boundaries with `zoneinfo` from a calendar port whose CME implementation wraps `pandas_market_calendars` `"CME Globex Equity"`.

## Findings (prioritized)

Severity legend: **P0** = wrong data or wrong behaviour today or on day one of futures; **P1** = wrong under a plausible deployment or a routine futures event; **P2** = latent footgun / inconsistency; **P3** = cosmetic.

### P0-1 — APScheduler cron jobs run in the HOST timezone, not UTC [V]

- `src/pocketquant/core/infra/scheduling/scheduler.py:79` sets `timezone="UTC"` on the scheduler, but `scheduler.py:219-233` constructs `CronTrigger(...)` directly with no `timezone=` argument and passes the pre-built trigger to `add_job` (`scheduler.py:245`). The scheduler timezone only applies when `add_job` builds the trigger from a string alias; a pre-built trigger keeps its own.
- Installed APScheduler 3.11.2 (`uv.lock`): `.venv/lib/python3.14/site-packages/apscheduler/triggers/cron/__init__.py:85-92` — with no `timezone`, `start_date`, or `end_date`, the trigger calls `get_localzone()` (tzlocal 5.3.1). The chosen zone is pickled into the Mongo jobstore (`__getstate__`, line ~260) and survives restarts.
- Affected jobs (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:690-720`): `sync_backfill hour=3`, `sync_integrity hour=4`, `sync_repair "0 */12"`, `sync_verify_cascade "0 * * * *"`. `sync_1m "*/1 * * * *" second=2` is unaffected in practice (minute grid is zone-invariant, DST offsets are whole minutes for US/CT).
- Consequences: on the VPS the container has no `TZ` and the `python:3.14-rc-slim` base is UTC by default, so it is *accidentally* correct. On a developer host in Asia/Saigon with jobs enabled (`just be` with a full `.env`; the `remote-db.env` profile disables jobs, `README.md:43`, gated at `app/main_extensions.py:146,200,218`), `sync_backfill` fires at 20:00 UTC and the doc comment "03:00 UTC" (`sync_jobs.py:686`, `docs/system-architecture.md:676`) is false. On any DST host the UTC firing time shifts twice a year. Any future host or CI runner with a non-UTC zone silently changes the schedule.
- Fix: pass `timezone=UTC` (the `datetime.UTC` object, or the string `"UTC"`) to both `CronTrigger(...)` constructors in `scheduler.py:219-233`. Add a unit test asserting `trigger.timezone == UTC` for a registered job and a startup assertion (see "UTC enforcement").

### P0-2 — Alignment filter will discard every session-based daily and weekly bar [V for code path; B for provider bar shape]

- `src/pocketquant/core/domain/bar/services/bar_builder_domain_service.py:10-32`: `get_bar_start` defines 1d as `replace(hour=0, minute=0, ...)` and 1w as Monday 00:00 in the timestamp's own tzinfo; sub-day intervals floor the epoch. `is_bar_aligned` is exact equality against that.
- `src/pocketquant/engine/market_data/sync_internals/bar_filters.py:72-82` drops any bar not on that grid; `sync_service.py:79-81` applies it on every sync; `sync_jobs.py:54-62` (`SYNC_INTERVALS`) includes `DAY_1` and `WEEK_1` in `sync_backfill`.
- A CME daily bar opens at 17:00 America/Chicago (22:00 or 23:00 UTC depending on DST); a CME weekly bar opens Sunday 17:00 CT. Neither equals 00:00 UTC / Monday 00:00 UTC, so 100% of provider 1d and 1w bars are dropped with `market_data.sync.misaligned_bars_dropped` at WARNING, every run. Because 1w is REST-only (cascade does not produce it, `cascade_aggregator.py:32-38`; rationale at `sync_jobs.py:51-53`), the 1w series for futures is permanently empty. 1d survives only as the cascade's UTC-midnight version (see P0-3), which is a different bar from every vendor chart.
- Knock-on: `emit_no_progress` (`sync_internals/anomaly_log.py:52-59`) then logs a false `stuck_threshold_crossed` ERROR.
- Fix: alignment must be calendar-aware. `is_bar_aligned(ts, interval, calendar)` where for intraday intervals the grid is anchored at the session open, and for 1d/1w the expected open instant comes from the calendar (`session_open(session_date)`), not from `replace(hour=0)`.

### P0-3 — Cascade buckets are hardwired to the UTC calendar; every futures session spans UTC midnight [V]

- `src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:98-137`: `compute_boundaries` floors `range_start.timestamp()` to `tf_seconds` — 1d buckets at 00:00 UTC, 4h at 00/04/08/12/16/20 UTC; `_TF_EXPECTED_BARS[DAY_1] = 1440` (line 46) assumes a 24h day.
- CME equity index futures trade Sun 17:00 CT to Fri 16:00 CT with a 16:00-17:00 CT halt. Every session opens ~22:00/23:00 UTC and closes ~21:00/22:00 UTC the next day, so a UTC-midnight 1d bar always merges the tail of one session with the head of the next: the "daily open" is the 00:00 UTC print, the "daily close" is the 23:59 UTC print (mid-overnight), and the volume total is a blend. Same for 4h: the four-hour grid never lands on the session open, and the bucket containing the halt has a hole.
- DST: the session open in UTC moves between 22:00 and 23:00 UTC twice a year, so a fixed-UTC grid is wrong by one hour for half the year *and* the two transition weeks contain sessions with two different offsets. Any strategy reading `1d` or `4h` bars will see different bars than TradingView/CME settlement data.
- `cascade.partial_aggregate` (lines 185-195) will WARN on every daily bucket for futures (1380 minutes in a 23h session, fewer on early-close days), turning a useful signal into noise.
- Fix: `compute_boundaries(tf, range_start, range_end, calendar)`; for 1d and 1w, boundaries are `calendar.session_open` instants; for intraday tfs, bucket starts are `session_open + k*tf` clipped to the session; expected counts come from `calendar.session_minutes`. Keep the pure-function shape; inject the calendar.

### P0-4 — Integrity check assumes a dense 1-minute grid; repair will thrash forever on futures [V]

- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py:62-63` builds `expected = {start + i*step}` over `days_back=7` and reports every absent grid point as "missing". The docstring admits it (lines 46-47).
- For ES 1m: weekend closure (Fri 16:00 CT to Sun 17:00 CT, ~2,940 minutes) plus five daily halts (~300 minutes) plus holidays are all reported as gaps. `repair_integrity` (lines 79-116) then runs `sync_one(n_bars=5000, skip_filter=True)` per symbol per interval every 12h (`sync_repair`), and `_run_integrity` (`sync_jobs.py:300-310`) logs `integrity.issues_found` for every symbol/interval daily. For 1d/1w the resync output is dropped again by P0-2. This is unbounded, permanent churn against the provider's rate limit.
- Fix: `expected = calendar.trading_minutes(start, end)` (or `calendar.sessions(...)` for 1d) instead of the arithmetic grid; skip 1w repair for calendar symbols until a weekly convention exists.

### P0-5 — "Stuck"/freshness logic assumes continuous trading [V]

- `src/pocketquant/engine/market_data/sync_status_service.py:62-69` (`_is_stuck`, 3x cadence), `sync_internals/anomaly_log.py:35-40,52-59` (`last_bar_age_seconds`, streak threshold), and `web/src/lib/datetime.ts:88-97` (`ageColorClass`) all measure `now - last_bar.datetime`.
- On a futures 1m symbol the UI turns "stuck" three minutes after Friday close and stays red until Sunday evening; `sync_1m` emits `no_progress` WARN every minute of the weekend (~2,900 per symbol) and one false `stuck_threshold_crossed` ERROR; the daily halt produces 60 WARNs per day per symbol. This directly violates the CLAUDE.md log-frequency rule.
- Fix: age must be measured against the *last expected bar close* from the calendar (`calendar.previous_close(now)`), and `emit_no_progress` must short-circuit when `calendar.is_open(now)` is false. Expose `is_market_open` in the sync-status DTO so the UI can show "closed" rather than "stuck".

### P1-1 — Annualization is 365-day crypto; futures need calendar-derived periods [V]

- `src/pocketquant/core/domain/shared/enums.py:5-13` (`_PERIODS_PER_YEAR`, 365 days x 24h) and `core/domain/trading/performance_calculator_domain_service.py:13-14` (`TRADING_DAYS_PER_YEAR = 365`), consumed at lines 108-109 and 166-167 (`sqrt(periods_per_year)`).
- ES trades ~252 sessions x ~23h. Using 365x24 overstates Sharpe/Sortino by `sqrt(365/252) ~ 1.20` on 1d bars and `sqrt(525600/347760) ~ 1.23` on 1m bars. Not a timezone bug per se, but the same root cause: the interval enum encodes a calendar it does not own.
- Fix: `periods_per_year(interval, calendar)`; default calendar = 24/7 keeps current numbers for crypto.

### P1-2 — Weekly bars from Binance can be persisted mid-week (pre-existing, crypto) [V for logic; B for observed data]

- `src/pocketquant/core/infra/binance/binance_adapter.py:80-83` computes the in-progress cutoff as `floor(now / bar_duration)`. For 1w, `bar_duration = 604800000` floors to *Thursday 00:00 UTC* (the Unix epoch was a Thursday — the repo already knows this, `bar_builder_domain_service.py:17-20`). From Thursday to Sunday the cutoff is later than the current Monday-open weekly bar, so the in-progress weekly kline passes the `b.datetime < cutoff_dt` guard (line 108) and the `endTime` cap (line 96), and gets upserted with partial OHLCV. The diff-aware upsert (`bar_repository.py:71-144`) rewrites it on each daily backfill until the week closes, so it self-heals on Monday, but for four days a week the latest 1w bar is a partial bar with `source=rest_backfill`.
- Fix: compute the 1w cutoff with `get_bar_start(now, WEEK_1)` (Monday-aligned) rather than the epoch floor; more generally, derive the "last closed bar open" from the same alignment function used by the filter, so the two can never disagree.

### P1-3 — Nothing pins the process timezone; production is UTC by accident [V]

- `deploy/Dockerfile:44-47` sets `PATH/PYTHONUNBUFFERED/PYTHONDONTWRITEBYTECODE` only; `deploy/compose.prod.yml:43-44` loads `.env`; a grep of the config repo for `^TZ=` returns nothing; `justfile` and `pyproject.toml` have no TZ. The `python:3.14-rc-slim` image defaults to UTC [B — standard Debian base behaviour; not executed here]. `tzdata` 2025.3 is in `uv.lock`, so `zoneinfo` will resolve zones even if the OS database is absent.
- Sites that read the host zone today: P0-1 (APScheduler via tzlocal); `src/pocketquant/engine/backtest/backtest_strategy_loader.py:37` `date.today()` (host-local calendar date; in Asia/Saigon it is one day ahead of UTC between 00:00 and 07:00 ICT — only affects the fallback 365-day window when no bars exist); `web/src/lib/datetime.ts:29` and `backtest-form.tsx:60-61` read the *browser* zone by design (that is the "local" display mode, fine).
- No `datetime.utcnow()`, bare `datetime.now()`, or naive `fromtimestamp()` exists in `src/` (grep verified). Every `now` is `datetime.now(UTC)` or `utc_now()`.

### P1-4 — One deliberately naive site plus a mode-dependent domain helper [V]

- `src/pocketquant/engine/market_data/app_services/integrity_jobs.py:50`: `now = datetime.now(UTC).replace(tzinfo=None)`. It is naive on purpose so `expected` (line 63) set-compares with the naive datetimes that the raw `find_datetimes` projection returns (`bar_repository.py:219-242`; Mongo client is not `tz_aware`, `core/infra/persistence/mongodb.py:44-49`; acknowledged at `bar_filters.py:54-55`).
- `bar_builder_domain_service.py:24` carries a naive epoch branch solely to serve that call. The result: the integrity job is correct only while the Mongo client stays naive. The obvious hardening (`tz_aware=True`) would make `expected - aligned_times` report every bar as missing and trigger a full resync of every symbol. This is the kind of trap that will fire during the futures work.
- Fix: switch the client to `AsyncMongoClient(..., tz_aware=True, tzinfo=UTC)` and in the same change make `integrity_jobs.py:50` aware and delete the naive epoch branch. `coerce_utc` stays as a no-op safety net.

### P2-1 — Naive datetimes accepted at the API edge and carried into queries [V]

- `src/pocketquant/app/routes/market_data_ohlcv.py:42-43` and `engine/backtest/backtest_command_service.py:31-32` accept ISO strings without an offset (`docs/system-architecture.md:573` documents "parsed as 00:00:00 UTC"). `backtest_strategy_loader.py:58-59` builds naive `datetime.combine(...)`; `backtest_dispatch.py:47-48` `fromisoformat` preserves naivety; `backtest_app_service.py:193-195` passes them to `bar_repo.stream` `$gte/$lte`.
- This works only because PyMongo encodes naive datetimes as if UTC [B — PyMongo documented behaviour]. It is correct today but unenforced. Side effects: the first `EquityPoint` (`backtest_report_app_service.py:81-86`) is naive while `mark_to_market(event.bar_start)` points are aware, so the equity series mixes `...T00:00:00` and `...T00:00:00+00:00` strings; `parseIso` (`datetime.ts:16-23`) tolerates both. Any future `sorted()`/subtraction across those points raises `TypeError`.
- Fix: a Pydantic `field_validator` (or `AwareDatetime` with a `BeforeValidator` that attaches UTC to naive input) on both DTOs, so everything past the route boundary is aware. Keep accepting naive input for backwards compatibility, but normalise it in one place.

### P2-2 — Serialization inconsistency vs. the documented standard [V]

- `docs/code-standards.md:777` mandates `to_utc_iso()` for JSON. `core/domain/bar/entities.py:104`, `engine/market_data/ohlcv_service.py:66`, `backtest_command_service.py:74-75`, `backtest_report_app_service.py:396-397` use `.isoformat()` (emits `+00:00` for aware, nothing for naive); `sync_status_service.py:72-73` hand-rolls a `Z` replacement. Frontend normalises, so this is only a contract smell — but a futures adapter that yields `America/Chicago`-aware datetimes would emit `-05:00` strings from these sites, which `parseIso` handles, while `_cache_key` (`bar_repository.py:23-30`) would key the same instant differently from the cascade writer and defeat the write-dedupe cache.
- Fix: normalise to UTC at the adapter boundary (`Bar.datetime` validator) and use `to_utc_iso()` at the serialisation sites.

### P2-3 — `get_bar_start` silently changes meaning with the input's tzinfo [V]

- `bar_builder_domain_service.py:13-22` performs `replace(hour=0)` / Monday arithmetic in whatever zone the datetime carries. Feeding it a `ZoneInfo("America/Chicago")` timestamp yields Chicago-midnight "days" while sub-day intervals stay on the UTC epoch grid. There is no assertion that the input is UTC. Once a second provider exists, the function will be called with non-UTC input.
- Fix: assert `timestamp.tzinfo is not None` and convert to UTC on entry, or (better) replace with the calendar-aware version from P0-2.

### P3-1 — Frontend timezone label uses the *current* offset for historical bars [V]

- `web/src/lib/datetime.ts:26-35` derives the suffix from `new Date().getTimezoneOffset()`. In a DST zone a July bar viewed in January is formatted at the correct historical offset (`.local()`), but labelled with today's (`GMT-6` vs actual `GMT-5`). Asia/Saigon has no DST, which is why nobody noticed. `backtest-form.tsx:60-61` local mode: a `datetime-local` value inside the spring-forward gap is shifted by the browser, and a fall-back hour is ambiguous; both are edge cases in user input, not in stored data.

### P3-2 — Non-issues, documented so they are not re-audited

- Provider timestamp ingest is correct: `core/infra/binance/binance_mappers.py:57-58,90-91` use `fromtimestamp(ms/1000, tz=UTC)`; kline open time is epoch-ms UTC, zone-free by definition. No pandas `DatetimeIndex` path exists in `src/`; pandas is a dependency (`pyproject.toml`) but unused for ingest.
- Persistence is instant-based: BSON date is int64 ms UTC; aware datetimes are converted on encode, naive are assumed UTC, reads are naive unless `tz_aware=True` [B — PyMongo docs]. `Bar.from_mongo` (`entities.py:87,94-95`) and `SyncStatus.from_mongo` (`sync_status/entities.py:53-54`) coerce; tests cover it (`tests/core_test/unit/domain/test_mongo_datetime_normalization.py:10-41`).
- Mongo precision: milliseconds. Bar `datetime` values are whole minutes, so no truncation. `created_at`/`updated_at` carry microseconds and will not round-trip exactly; nothing compares them for equality.
- Leap seconds: Binance epoch-ms, Python `datetime`, and BSON are all POSIX time (no leap seconds). Nothing to do. A CME provider that reports ISO strings is likewise POSIX.
- `DateTrigger(run_date=datetime.now(UTC))` (`scheduler.py:275`) and `job.modify(next_run_time=datetime.now(UTC))` (`:330`) are aware; the jobstore stores UTC floats (`main_extensions.py:340-346`).
- Realtime bar building (`bar_app_service.py:88-117`) uses tick timestamps that are aware UTC from `aggtrade_to_quote_dict`; correct for crypto, but inherits P0-2/P0-3 semantics for futures via `get_bar_start`.

## Answers to the seven questions

1. **Naive datetimes.** No `utcnow()`, bare `now()`, or naive `fromtimestamp()` anywhere in `src/`. Naive sites: `integrity_jobs.py:50` (deliberate), `bar_builder_domain_service.py:24` (naive branch), `backtest_strategy_loader.py:29-33,37,58-59`, API DTOs at `market_data_ohlcv.py:42-43` and `backtest_command_service.py:31-32` (naive if the client omits an offset), `backtest_dispatch.py:47-48`, raw projections from `bar_repository.find_datetimes` and the job-history repository (Mongo client not `tz_aware`).
2. **Ingest.** Binance klines are epoch-ms UTC, mapped with `tz=UTC` (`binance_mappers.py:58`); no misinterpretation path today. The off-by-timezone entry points for a futures provider are: any adapter returning naive ISO strings (would be treated as UTC by both `coerce_utc` and PyMongo), any adapter returning exchange-local-aware datetimes (P2-2/P2-3 change bucketing semantics), and any pandas `DatetimeIndex` without `tz` (would be naive). The `Bar` entity currently accepts all three.
3. **Cascade.** Fixed UTC grid by epoch floor (P0-3); 1d at 00:00 UTC; 1w is not cascaded. A 17:00 CT session day makes every daily bar a blend of two sessions; a DST week makes the UTC offset of the session open differ between the days of the same week, so no fixed grid can be right for all of them.
4. **Host timezone dependence.** Yes: APScheduler `CronTrigger` via `tzlocal` (P0-1) and `date.today()` (`backtest_strategy_loader.py:37`). Deployed in Asia/Saigon with jobs on, the daily backfill/integrity/repair crons shift by +7h; in US/Central they shift by -5/-6h and move with DST. Everything else is host-invariant.
5. **Enforcement.** See next section.
6. **Edge cases.** See "Edge-case matrix".
7. **Modelling.** See "Storage and calendar convention".

## UTC enforcement mechanism (concrete, testable)

Layer the checks so that a violation is impossible in code, loud at boot, and caught in CI.

1. **Code (make the host zone irrelevant).** `scheduler.py:219-233`: `CronTrigger(..., timezone=UTC)`. Replace `date.today()` at `backtest_strategy_loader.py:37` with `datetime.now(UTC).date()`. Mongo client: `tz_aware=True, tzinfo=UTC` (`mongodb.py:44-49`) together with the `integrity_jobs.py:50` fix. `Bar.datetime: AwareDatetime | None` (Pydantic v2) with a `BeforeValidator` that converts aware non-UTC to UTC and rejects naive from adapters; keep `coerce_utc` for `from_mongo`.
2. **Container (pin the accident).** `deploy/Dockerfile` runtime stage: `ENV TZ=UTC`. `deploy/compose.prod.yml` `app.environment: TZ=UTC` (explicit even though `env_file` exists, so a missing key in `.env` cannot unpin it). Same in `compose.local.yml`.
3. **Startup assertion (fail fast, once).** In the lifespan before the scheduler starts (`app/main_extensions.py`, next to the `enable_jobs` gates): `time.tzset()` is unnecessary; check `time.timezone == 0 and not time.daylight` and `tzlocal.get_localzone_name() in {"UTC", "Etc/UTC"}` (the second is what APScheduler actually consults). After `register_sync_jobs`, assert every `job.trigger` with a `timezone` attribute has `timezone == UTC`. Log one INFO `runtime.timezone` with `TZ`, `time.tzname`, and the tzlocal name. Raise `RuntimeError` on mismatch — there is no legitimate non-UTC deployment. For local dev, `just be` should export `TZ=UTC` so the assertion passes without touching the machine's zone.
4. **CI lint.** Enable ruff `DTZ` in `pyproject.toml` `[tool.ruff.lint] select` (currently `E,F,I,N,W,UP,TID`): DTZ001/002/003/005/006/007/011/012 catch naive constructors, `utcnow`, `now()` without tz, `fromtimestamp` without tz, `strptime` without `%z`, `date.today()`. Expect a handful of hits at the sites listed in P1-4/P2-1; fix rather than ignore.
5. **CI empirical check (the one that would have caught P0-1).** Run the unit suite twice more in CI with `TZ=Asia/Saigon` and `TZ=America/Chicago` exported (a matrix job, or a `just test-tz` recipe). Add one test that registers the cron jobs and asserts identical `next_run_time` in UTC regardless of `TZ`, and one that builds a 1d/1w/4h boundary set across 2026-03-08 and 2026-11-01 (US transitions) and asserts equality with hard-coded UTC instants.

## Edge-case matrix for a session-based asset class

| Case | Current behaviour | Where | Needed |
|---|---|---|---|
| Daily halt 16:00-17:00 CT | 60 `no_progress` WARN/day/symbol; 1m "stuck" after 3 min; integrity marks 60 missing bars/day | P0-4, P0-5 | calendar `is_open`, trading-minute grid |
| Weekend Fri 16:00 -> Sun 17:00 CT | ~2,900 WARN/symbol, false ERROR, UI red all weekend, repair resyncs 5000 bars twice | P0-4, P0-5 | same |
| Sunday reopen | first 1m bar arrives 22:00/23:00 UTC; cascade puts Sun evening into "Sunday" UTC day, vendor calls it Monday's session | P0-3 | `session_date` from calendar |
| Session spans UTC midnight (every session) | 1d/4h split across two sessions | P0-3 | session-anchored buckets |
| DST spring-forward (2026-03-08) | session open moves 23:00 -> 22:00 UTC; fixed grid off by 1h for the next ~8 months; 1d provider bars dropped regardless | P0-2, P0-3 | zoneinfo-computed opens |
| DST fall-back (2026-11-01) | reverse; the repeated local hour never lands in a CME session (transitions are Sunday 02:00 CT, session opens 17:00 CT), so no double-bar risk — but any *local-wall-time* arithmetic must use `fold` | P2-3 | never do local arithmetic on instants |
| Holidays / early closes (12:00 or 12:15 CT) | integrity gaps; 1d partial-aggregate WARN; freshness "stuck" | P0-4, P0-5 | calendar `special_closes` |
| Weekly bar convention | Monday 00:00 UTC vs CME Sunday 17:00 CT; provider 1w dropped; no cascade | P0-2, P1-2 | calendar `week_open` or provider 1w with calendar alignment |
| Annualization | 365x24 | P1-1 | calendar-derived |
| Host TZ | cron shift | P0-1, P1-3 | pin + assert |
| Naive input at API | works via PyMongo convention only | P2-1 | validator |
| Leap seconds / Mongo ms precision | none | P3-2 | none |

## Storage and calendar convention (recommendation)

**Persist UTC instants only.** Keep `bars.datetime` as the UTC instant the bar *opened* (already the case). Never store local wall time or an offset; both are derivable and both go stale across DST rules. For session-based instruments add two derived, indexed fields on daily and weekly bars: `session_date` (ISO date in the exchange calendar, e.g. the session opening Sun 2026-09-20 17:00 CT has `session_date = 2026-09-21`) and `calendar_id` (e.g. `"CME_GLOBEX_EQUITY"`, `"CRYPTO_24_7"`). `session_date` gives consumers a stable day key while `datetime` keeps varying with DST. Keep the unique index `(symbol, interval, datetime)` as is.

**Represent the calendar as a domain port**, not as data in Mongo: `ITradingCalendarPort` with `tz: ZoneInfo`, `is_open(instant)`, `session_open(session_date)`, `session_close(session_date)`, `previous_close(instant)`, `trading_minutes(start, end)`, `sessions(start, end)`, `periods_per_year(interval)`. Two implementations: `Continuous24x7Calendar` (crypto, preserves today's numbers exactly) and a CME one. The symbol (or `tracked_symbols`) carries `calendar_id`; the sync/cascade/integrity/freshness code takes the calendar as a parameter, keeping `cascade_aggregator`'s pure-function shape.

**Compute in exchange-local wall time with `zoneinfo`, convert to UTC per instant.** Session opens are defined as "17:00 America/Chicago on the previous calendar day"; build `datetime(y, m, d, 17, tzinfo=ZoneInfo("America/Chicago"))` and call `.astimezone(UTC)`. Never add a fixed offset. `zoneinfo` is stdlib and `tzdata` 2025.3 is already locked, so this needs no new dependency.

**Library for the CME schedule: `pandas_market_calendars`, wrapped behind the port.** Verified from source (`pandas_market_calendars/calendars/cme_globex_equities.py`): class `CMEGlobexEquitiesExchangeCalendar`, alias `"CME Globex Equity"`, `ZoneInfo("America/Chicago")`, `market_open = time(17)` with a -1 day offset, `market_close = time(16)`, and explicit US holiday and early-close rules (10:30 / 12:00 / 12:15 / 8:15 groups, incl. Juneteenth from 2022). That is exactly ES/NQ/YM's session. `exchange_calendars` has only a generic `CMES` entry and is built around equity-exchange sessions with lunch breaks; it does not model the futures maintenance halt or the previous-day open as cleanly, and `pandas_market_calendars` already re-exports `exchange_calendars` if you ever need XNYS. `pandas` is already a dependency, so the cost is one package and the import-linter contract (keep it in `core/infra`, expose only the port to `engine`). Belief, not verified: `pandas_market_calendars` does not model the 16:00-17:00 halt as a `break`, because the halt is simply the gap between `market_close` and the next `market_open`; that is correct for your purposes (a 1m bar at 16:30 CT is not a trading minute).

**What not to do.** Do not shift stored timestamps to Chicago time; do not add a `tz_offset` column; do not model the calendar as Mongo documents you have to keep in sync with CME notices; do not special-case "if symbol endswith 1!" in the cascade; do not let the interval enum own periods-per-year once a second calendar exists.

## Work checklist

1. `scheduler.py:219-233` — `CronTrigger(..., timezone=UTC)`; unit test on `trigger.timezone`.
2. `deploy/Dockerfile`, `compose.prod.yml`, `compose.local.yml`, `justfile be` — `TZ=UTC`.
3. Lifespan startup assertion + one INFO log; assertion that all registered triggers are UTC.
4. `pyproject.toml` — add `DTZ` to ruff select; fix the hits.
5. `mongodb.py` — `tz_aware=True, tzinfo=UTC`; `integrity_jobs.py:50` aware; delete the naive branch at `bar_builder_domain_service.py:24`; rerun `test_mongo_datetime_normalization.py`.
6. `Bar.datetime` -> `AwareDatetime`, UTC-normalising validator; validators on `GetOHLCVQuery`/`RunBacktestCommand` DTOs; `to_utc_iso()` at the four `.isoformat()` sites.
7. `binance_adapter.py:80-83` — Monday-aligned 1w cutoff (P1-2).
8. Introduce `ITradingCalendarPort` + `Continuous24x7Calendar`; thread the calendar through `get_bar_start`/`is_bar_aligned`, `compute_boundaries`/`_TF_EXPECTED_BARS`, `check_integrity`, `_is_stuck`/`emit_no_progress`, `periods_per_year`. Crypto behaviour must be byte-identical (assert with existing tests).
9. Add `pandas_market_calendars` in `core/infra`, `CmeGlobexEquityCalendar` adapter; `calendar_id` + `session_date` on symbols/bars; DST-crossing tests for 2026-03-08 and 2026-11-01 and for a Juneteenth early close.
10. CI matrix: unit suite under `TZ=Asia/Saigon` and `TZ=America/Chicago`.

## Success metrics

- Same `next_run_time` (UTC) for every cron job when the process starts under `TZ=UTC`, `TZ=Asia/Saigon`, `TZ=America/Chicago`.
- Zero `misaligned_bars_dropped`, `integrity.issues_found`, `no_progress`, or `partial_aggregate` events for a futures symbol across one full week including a weekend and one early-close holiday.
- Futures 1d bars match the vendor's session OHLC (open at 17:00 CT, close at 16:00 CT) on both sides of a DST transition.
- ruff `DTZ` clean; no naive datetime reaches a repository (assert in `BaseRepository` under tests).
- Crypto metrics, bars, and cascade output unchanged after the refactor (golden-file test).

## Assumptions

- The futures provider will deliver bar open timestamps as instants (epoch or offset-bearing ISO), not naive local wall time. Confidence: medium. If it delivers naive Chicago wall time, the adapter must localise with `ZoneInfo("America/Chicago")` and `fold` handling before constructing `Bar`; nothing else in this report changes.
- ES/NQ/YM use the CME Globex equity session (Sun 17:00 - Fri 16:00 CT, halt 16:00-17:00). Confidence: high for the session; medium on any residual intraday pause, which the calendar library would encode if it exists.
- Production container base image defaults to UTC. Confidence: high, but the recommendation is to stop depending on it.
- The "advisor" run owns provider selection; this report only constrains the provider's timestamp contract.
