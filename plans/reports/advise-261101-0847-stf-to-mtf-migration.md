# Advice: retire single-timeframe strategies and build a generic multi-timeframe foundation

Date: 2026-11-01 (Asia/Bangkok). Repo: `D:/w/_me/algotrading/pocketquant`, branch `develop` @ `689c15d0`. Mode: `ak:advise --agent`.
Previews (hypothetical end state, assumptions marked): [architecture diagram](./advise-261101-0847-stf-to-mtf-migration-preview.html), [scope boundary](./advise-261101-0847-stf-to-mtf-migration-scope-preview.html), [generic UI mockup](./advise-261101-0847-stf-to-mtf-migration-ui-mockup.html). Interview record: [state file](./advise-261101-0847-stf-to-mtf-migration-state.md).

Facts below marked **V** were verified in the repo or a fetched spec on 2026-11-01; everything else is my inference or the owner's decision.

## Corrections (2026-11-01, verified by kongming)

Re-verified against `develop` and against prod (read-only queries, 07:58-08:05Z). The owner's confirmed decisions are unchanged; only wrong data-path claims and their downstream mentions were fixed.

- Wrong: "1d and 1w are REST-only and refreshed only by `sync_repair` (00:00/12:00 UTC), `sync_backfill` (03:00) and `sync_integrity` (04:00)", and "add one hourly freshness job". Right: `sync_integrity` is read-only (`src/pocketquant/engine/market_data/app_services/sync_jobs.py:440-479` only calls `check_integrity`); `sync_repair` skips 1w (`integrity_jobs.py:79-87,131-143`); 5m-4h are cascaded from 1m inside `sync_1m` every minute at +12 s (`sync_jobs.py:388-427,734-740`), so they lag the venue by seconds; 1d reaches Mongo through `sync_repair` at 00:00 UTC (prod: `created_at` 00:00:18Z-00:39:51Z over the last 8 session days) with `sync_backfill` at 03:00 UTC as fallback; 1w through `sync_backfill` (prod: Sunday 03:01-03:03Z). No hourly job exists and none is added. Item 6 now plans a 1d cascade instead; requirement R6 and scout line 14 in the state file are superseded by this report.
- Wrong: "lags the venue by up to an hour". Right: seconds for 5m-4h; 18 s to 40 min after 00:00Z for 1d today; 3 h after Sunday 00:00Z for 1w, while gold and FX are closed. The 1d cascade in item 6 removes the 1d lag.
- Wrong: "stored Exness 1d/1w bars are vendor session candles" that differ from UTC buckets. Right: Exness D1 opens at 00:00Z and W1 on Sunday 00:00Z (`src/pocketquant/core/infra/calendars/exness_session_calendar_adapter.py:8,84-89,180-183`), and on prod every stored REST 1d bar of the last 8 session days equals the aggregate of that UTC day's stored 1m bars exactly on OHLC for all three Exness symbols (one BTCUSD volume difference of 0.009%). The "don't route live 1d/1w events" bullet keeps its conclusion with a corrected reason.
- Verified, was listed as unverified: the REST sync never stores the open vendor 1d/1w candle (`src/pocketquant/core/infra/exness/exness_adapter.py:39-43,60` keeps only bars before `exness_bar_start(now)`).
- Prod state re-verified (see Prod checks): two subscriptions; one running, on BTCUSDT:BINANCE with two open paper positions.

## Needs from you

1. **The prod delete is destructive.** When the executor lists the exact subscription, position, order, trade and backtest documents it will remove, say yes once more before it runs. Recommended: yes, after reading the list.
2. **Safety dump: decided, none.** The owner decided on 2026-11-01 that nothing is backed up before the STF delete. The executor takes no dump. The trade-off stands: a wrong delete filter cannot be undone, so the executor shows the exact document list (item 1) before deleting.
3. **Open BTCUSDT:BINANCE paper positions: decided, delete with the STF data.** The owner decided on 2026-11-01 that the two open paper positions under the Binance STF subscriptions are deleted with the rest of the STF data; they are not left to close at SL/TP.

## Verdict

