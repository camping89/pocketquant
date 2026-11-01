# Red team: assumptions lens (Assumption Destroyer + Scope Auditor)

Reviewed: `plan.md` and phases 01-17 against `develop` @ `e4a998b8`. Every code citation was read or grepped in this session. Inferences are labelled.

## Finding 1: The snapshot `pending` shape and `/orders` row keys disagree across Phase 11, Phase 13 and owner contract C7
- **Severity:** High
- **Location:** Phase 11, Task 11.1 step 6 and Task 11.3 step 4; Phase 13, Task 13.1 step 2 and Task 13.2 step 1.
- **Flaw:** C7 (`reports/debate-evidence-packet.md`, table C7) fixes `pending{side, price} | null`. Phase 11 writes `pending = {side, stop_price, sl_price, tp_price}` and does not list this as a deviation. Phase 13 types `SnapshotEntry.pending` as `{ side: string; price: number }`, and its pinned test calls `pendingText({ side: 'buy', price: 71250 })`. Phase 11's `/orders` rows are `id, side, order_type, status, quantity, stop_price, sl_price, tp_price, filled_price, created_at`. They have no `price` and no `updated_at`. Phase 13 lists both keys in `SubscriptionOrder`, and `timeline()` sorts orders by `updated_at`. Phase 13 Task 13.1 says "the code wins", but the Task 13.2 tests hard-code the C7 keys. The executor has to choose which phase to break.
- **Failure scenario:** If the executor follows the Task 13.2 tests, the row shows `BUY STOP @ undefined` (or `NaN`), because the data has no `price` key, and `timeline()` sorts every order on `undefined`. If it follows "code wins", the pinned fixtures no longer match the types and `tsc -b` or vitest goes red, which triggers the Failure Protocol. Either way A9 and the obs-6 `DRAWER OK` check run against a drawer whose pending section is wrong.
- **Evidence:** `OrderAggregate.to_mongo` has both `price` and `updated_at` (`src/pocketquant/core/domain/order/entities.py:181,188`), so Phase 11 leaves them out by choice, not because the data lacks them. `OrderSide` values are lowercase `buy`/`sell` (`src/pocketquant/core/domain/order/enums.py:11-13`), which matches the Phase 13 fixture.
- **Suggested fix:** Fix one shape in Phase 11 and copy it into Phase 13. One option: `pending = {side, price, sl_price, tp_price}`, where `price` is the stop price (a C7 superset). Add `price` and `updated_at` to the `/orders` rows. Then make the Phase 13 types and fixtures quote those exact keys.

## Finding 2: The Phase 06 Task 06.3 Verify can never print `readers=0`
- **Severity:** High
- **Location:** Phase 06, Task 06.3 Verify.
- **Flaw:** The grep `config\.interval\b|sub\.interval\b|body\.interval\b|doc\["interval"\]` runs over all of `src` and excludes only `engine/backtest`. `body.interval` also appears in the market-data integrity and repair routes. Their request bodies have nothing to do with subscriptions, and no phase changes or should change them.
- **Failure scenario:** After a correct Phase 06, the command prints `readers=2`. That is a failed Verify, so the executor stops, spawns kongming, and may "fix" the market-data route body to make the grep pass. That would be a change outside the contract.
- **Evidence:** `git grep` on HEAD gives `src/pocketquant/app/routes/market_data.py:109: return await check_integrity(symbol, body.interval, ...)` and `:125: body.interval,`. `market_data.py` is not in the Phase 06 Files list.
- **Suggested fix:** Limit the grep to the files the phase owns (`app/routes/strategy.py`, `engine/strategy`, `engine/live`, `core/domain/subscription`, `core/infra/persistence/repositories/subscription_repository.py`), or add `':!src/pocketquant/app/routes/market_data.py'`.

## Finding 3: Triple Screen loses track of its resting stop and its position on every skip, warm-up and deploy
- **Severity:** High
- **Location:** Phase 14, Task 14.2 step 5 (`on_order_filled` and `on_order_rejected`) together with Phase 09, Task 09.4 steps 4, 8 and 9.
- **Flaw:** Phase 14 sets `_open_direction = _armed` on an armed-side fill and clears both flags on any `on_order_rejected`. Phase 09 cancels the resting stop only inside `_process_signal`, after the `trading_until`, deadline and broker checks. It keeps stops across a handover and restores them at takeover. The engine calls `on_order_rejected` in four cases where the stop stays in the broker:
  - a stale, gap or inflight skip (`strategy_app_service.py:401-421`, `_notify_rejected`);
  - standby, drain or lease discards (`:513-537`, before the broker lookup);
  - every warm-up replay signal (`:265-266`);
  - takeover, which restores `_open_direction` from positions only (`:174-178`) and never restores `_armed`.
