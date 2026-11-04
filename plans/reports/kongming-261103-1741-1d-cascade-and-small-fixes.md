# Kongming counsel: 1d cascade fixes and four small fixes

Date: 2026-11-03 (Asia/Bangkok). Asked by the controller session after its own diagnosis. Advisory only. The plan `plans/261103-1741-1d-cascade-fold-and-small-fixes/` follows this counsel.

**TL;DR.** All six diagnoses hold; verified against code, the installed cachetools source, and prod logs. Change four of the six fixes: (1) add the cascade through one shared helper with a 7-day window and drop 5m-1d from the REST *repair* path (prod shows that path firing uselessly); (2) make the 1d check stored-1d vs aggregate-of-stored-1m, not REST; (3) also delete `expected_count` and the three tests that pin the limit; (5) keep the Binance re-raise. Items 4 and 6 are right as proposed, with small precisions.

## Verified prod evidence (read-only, worker/trader containers started 2026-11-02T08:49Z, so ~32 h, two `sync_repair` runs)

- `integrity.repaired`: 6x `interval=1m`, 2x `interval=5m`. `integrity.repair.still_missing`: 2x 1m, 2x 5m. `integrity.issues_found`: 6x 1m, 1x 5m. `cascade.divergence_alert`: 0.
- Trader: exactly one `binance_ws.callback_failed` and one `binance_ws.error` in the window (the 11-03 event). No `exness_ws.callback_failed`.
- Prod logs are ANSI-coloured; grep `key=value` only after stripping `\x1b\[[0-9;]*m`.

So late 1m fills happen on every repair run (item 1 is live, not theoretical), and the 5m REST resync fires on gaps it then cannot fill (venue-empty minutes), rewriting 5000 5m bars with `skip_filter=True` each time.

## Item 1: late 1m bars never folded

Verdict: agree on the diagnosis; change the fix.

1. Extract the loop at `sync_jobs.py:400-417` into `_cascade_all(lookback_minutes) -> dict[Interval, int]` (resolves repo and calendar factory from the container like `_rest_sync`). Three real callers: `sync_1m` (100), `sync_repair`, `sync_backfill`. Call it in `sync_repair`'s body after the symbol loop and before `if failed: raise` (`sync_jobs.py:515`), so symbols that repaired fine still get folded when one symbol failed, matching the `sync_1m` comment at `:381-382`. Turn `sync_backfill`'s lambda (`:425-432`) into a body like `sync_1m`'s: `_rest_sync(...)` then `_cascade_all(...)`.
2. Window: fixed 7 days. One constant `_REPAIR_DAYS = 7`, passed explicitly as `repair_integrity(..., days_back=_REPAIR_DAYS)` and as `_cascade_all(_REPAIR_DAYS * 1440)`, so the two stay tied. Keep `lookback_minutes`; do not add `range_start`.
3. Reject the "earliest repaired gap" alternative: `repair_integrity` resyncs with `skip_filter=True` (`integrity_jobs.py:147-154`), so a revised 1m bar with no gap is also rewritten (`bar_repository.py:84-98`) and needs a re-fold; a gap-derived start misses it. Backfill has no such signal either.
4. Drop 5m-1d from the REST repair: iterate `[i for i in SYNC_INTERVALS if i not in CASCADE_TFS]` (1m, 1w; 1w repair is misaligned-delete only, `integrity_jobs.py:79-87,131-143`). Keep backfill untouched: it inserts missing bars only (`sync_service.py:82-85`) and is the deep-history source (`sync_jobs.py:48-51`); update that comment. Loss: misaligned-bar deletion for 5m-1d, which cannot occur for cascade bars (`calendar.bar_start` boundaries) and is filtered at REST insert (`sync_service.py:87`); `sync_integrity` still warns (`sync_jobs.py:450-465`).

Cost (inference, unmeasured): per symbol 2016+672+168+42+7 = 2,905 buckets, each one `find` plus one `find_one` inside `upsert_bar` (`bar_repository.py:52`), about 35k indexed round trips per run for 6 symbols; expect low minutes, twice a day.