Yes, retire the two STF strategies and their subscriptions, and build the multi-timeframe foundation you confirmed. The platform you have is worth keeping almost whole: brokers, risk, lease roles, reconcile loop, sync jobs, position store, backtest engine and the compare view all stay, and the cascade aggregator changes in one place only (item 6: it builds the 1d bar for session calendars too). What changes is narrow and well located: the subscription gains `intervals` and `parameters`, the one shared bar handler gains higher-timeframe context read from Mongo through a per-(symbol, interval) cache, the Signal gains two capabilities (pending stop entry, strategy exit), and a generic snapshot carries strategy state to a strategy-agnostic UI. Your two late corrections made the plan better: generic contracts stop Triple Screen from leaking into the platform, and the spike-first order means the full build only hardens what already works. The one rule you reversed, "exits are SL/TP only", is a real cost: it touches the risk check, both brokers, the position store, the UI and the architecture doc, and it must land as one change.

## What you should do

1. **Stop first (done 2026-11-01).** Both prod subscriptions (engulfing on BTCUSDT:BINANCE 1m, engulfing EURUSD:EXNESS 1h) show `desired_state=stopped` and `actual_state=stopped`, set through `POST /subscriptions/{id}/stop` and confirmed after the reconcile loop converged. **V** the loop owns load/unload; routes only write Mongo.
2. **Spike the foundation end to end on `develop`** with the first consumer as the probe (requirement 13). The spike is allowed to be rough; its output is a go/no-go per piece recorded in the plan.
3. **Delete STF in one commit**: two services, `engulfing_detector.py`, registry entries, their unit and backtest tests; repoint the integration-test fixtures to the new strategy code. **V** `web/src/lib/indicators/engulfing.ts` says it mirrors the Python detector and is locked by a golden fixture that both a Python test and a web test read; keep the web test and fixture, rewrite that comment in the same commit.
4. **Subscription contract**: replace `interval` with an ordered `intervals` list (lowest = entry) and add `parameters`; unique index on `(strategy_code, symbol, intervals)`; validate on create that each higher interval is a multiple of the entry interval and that `parameters` passes the strategy class's own validation. **V** today's create route and `add_symbol` carry no parameters and reconcile builds `StrategyConfig` without them, so this closes a real gap.
5. **Higher-timeframe context from Mongo, one code path.** Put the context fetch in `StrategyAppService._on_bar_completed`, which **V** serves live, warm-up and the backtest sandbox alike and already holds `_bar_repository` and `_calendar_factory`. Cache closed bars per `(symbol, interval)`; re-query only when the entry bar's end passes the cached bucket end, using the symbol's calendar for the bucket end. **V** the cascade persists partial buckets, so the closed-bucket filter is mandatory, not defensive.
6. **Cascade the 1d bar from 1m for Exness symbols (plan, not done).** Today `cascade_tfs` (`src/pocketquant/engine/market_data/app_services/cascade_aggregator.py:34-41`) omits `DAY_1` for session calendars on the belief that a vendor daily bar need not match a UTC-day bucket. **V** That belief is false for Exness: D1 opens at 00:00Z (`exness_session_calendar_adapter.py:8,180-183`), `session_date` is the UTC date (`:170-171`), and on prod the stored REST 1d bars equal the UTC-day aggregate of the stored 1m bars (Prod checks below). With the cascade, yesterday's daily bar is final in Mongo seconds after the 00:00:12Z `sync_1m` run instead of 18-40 min later, and the closed-bucket filter admits it from 00:00Z. The machinery exists: `compute_boundaries` walks 1d through `calendar.bar_start` (`:86-113`), `trading_minutes` bounds the 1m read (`:141-149`; prod 1m counts of 1378, 1258 and 119 per day match the calendar), and the bar carries `session_date` (`:163-174`).
   - Files: (a) `cascade_aggregator.py`: delete `_INTRADAY_CASCADE_TFS`, `cascade_tfs()` and the comment at 34-37; `cascade_for_symbol` iterates `CASCADE_TFS`; drop the `CALENDAR_CRYPTO_24_7` import. (b) `src/pocketquant/engine/market_data/tracked_symbols_backfill.py:80-102`: delete the `DAY_1` direct-mode override and its `CALENDAR_CRYPTO_24_7` import; `_CASCADE_DEFAULT_TFS` (`:22-29`) already holds `DAY_1`. (c) `sync_jobs.py:48-56`: rewrite the comment: 1d cascades for every calendar; 1w stays REST because Binance weeks open Monday and Exness weeks Sunday, and no cascade convention exists. Expected diff: about -55/+10 lines in src and -70/+45 in tests; no schema, index, route, env or doc change (no doc under `docs/` states the rule, checked by grep).
   - Tests: invert `TestCascadeTimeframesDependOnTheCalendar` in `tests/app_test/market_data/test_cascade_aggregator.py:511-544` into two tests: a session calendar cascades `DAY_1` with the bar stamped at UTC midnight, `session_date` equal to the UTC date, and `find` called with `limit = len(trading_minutes) + 5` (1378 + 5 for an XAUUSD Monday, 119 + 5 for its Sunday); the timeframe order is unchanged. In `tests/engine_test/market_data/test_backfill_daily_mode.py` delete the three override tests (lines 73, 97, 114) and the header comment, keep `test_crypto_daily_backfill_still_cascades`, and add one test that a session-calendar `DAY_1` auto backfill resolves to cascade. The golden test is untouched (`CASCADE_TFS` and the 24/7 calendar do not change).
   - REST 1d stays as backfill: `SYNC_INTERVALS` keeps `DAY_1` for `sync_backfill`, because the cascade cannot build history older than the stored 1m bars (XAUUSD 1m starts 2025-10-21; its 1d holds 2363 bars), and `sync_repair` keeps its gap fallback. Writer order: `upsert_bar` writes only when OHLCV differ and the last writer sets `source` (`src/pocketquant/core/infra/persistence/repositories/bar_repository.py:42-98`); the cascade rewrites the current and the previous UTC day every minute until 01:40Z (100-minute lookback); `sync_backfill` never touches an existing datetime (`filter_new_bars`); `sync_repair` resyncs 1d only when a 1d bar is missing inside its 7-day window (`integrity_jobs.py:58-62,91-95,145-154`), which the cascade now prevents on every normal day, so the 00:00Z 5000-bar 1d fetch per Exness symbol disappears. Sources become mixed (`cascade` for new days, `rest_backfill` for history); no reader branches on `source` (grep).
   - 1w: nothing now. It stays REST via `sync_backfill`; the closed week lands Sunday 03:0x Z, before gold and FX reopen (22:01Z and 21:05Z); only BTCUSD:EXNESS trades in that gap. Cascading 1w from 1d through the calendar's Sunday-anchored `bar_start` is a later option if a 24/7 Exness symbol gets a 1w top interval (`tf_seconds` lacks `WEEK_1`; `check_integrity` skips 1w).
   - Risks: a venue no-tick gap at a session open could make the cascade open differ from the vendor open, and nothing rewrites it because repair checks presence, not values; 8 days per symbol on prod showed no such difference, and the plan's validation step reruns the same 1d-versus-1m comparison a week after deploy. Today's partial daily bar becomes visible for Exness symbols on the chart, as it already is for Binance symbols; the context reader's closed-bucket filter must drop it (already required by item 5). The 1d re-aggregation reads up to 1440 1m documents per Exness symbol per minute, the cost the three Binance symbols already pay. This reverses the decision recorded in the `test_backfill_daily_mode.py` header on new evidence (the prod equality), which the review rules allow.