- **Failure scenario:** A deploy (D-2, or any later one) hands over while a stop rests. The new trader restores the stop (Phase 09 step 9). Warm-up replay clears `_armed`. If the setup is gone on the next live bar, no EXIT is sent, because `_armed` is `None`. The stop stays and later fills. `on_order_filled` then sets `_open_direction = _armed = None`, so the strategy thinks it is flat while paper holds a position. In `exit_mode=strategy` the tide-flip EXIT never fires. The position closes only at its SL. Later setups send entries that risk rejects. This breaks A7/obs-2 (a strategy EXIT on prod, D4) whenever a restart happens between a stop placement and its fill. A stale skip (`_STALE_AFTER_S["15m"] = 60`, `:43`) causes the same desync without a restart. Related: a manual "Cancel pending" (Phase 11) sends no event to the strategy, so with the setup still holding, the next bar re-places the stop. The cancel lasts one bar. The owner may accept this, but no phase states it.
- **Evidence:** Plan text: Phase 14 step 5, "a fill on the armed side (BUY for LONG) sets `_open_direction = _armed` ... `on_order_rejected` clears both". Phase 09 step 4: "after the broker lookup: `pending = pending_stop(...)`". Code: `src/pocketquant/engine/strategy/strategy_app_service.py:174-178,265-266,410-421,513-537`.
- **Suggested fix:** In Triple Screen, derive `_open_direction` from the fill side whenever the strategy is flat (BUY→LONG, SELL→SHORT). Do not clear `_armed` for engine skip reasons. Alternatively, have the engine cancel the subscription's resting stop whenever it rejects or skips a signal. Add a Phase 09 or Phase 14 test: a stop restored at takeover with `_armed` lost, then a fill, gives `_open_direction == LONG`.

## Finding 4: The "snapshot is changing" gates pass on warm-up records alone
- **Severity:** Medium
- **Location:** Phase 11, Task 11.1 steps 6-7; Phase 16, Task 16.6 Verify; Phase 17, Task 17.1 obs-5.
- **Flaw:** The warm-up replay appends up to 20 records to the in-memory ring (`write=False`). The first live bar then writes `list(ring)`, which includes those replay records. A replay bar with no signal gets outcome `no_signal`, the same as a live bar, so a reader cannot tell the two apart.
- **Failure scenario:** One live bar after start, Redis holds up to 20 entries with distinct `bar_start` and usually distinct readings. Task 16.6's `distinct_bar_start>=2` and obs-5's `distinct_readings>=2` pass even if the second live bar never writes, for example when every later write fails and only logs `strategy.snapshot_write_failed`. A9 ("visible and changing") is then marked met without evidence that the live path writes more than once.
- **Evidence:** Warm-up replays up to `_WARMUP_BARS = 500` stored bars (`src/pocketquant/engine/strategy/strategy_app_service.py:45,252-266`). Plan text: Phase 11 step 7, "The warm-up replay calls `_record_snapshot(..., outcome=... "no_signal", write=False)`", and step 6, "It writes `list(ring)`".
- **Suggested fix:** Count only entries with `bar_start >= paper_started_at` (Task 16.6, obs-5). Or mark replay entries (`outcome="warmup"` for every replay bar) and exclude them from both gates.

## Finding 5: The S4 cost spike does not represent the D3 `5m,15m,1h` set, and every rollover re-reads 500 bars
- **Severity:** Medium
- **Location:** Phase 01, Task 01.6 (S4 go bounds); Phase 07, Task 07.1 step 3 (`_refresh_context` uses `_closed_bars`); Phase 16, Task 16.2.
- **Flaw:** S4 runs 30 days of 1m with `1h,4h` context: 900 rollovers against 43,200 entry bars, about 2 %. The go bound is `t_mtf <= 2*t_stf`. Each rollover calls `_closed_bars`, which is `find(..., limit=_WARMUP_BARS)` with `_WARMUP_BARS = 500`, and decodes up to 500 pydantic `Bar`s.
- **Failure scenario (inference, computed from code constants, not measured):** XAUUSD trades about 5,980 hours a year. Runs 5 and 6 (`5m,15m,1h` over 2025-11-03..2026-10-30) have about 71.8k entry bars and about 29.9k rollovers (15m and 1h). That is up to about 15M `Bar.from_mongo` calls per run, against about 0.45M in S4: about 208 decoded bars per entry bar, against about 10. S4 can read `go` while the D3 runs cost far more than twice an STF run. These runs execute as asyncio tasks in the api process on the live Mongo pool, with no cap. The route itself says a large run "can starve live order persistence" (`src/pocketquant/app/routes/backtest.py:44-45`). Phase 16 then runs six of them in a row.
- **Evidence:** `src/pocketquant/engine/strategy/strategy_app_service.py:45,285-289`; `src/pocketquant/core/infra/persistence/repositories/bar_repository.py:100-128` (all docs materialised, `limit` default 5000); `src/pocketquant/core/domain/bar/entities.py:22` (`class Bar(BaseModel)`).
- **Suggested fix:** Add the D3 ratio to S4: a `5m,15m,1h` run over at least 60 days, with the same bound. Bound the rollover read to what changed. Keep the cached list and fetch only bars newer than its last bar (`start_date=last.datetime + step`), trimming to N. Or pass a smaller `limit` to the context read.