Risks:
- 1m-history edge bucket. The cascade persists partial buckets by design (`cascade_aggregator.py:97-99,131-138`). For a symbol tracked less than 7 days (1m backfill is 5000 bars, about 3.5 days), the oldest 4h/1d bucket only partly covered by 1m is rebuilt from partial 1m and overwrites the full REST backfill bar. Bounded: one bucket per TF per symbol, gone from the window after 7 days. Accept and record it.
- The repair cascade at 00:00 overlaps `sync_1m`'s cascade at 00:00:12 on the same buckets. Both are idempotent (`bar_repository.py:81-82`); a stale write loses to the next minute's `sync_1m`. No action.

Test: patch `cascade_for_symbol` and assert (a) repair calls it once per tracked symbol with `lookback_minutes=10080` even when one symbol's `repair_integrity` raised; (b) `repair_integrity` is called only for 1m and 1w; (c) backfill calls the cascade after `_rest_sync`.

## Item 2: no 1d value check

Verdict: change. Use self-consistency (stored 1d vs aggregate of stored 1m), not REST-vs-stored.

- It targets the two failure modes Phase 17 named (stale fold, REST overwrite) and the truncation in item 3. REST-vs-stored also fires on venue-vs-aggregate differences that cannot be acted on, and for Binance that equality is unmeasured. Self-consistency removes the need for a prod measurement first.
- No provider calls and no newest-bucket race: both reads see the same Mongo state.
- Coverage: the hourly 5m REST check proves stored 1m against the venue transitively; 1d self-consistency closes the fold.