7. **Capabilities, not modes.** Extend `Signal` with `entry_type: market | stop` and allow `Direction.EXIT`. Risk check: accept EXIT when a position is open; keep rejecting entries against an open position. Paper broker: pending stop fills on the next bar's high/low touch; EXIT closes at market. Exness: **V** the client only has `openPosition`; the public spec exposes `DELETE /v1/trading/accounts/{id}/positions/{position_id}` (full or partial close) and `POST /v1/trading/accounts/{id}/orders` with `order_type` `limit | stop | sltp`, both async 202 + `operation_id` like open. Rewrite the "Exits are SL/TP only" decision and the "One take-profit per entry" table in `docs/system-architecture.md` in the same change.
8. **Generic snapshot.** Each entry bar the strategy returns `readings[{interval, name, value, ok}]`, `decision{action, reason}` and `pending{side, price} | null`. The trader writes it to Redis per subscription (the existing trader-to-Redis-to-api path); the UI renders the table. Nothing in the UI knows the strategy.
9. **UI** as in the mockup: list row, detail drawer, create and edit form, and the actions start, stop, edit while stopped, delete with a warning, close at market and cancel pending with a real-money confirmation that goes through the same paths the strategies use.
10. **Backtest**: add `intervals` to `BacktestConfig` and the form; show intervals and parameters in the run header and the existing compare view. **V** `run-compare-view.tsx` and `metrics-diff-table.tsx` already exist.
11. **Triple Screen** last, as a strategy file only: MACD-histogram slope on the top interval, two-bar Force Index on the middle interval, entry on the entry interval; its own parameters pick `entry_type` and exit mode. Backtest two or three interval sets and both entry and exit variants, then pick the live set.