## Finding 6: The Phase 16 data check cannot detect partial or holed coverage of the cascaded intervals
- **Severity:** Medium
- **Location:** Phase 16, Task 16.1 (Verify: `inside > 0`, `before >= 36`).
- **Flaw:** The check proves only that some bars exist inside the range and that 36 exist before it. Cascaded 5m-4h bars come from `sync_1m` with a 100-minute lookback. So history before the live window exists only where a tracked-symbol backfill ran. The advice measured the start of the 1m data and the 1d sources, but not the 5m, 15m, 1h or 4h coverage.
- **Failure scenario:** If 5m or 15m cover only part of 2025-11-03..2026-10-30, or have multi-day holes (for example the VPS was down and backfill did not cascade them), `inside > 0` still passes. The backtest streams only the bars that exist, so runs 5 and 6 cover a shorter period without warning. After each missing higher bucket, the Phase 07 rule re-queries Mongo on every entry bar and logs a WARNING per window. The A10 comparison of six runs then compares runs over different effective periods.
- **Evidence:** `src/pocketquant/engine/market_data/app_services/sync_jobs.py:408-411` (`lookback_minutes=100`); `src/pocketquant/engine/market_data/tracked_symbols_backfill.py:22-29` (cascade-mode intervals); `plans/reports/advise-261101-0847-stf-to-mtf-migration.md:106` (only 1m start and 1d sources measured).
- **Suggested fix:** For each interval in Task 16.1, print `min` and `max` datetime inside the range and `inside` against the expected count. Get the expected count from `calendar.trading_minutes`, or run `check_integrity` with the range as `days_back`. Fail when coverage does not start within one top bucket of `START`, or when a hole is longer than one day.

## Finding 7: The D-2 rollback leaves `ix_subscriptions_dedup_intervals`, which the old code cannot satisfy
- **Severity:** Medium
- **Location:** Phase 15, Rollback.
- **Flaw:** The rollback deletes new-shape subscriptions and re-rolls the old image. It does not drop the new unique index. The old code writes no `intervals_key`, and its `ensure_indexes` creates only its own index.
- **Failure scenario:** After a rollback, every subscription the old code creates has `intervals_key` missing, which a unique index treats as null. A second subscription for the same `(strategy_code, symbol)` with another interval raises `DuplicateKeyError`. The old code maps that to `SubscriptionAlreadyExistsError` (409), so the owner sees "already exists" for a binding that does not exist.
- **Evidence:** `src/pocketquant/core/infra/persistence/repositories/subscription_repository.py:19-27` (DuplicateKeyError→409), `:71-84` (old `ensure_indexes` creates only `ix_subscriptions_dedup_triple`).
- **Suggested fix:** Add a rollback step 0: `db.subscriptions.drop_index("ix_subscriptions_dedup_intervals")` when present, as an [ASK] together with the delete.