What to do: extract from `cascade_for_symbol` the per-bucket read-and-aggregate (`cascade_aggregator.py:118-155`) into `aggregate_bucket(symbol, tf, boundary, bar_repo, calendar) -> Bar | None`; two callers (cascade, verify). In `sync_verify_cascade`, after `_verify_one_symbol`: for each boundary from `compute_boundaries(DAY_1, now - 4d, now, calendar)` with `boundary + 1d <= now`, fetch the stored 1d, call `aggregate_bucket`, skip when either side is absent (presence is integrity's job), and warn `cascade.daily_divergence` with `datetime` and the `compare_bar_fields` result. The job needs `TradingCalendarFactory` from the container. About 25 lines. Do not parametrize `_verify_one_symbol`. Trade-off: the same `aggregate_ohlcv` computes both sides, so a bug there is invisible to this check; the 5m REST check covers that.

Test: fake repo with a day's 1m bars and a stored 1d whose close differs gives one warning naming that day; equal gives none; the in-progress day is never compared.

## Item 3: read limit truncates

Verdict: agree, plus two deletions. Drop `limit=` at `cascade_aggregator.py:129` and delete `expected_count` with its `trading_minutes` call and comment (`:120-122`); `trading_minutes` keeps its caller at `integrity_jobs.py:43`. The query is bounded by the bucket range (at most 1440 docs for 1d) and the unique index (`bar_repository.py:235-239`) rules out duplicates. Only a future 1w cascade (10080 > 5000) would need a thought.

Tests that pin the old behaviour and must be deleted: `test_a_halted_hour_bounds_the_query_by_the_calendar` (`test_cascade_aggregator.py:454-460`), `test_the_same_hour_on_a_24x7_calendar_fetches_sixty` (`:462-467`), the `limit` assert at `:551`, and `test_a_short_session_day_bounds_the_daily_read` (`:553-556`).

New test: with the `mock_bar_repo` fixture (`:280-321`, sorts descending and applies `limit`), store all 1440 minutes of a weekday as 1m bars for `XAUUSD` (its calendar expects 1383), cascade one 1d boundary, assert the upserted open equals the first bar's open and volume equals the sum. The old code reads 1388 bars and gets the wrong open.

## Item 4: remove the positions route

Verdict: agree. No `/positions` call under `web/src`, no doc names the route, `StrategyQueryService` still needs `position_repository` for `list_symbols` (`:62`) and `get_trades` (`:125`). Remove the line at `test_admin_token_guard.py:101`; delete the two tests at `test_strategy_service.py:525-548` and fix the section comment at `:521`; then delete `_open_position()` in that file if it has no remaining caller. `test_exness_live_trading_off.py:62` matches `/positions` but is an Exness client path assertion; leave it.

## Item 5: TTLCache race and the re-raise

Verdict: diagnosis verified; fix is right; do not remove the raise.

cachetools 7.1.4: `TTLCache.__contains__` evaluates `self.timer() < link.expires`, `__getitem__` evaluates `not (self.timer() < link.expires)` and calls `__missing__`, which raises `KeyError(key)`. Two clock reads, so the window exists. `_TimedCache.get` wraps `Cache.get` in `with self.__timer:`, which freezes the clock for the nested `in` and `[]`, so `_CACHE.get(key, _MISS)` is race-free. Equally correct: `try: return _CACHE[key] except KeyError: pass`.

Test: monkeypatch `symbol_lookup_helper._CACHE` with `TTLCache(maxsize=500, ttl=60, timer=fake)` where `fake` yields `[0, 59, 60, ...]`; call `get()` twice. Old code raises `KeyError`; new code returns the cached value.

Keep the re-raise: (a) one callback failure since 2026-11-02T08:49Z, caused by this bug; (b) without the raise, a persistent callback failure logs one ERROR per aggTrade at 50-500/s/symbol, which CLAUDE.md forbids above DEBUG; the reconnect loop bounds it to one ERROR per backoff step; (c) one reconnect costs about a second of ticks, and that minute's 1m bar is rewritten by REST `sync_1m` (inference). Optional: `exc_info=True` on `binance_ws.error` (`binance_websocket_adapter.py:117`), bounded to one per reconnect.

## Item 6: local ports

Verdict: agree, two precisions. Dynamic range 49152-65535; excluded ranges now 5357, 50000-50760, 65035-65134. 53679 and 52017 are free today but sit where the blocks move; below 49152 only 5357 is excluded. 46379 and 47017 have no listener now. `just tunnel` reads `MONGO_PORT`/`REDIS_PORT` from `../pocketquant-config/vps/default/.env` (`justfile:46-47,53-54`), never from the local profile, so prod ports stay. Per file: `all-local.env` changes both PORT vars and both URLs; `remote-db-local-redis.env` changes `REDIS_PORT` and `REDIS_URL` only, `MONGODB_URL` stays; `remote-db.env`'s PORT vars are unused (its own comment at line 20). Put the reason as a comment in the env files. Run `just down` before switching. Verification is `just up` + `just be` on the all-local profile.

## Phase order

- Item 6 first (outside the repo), so local `just up` works for later verification.
- Items 3, 4, 5 together: three independent small fixes with tests. Ship before item 2 so the 1d check does not share the limit bug; item 5 is a live reconnect cause.
- Item 1 on its own: it changes two prod jobs' behaviour and cost.
- Item 2 after item 1.

## Success metrics

- Item 1: zero `interval=5m` repair lines; job duration bounded; the Phase 17 D16 dry-run comparison shows 0 mismatches for post-deploy days.
- Item 2: `cascade.daily_divergence` stays 0 for a week; when it fires, the log names the day.
- Items 3-5: no `binance_ws.callback_failed` with a `KeyError` text; ratchet not raised; route list test green.

## Assumptions

- Six tracked symbols (medium; affects only the cost estimate).
- Binance REST 1m has no gaps that REST 5m could fill, so dropping 5m-1d from repair loses nothing (medium).
- The prod sample is 32 h; the 5m-overwrite frequency beyond that is extrapolation (medium).
- Live tick-built 1m bars are rewritten by `sync_1m` REST at +12 s (medium, inferred from `sync_jobs.py:718-720`).