## What you shouldn't do

- Don't read higher-timeframe bars inside the strategy class. **V** import-linter forbids `core.domain` importing `core.infra`; the engine already owns the repository, so the fetch belongs there. This is a lint fact, not a layering opinion.
- Don't route the trader's live 1d/1w `BarCompletedEvent`s into strategies as context. **V** the stored Exness 1d/1w bars use the same UTC buckets as the live ones (prod check 2026-11-01), so the window is not the problem; the source is. The trader builds those bars from ticks and never persists them, the backtest can only read Mongo, and a tick-built bar can differ from the stored one after a feed gap. One source, Mongo, is what keeps the live view equal to the backtest view.
- Don't add a `context_intervals` field, a ratio field or any Triple-Screen-named parameter to the subscription. One `intervals` list plus a generic `parameters` dict covers every future MTF strategy.
- Don't query Mongo per entry bar for context. Re-query only on bucket rollover, and load each interval once for the whole range in a backtest; otherwise a 100k-bar backtest turns into 100k round trips.
- Don't persist a decision history collection now. You chose the bounded Redis ring; a collection would also need a cleanup job and a cascade entry in `TrackedSymbolService`.
- Don't run a 100-instance load test now. Keep the design scale-aware (shared cache, bounded writes) and measure when a second strategy exists.
- Don't remove the tracked symbol to "clean up". **V** `TrackedSymbolService.remove` cascades market data, subscriptions, backtests and live rows.
- Don't deprecate-and-keep the old `interval` field or the STF codes. Delete them in the same change; no compatibility was asked for.

## What could be better

Ranked by effort against impact.