## Finding 8: Re-placing the stop on every bar makes order lifecycle logs per-bar INFO in live
- **Severity:** Medium
- **Location:** Phase 09, Task 09.2 step 5 (`cancel` logs INFO `order_cancelled`); Phase 14, Rules ("sent again each bar while the setup holds").
- **Flaw:** Phase 09 treats a cancel as a low-frequency per-trade event. Phase 14 turns it into a per-bar event. While a setup holds, each live entry bar logs INFO `order_cancelled`, INFO `order_submitted` and INFO `live.signal_latency`. CLAUDE.md says a per-bar event must be DEBUG. In backtests these lines are dropped (`drop_backtest_info`), so only prod is affected and no test notices.
- **Failure scenario:** With several stop-mode subscriptions, prod INFO volume grows with bars × subscriptions. This is the "scales with market activity" pattern CLAUDE.md forbids. No gate catches it.
- **Evidence:** `src/pocketquant/engine/execution/order_app_service.py:89-94` (INFO `order_submitted`); `src/pocketquant/engine/strategy/strategy_app_service.py:605-626` (INFO `live.signal_latency`); `src/pocketquant/core/common/logging/setup.py:36-42` (backtest INFO dropped).
- **Suggested fix:** Log a cancel caused by a re-placement at DEBUG. Keep INFO only for a manual cancel or an EXIT cancel. Log the submit of a re-placed stop at DEBUG, for example by passing a flag from `_process_signal` or logging the replace once.

## Finding 9: The Phase 10 doc bullet has its own Verify pasted into it, and the Verify then matches the garbage
- **Severity:** Medium
- **Location:** Phase 10, Task 10.5 step 2.
- **Flaw:** The bullet text reads `"- An **Verify:** \`grep -c -E "Exness pending stop|..." docs/system-architecture.md\` prints a number of at least \`2\`. fill is linked to its order by the deal field ..."`. A weaker executor will write it into the doc literally. The Verify grep counts the string `Exness pending stop` inside that pasted text, so it passes on the corrupted bullet. Separately, Task 10.1 says "Write six lines" but lists, and the Verify counts, seven keys.
- **Failure scenario:** `docs/system-architecture.md` (48 lines, Limitations at `:30`) gains a corrupted Limitations bullet. That is the bullet a reader must check before arming live trading (R4, R5). The phase still passes.
- **Evidence:** `docs/system-architecture.md:30` (`## Limitations`); plan text at `phase-10-exness-close-pending-cancel.md` Task 10.5 step 2.
- **Suggested fix:** Restore the intended text: "- An Exness pending-stop fill is linked to its order by the deal field `<link_field>` (from the venue spec)." Make the Verify grep a phrase only the real bullets contain, for example `linked to its order by the deal field|names no field that links`.

## Scope audit: new state, lifetimes, leaks

| State (phase) | Instantiation sites | Lifetime | Leak or crossing |
|---|---|---|---|
| `StrategyAppService._context` (07) | the live engine (DI, one per process); one per backtest sandbox (`build_backtest_sandbox`, one per run) | process (trader) / run | No eviction on unload or symbol delete. Inference: a symbol deleted and re-added inside one window serves bars from the deleted data until rollover. Low impact. |
| `_snapshots` ring (11) | same engines | process / run | Warm-up records share the live ring (Finding 4). Popped on unload. The Redis key outlives a DELETE for 7 days; no reader lists it. |
| `PaperBrokerAdapter._resting` (09) | one per pooled paper broker, keyed `(paper, ContractSpec)` (`strategy_app_service.py:83-86,661-678`), so it is shared across subscriptions | process | Restored wholesale at takeover. Dropped per subscription on unload. Consistent. |
| `OrderAppService._pending` stop entries (09) | one per engine | process | Mirrors `_resting`. Desyncs from the strategy's `_armed` (Finding 3). |
| `ExnessBrokerAdapter._parked` (10) | one per Exness broker | process | Not re-adopted after a restart. This is stated (R5), and live stays disarmed. |
| `Subscription.manual_action` (11) | Mongo document | persistent, api→trader | The correct cross-process channel. Only the lease holder applies it. |
| `_Recorder.runs` class list (08) | test module | pytest process | The Phase 07 tests append to it too. Reset in one test only. Harmless. |
| `probe_registry` (05) | `monkeypatch.setitem` per test | test | Restored per test. Safe with the function-scoped `app_client` (`tests/app_test/integration/conftest.py:14`). |
| Phase 07 `bars` fixture drops `COLLECTION_BARS` | session Mongo container (`tests/conftest.py:64-75`) | session | It drops at the start and leaves its seeds behind. Later tests that seed BTCUSDT:BINANCE delete per interval first (`test_backtest_single_run_direct_task.py:95-98`), so there is no collision today. Inference: order-dependent. |

Status: DONE_WITH_CONCERNS
Summary: Nine findings. Three are High: a cross-phase snapshot and order key mismatch with C7, a Phase 06 Verify that cannot pass, and Triple Screen losing its stop and position state across skips and restarts. Every finding is backed by grep or read evidence on `e4a998b8`.
Concerns: Finding 5's cost figures are computed from code constants, not measured. Finding 6 depends on prod coverage I did not query.