1. **Order the spike so the cheapest proof comes first**: subscription `intervals`/`parameters` and the Mongo context fetch with the closed-bucket test, then snapshot to UI, then EXIT in paper, then pending stop in paper, then backtest with intervals. The two paper capabilities are the riskiest; proving the data path first keeps a late no-go cheap.
2. **Reuse the warm-up replay for the context cache.** Warm-up already replays closed entry bars through `on_bar_completed`; if the context fetch lives in that same handler, warm-up gets higher-timeframe context for free and you avoid a second loader.
3. **One place for "closed before this instant".** The filter is used by live, warm-up and backtest; write it once next to the cache, with the no-look-ahead check as its test (first entry bar of a new bucket sees the previous bucket's close). It must also drop the cascade's partial bucket of the current day, which item 6 makes visible for Exness symbols.
4. **Treat the pending stop as "cancel then place" on every signal**, not as an edit. It matches both the paper model and the Exness async pattern and avoids a modify path.

## My take and how to get there

Current state (**V** prod, 2026-11-01 08:00Z): two paper subscriptions, one running (`engulfing` on BTCUSDT:BINANCE 1m) and one stopped (`engulfing` on EURUSD:EXNESS 1h); zero exness-broker subscriptions; live disarmed; entries paused; two open paper positions on BTCUSDT:BINANCE; two STF strategies in code.

Route:

1. Stop all subscriptions (done 2026-11-01; both show `actual_state=stopped`).
2. Open one plan under `plans/` with phases: 01 spike, 02 delete STF, 03 subscription contract, 04 context from Mongo plus the 1d cascade of item 6, 05 capabilities (stop entry, EXIT) with doc rewrite, 06 snapshot plus UI, 07 backtest intervals, 08 Triple Screen and backtests, 09 prod data delete and paper run.
3. Run the spike (phase 01) and record go/no-go per piece. Stop and rethink only if the Mongo context path or the paper EXIT fails; everything else is UI and plumbing.
4. Build phases 02-07 on `develop`; keep every flow within three files and every new field with a real second caller (the subscription and the backtest config are the two callers for `intervals` and `parameters`).
5. Write Triple Screen, run the backtests, pick the live set, start one paper subscription.
6. Delete the STF prod data last, after the new paper subscription runs, so the system is never empty.

## Benefits

- Every live decision carries higher-timeframe context, read from the same Mongo bars the backtest reads, so the view is identical in both.
- A new MTF strategy is one file plus a registry entry: no subscription, UI or backtest change.
- You can see why a subscription did or did not act, per bar, without opening logs.
- Pending stop entries and strategy exits are available to any strategy, paper and Exness alike.
- Mongo reads scale with bucket rollovers and symbols, not with instances or bars, which keeps the future 100-instance goal open.
- The codebase holds one strategy family and no dead STF code.

## Trade-offs

- **Lifting "exits are SL/TP only"** (your decision) widens the money path: the risk check, both brokers, the position store and the UI all change together, and the Exness close path is new, untested code behind the live flag. Cost if a bug slips: an unintended close on a real account. Mitigation is the spike in paper and keeping live disarmed.
- **Mongo as the context source** (your decision) needs the closed-bucket filter and, for 1d, the cascade in item 6; without that cascade the daily bar arrives 18-40 min after 00:00Z (**V** prod). 5m-4h already arrive seconds after each minute, and 1w arrives Sunday 03:0x Z while gold and FX are closed. In-memory aggregation would have had no I/O; its real cost was warm-up replay volume, not per-bar compute. Switch back only if a 24/7 Exness symbol needs a 1w top interval and the 3-hour Sunday gap proves to matter; the switch costs the strategy file and the warm-up constant, nothing in the UI.
- **No STF safety dump** (your decision) means a wrong delete filter is unrecoverable. The owner confirmed on 2026-11-01: no backup; the document list shown before the delete is the only guard.
- **Pending stop fills approximated from next-bar high/low** in paper and backtest (A-3) will differ from a venue fill on a tick; backtest numbers for the touch variant are optimistic in fast markets.
- **Generic snapshot** limits the UI to tables; a strategy that wants a chart overlay cannot have one without breaking the "no strategy-specific UI" rule you set.
- This advice stops being right if a second data provider's higher-timeframe bars are not in Mongo at all; then the engine-side fetch has nothing to read and self-aggregation returns as the fallback.

## Prod checks (2026-11-01 07:58-08:05Z, read-only)

Every query was a `find`, `aggregate` or `count` over SSH against the prod Mongo, plus one GET to the Exness configuration endpoint from the api container. Nothing was written, restarted or ordered.

- **V** Subscriptions (2): `engulfing BTCUSDT:BINANCE 1m` running/running; `engulfing EURUSD:EXNESS 1h` stopped/stopped. No document carries a `broker` field, which the loader reads as paper; `broker: exness` count is 0. Tracked symbols: three Binance, three Exness.
- **V** Safeguards: `entries_paused=true`, `live_trading=false`, last written 2026-10-31T12:02Z.
- **V** Positions: 234 documents (169 BTCUSDT:BINANCE, 65 XAUUSD:EXNESS); 2 open (`is_closed=false`), both BTCUSDT:BINANCE. Orders: 241 `filled`, 18 `rejected`, no pending status present. Trades 215, backtest runs 21.
- **V** `job_history` cannot show "bars_inserted for 1d" from `sync_repair`: `repair_integrity` never calls `record_detail`, so repair runs carry no per-interval rows. The bars answer it instead: the latest 1d bar per Exness symbol (XAUUSD 2026-10-30, EURUSD 2026-10-30, BTCUSD 2026-10-31) has `source=rest_repair` and `created_at` between 00:00:18Z and 00:39:51Z of the next day, over 8 sampled days per symbol. `sync_backfill` rows confirm it: 1d `bars_inserted=0` for every Exness symbol on 10-29 to 11-01 (the bar was already there), and 1w `bars_inserted=1` per Exness symbol on 2026-11-01 at 03:01-03:03Z. The last five `sync_repair` runs finished in 57-106 s; `sync_integrity` in 5 s.
- **V** REST 1d versus the 1m aggregate of the same UTC day: identical open, high, low, close and volume for the last 8 session days of XAUUSD and EURUSD, Sunday bars included (119 and 175 minutes), and for BTCUSD except 2026-10-24 volume 113120 versus 113130 (0.009%). 1w versus the Sunday-to-Sunday 1m aggregate: identical for the last 3 weeks except two BTCUSD volume differences under 0.006%. 1d by source for XAUUSD: 2352 `rest_backfill`, 11 `rest_repair`. Stored 1m history starts 2025-10-21 (XAUUSD), 2026-06-12 (EURUSD), 2026-07-21 (BTCUSD).
- **V** Exness 4h bars are `source=cascade`, updated seconds after each minute (XAUUSD bucket 2026-10-30T20:00Z last updated 20:58:19Z).
- **Not resolved** Exness XAUUSD conditions (A-4): `GET /v1/configuration/accounts/{id}/instruments/XAUUSD/conditions` returned the keys base_currency, calc_mode, category, contract_size, description, exec_mode, instrument, international_name, margin_currency, margin_percent, point_digits, quote_currency, swap_long, swap_multipliers, swap_short, trade_mode, trade_sessions, volume_max, volume_min, volume_step. There is no `order_types` field, and `trade_mode` read `trading_disabled` because the market was closed (Sunday 08:00Z). Whether `stop` pending orders are accepted cannot be read from this account's conditions; the remaining read-only sources are the public spec (already read) and Exness support. Do not place an order to find out.

## Unverified

- Whether Exness accepts `stop` pending orders on XAUUSD (A-4): see Prod checks; the conditions payload does not say. The spike's paper path does not depend on it; the Exness pending-order path does.
- Elder's Triple Screen description is from my recollection of his books, not from a fetched source; it only shapes the first consumer, not the platform.
- Mongo query cost (1-3 ms per indexed find) and the Redis write rate (100 per minute worst case at 1m entry) are estimates, not measurements.

## Work checklist

- [x] Stop all subscriptions; confirm `actual_state=stopped` for each (done 2026-11-01).
- [x] Re-verify prod (done 2026-11-01 08:00Z, see Prod checks): 4 subscriptions, 3 running, 0 exness-broker, entries paused, live off, 2 open paper positions on BTCUSDT:BINANCE. Repeat the subscription and position queries right before the delete.
- [ ] Open the plan with phases 01-09 as listed above; record the confirmed reframing as its contract.
- [ ] Spike 01: subscription with `intervals` + `parameters` from the form; context fetch in `_on_bar_completed` with closed-bucket filter and the rollover test; snapshot to Redis and visible in the UI; EXIT in paper; pending stop in paper; manual close and cancel in paper; backtest with intervals in the compare view. Record go/no-go per piece.
- [ ] Delete STF services, detector, registry entries, tests; repoint integration fixtures; rewrite the `engulfing.ts` mirror comment; keep web test and fixture.
- [ ] Subscription entity, repository index, DTOs, create and edit routes, reconcile to `StrategyConfig(intervals, parameters)`; validation of multiples and parameters.
- [ ] Context cache per `(symbol, interval)` with calendar-aware closed filter; warm-up and backtest use the same handler; no per-bar queries.
- [ ] 1d cascade for session calendars per item 6: `cascade_aggregator.py`, `tracked_symbols_backfill.py`, the `sync_jobs.py` comment, the two test files; one week after deploy rerun the 1d-versus-1m prod comparison from Prod checks and record the result in the plan.
- [ ] `Signal.entry_type`, `Direction.EXIT` accepted by the risk check; paper pending-stop fill and market close; Exness `DELETE positions/{id}` and `POST orders` type `stop` behind the live flag; position store updates.
- [ ] Rewrite `docs/system-architecture.md` exits decision and the one-take-profit table; update any other doc line that states SL/TP-only.
- [ ] Generic snapshot type; trader writes Redis per subscription; api endpoint; UI list row, detail drawer, create and edit form, actions with real-money confirmation.
- [ ] `BacktestConfig.intervals`, form, run header, compare view labels.
- [ ] Triple Screen strategy file with parameters for `entry_type` and exit mode; backtests over 2-3 interval sets and both variants; pick the live set.
- [ ] Start one paper subscription; observe one entry, one strategy exit, one manual action.
- [ ] Prod delete of STF subscription, positions, orders, trades, backtests after the owner confirms the listed documents.
- [ ] Full test suite, import-linter, code-metric gate; docs check per `docs/governance/documentation-rules.md`.

## Success metrics

- `grep -r "engulfing" src/pocketquant/core/domain/strategy` returns nothing; `STRATEGY_REGISTRY` lists only MTF codes.
- Prod `subscriptions` has zero documents with STF codes; `positions`, `trades`, `backtests` have zero rows referencing them.
- A test asserts that the first entry bar of a new higher-timeframe bucket receives the previous bucket's close, and it runs in live, warm-up and backtest paths.
- The trader log shows at most one Mongo context read per `(symbol, interval)` rollover and none per entry bar.
- For each Exness symbol, yesterday's 1d bar has `source=cascade` and an `updated_at` before 00:01Z, and for one week after deploy its OHLC equals the vendor's REST 1d bar (the Prod checks query); `sync_repair` at 00:00Z no longer resyncs 1d for Exness symbols.
- The UI shows readings and a decision reason for a running subscription that change each entry bar.
- One paper pending stop fill, one paper strategy exit and one manual close appear in the orders and trades timeline.
- At least four backtests (2 interval sets x 2 variants) appear in the compare view with intervals shown.
- `uv run python -m pytest tests/ -q` is green except the known tzset red; import-linter passes.

## Handoff brief

```text
Objective: Retire the two single-timeframe strategies and build the generic multi-timeframe foundation confirmed on 2026-11-01 (plans/reports/advise-261101-0847-stf-to-mtf-migration.md), spike first, then full build, Triple Screen as the first consumer only.
Done means: spike go/no-go recorded per piece before full build; STRATEGY_REGISTRY has no STF code and nothing under core/domain/strategy references engulfing; prod has zero STF subscriptions, positions, trades or backtests; subscription documents carry intervals + parameters with a unique index on (strategy_code, symbol, intervals) and the form has a multi-select and parameters; strategies receive closed higher-timeframe bars from Mongo via a shared per-(symbol, interval) cache and a test proves the first entry bar of a new bucket sees the previous bucket's close in live, warm-up and backtest; the 1d cascade for session calendars is deployed and one week of prod data shows the cascaded 1d bars equal to the vendor 1d bars; the generic snapshot is visible in the UI and updates each entry bar; pending stop-entry and strategy EXIT each work once in paper and the Exness paths exist behind the live flag; manual close and cancel work in paper with confirmation; at least 2 interval sets x 2 parameter variants appear in the compare view with intervals shown; pytest green except the known tzset red, import-linter green, docs/system-architecture.md exits decision rewritten.
Out of scope: Exness live go-live (stays disarmed); MT5; partial close or multi-TP; any STF baseline or STF data retention; any Triple-Screen-specific field, panel, column or setting in platform or UI; Mongo decision history; a backtest sweep runner; a 100-instance load measurement; changes to the symbol-suffix-is-provider model, lease roles or reconcile loop; changes to the cascade aggregator beyond the 1d cascade in item 6 of the report; any 1w cascade.
Constraints: docs/governance/no-look-ahead-rules.md (closed higher-timeframe bars only, start-stamped bars, backtest view equals live view); CLAUDE.md KISS limits (flow in at most 3 files, a new class/flag/config needs a second real caller today, delete dead code in the same change, never deprecate-and-keep); core.domain must not import core.infra; no secrets in the repo; never remove a tracked symbol; plans and code in English; questions to the owner in Vietnamese.
Stop and ask only if: the spike returns no-go for the Mongo context path or the paper EXIT; you are about to delete prod documents (show the list and wait for yes; take no backup, owner decision 2026-11-01); a change would leave the confirmed scope or repository; the Exness pending-order path fails in the spike (the account's conditions payload has no `order_types` field, checked 2026-11-01; never place a test order to find out); the post-deploy 1d comparison shows a cascaded bar that differs from the vendor bar; a failure you cannot explain.
```
