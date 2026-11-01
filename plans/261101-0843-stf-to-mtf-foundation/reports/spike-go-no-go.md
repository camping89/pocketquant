# Spike go/no-go

## Measurements

Run at 2026-11-01T13:11:46Z (UTC), read-only PRODPY script over the last 72 h of `source: cascade` bars on every `:EXNESS` tracked symbol. Lag is `updated_at - (datetime + step)` in seconds, for buckets that ended at least 5 minutes before the run.

This lag is evidence only. It sets no constant and gates nothing (synthesis D1).

```
lag BTCUSD:EXNESS 5m n=862 p50_s=17.6 p99_s=21.1 max_s=617.5 share_le_40s=0.994
lag BTCUSD:EXNESS 15m n=287 p50_s=17.7 p99_s=138.5 max_s=317.5 share_le_40s=0.990
lag BTCUSD:EXNESS 1h n=71 p50_s=18.0 p99_s=257.5 max_s=257.5 share_le_40s=0.972
lag BTCUSD:EXNESS 4h n=17 p50_s=18.3 p99_s=138.5 max_s=138.5 share_le_40s=0.941
lag EURUSD:EXNESS 5m n=378 p50_s=19.0 p99_s=21.9 max_s=23.0 share_le_40s=1.000
lag EURUSD:EXNESS 15m n=127 p50_s=19.1 p99_s=22.3 max_s=23.1 share_le_40s=1.000
lag EURUSD:EXNESS 1h n=31 p50_s=19.2 p99_s=23.1 max_s=23.1 share_le_40s=1.000
lag EURUSD:EXNESS 4h n=8 p50_s=19.5 p99_s=23.1 max_s=23.1 share_le_40s=1.000
lag XAUUSD:EXNESS 5m n=369 p50_s=19.6 p99_s=22.6 max_s=23.9 share_le_40s=1.000
lag XAUUSD:EXNESS 15m n=123 p50_s=19.6 p99_s=22.8 max_s=24.0 share_le_40s=1.000
lag XAUUSD:EXNESS 1h n=30 p50_s=19.9 p99_s=24.0 max_s=24.0 share_le_40s=1.000
lag XAUUSD:EXNESS 4h n=8 p50_s=20.1 p99_s=24.0 max_s=24.0 share_le_40s=1.000
```

## Go/no-go

| piece | go/no-go | evidence | carried to phase |
|---|---|---|---|
| S1 subscription key | go | `test_two_interval_sets_sharing_the_entry_interval_both_insert`: POST `["15m","1h"]` and `["15m","4h"]` for `probe` on `BTCUSDT:BINANCE` both return 201. `test_a_repeated_interval_set_is_a_conflict`: a second `["15m","1h"]` returns 409 from `DuplicateKeyError` on the unique index `ix_subscriptions_dedup_intervals` over `(strategy_code, symbol, intervals_key)`. Verify: `2 passed`. | 06 |
| S2 context in live, warm-up, backtest | go | Seed: 1m bars 2026-01-05 00:30-01:59, 1h bars 2026-01-04 23:00, 2026-01-05 00:00 and a partial 01:00. `test_live_first_entry_bar_of_an_hour_sees_the_previous_hour`: entry bars 00:59 and 01:00 see last 1h bars 23:00 and 00:00. `test_warm_up_contexts_match_the_live_rule`: start at 01:31:25, 61 replayed bars (00:30-01:30), each sees `floor_hour(t) - 1h`, never 01:00. `test_backtest_contexts_match_the_live_rule`: 90 bars (00:30-01:59), each sees `floor_hour(t) - 1h`. Verify: `4 passed` (with S3). | 07, 08 |
| S3 one read per rollover | go | `test_context_reads_once_per_rollover`: live entry bars 00:58-01:02 make exactly 2 `BarRepository.find` calls for `1h` (two windows). | 07 |
| S4 backtest cost | no-go | `spike_cost find_calls=900 rollovers=900 t_mtf_s=9.57 t_stf_s=1.17`. The find bound (`<= 902`) is met. The time bound (`t_mtf_s <= 2 * t_stf_s`) is missed by about 8x. Owner decision at Phase 02: fix in Phase 08 with a backtest-side prefetch and in-memory slice, keeping the 2x bound (see `## Owner answers`). | 08 |
| S5 paper EXIT live | go | `test_an_exit_signal_closes_the_paper_position`: a probe sends LONG (SL 50, TP 500) on bar 1, nothing on bar 2, `Direction.EXIT` on bar 3, on a live engine with a started `PositionAppService`. After bar 1 the tracker holds the position; after bar 3 it holds none, exactly one `TradeClosedEvent` was published, and the broker's exit order event carries reason `strategy_exit`. Red first: `Unsupported signal direction: exit`. Verify (with S6): `2 passed`. | 09 |
| S6 paper EXIT backtest | go | `test_an_exit_signal_closes_the_position_in_a_backtest`: `BacktestExecutionService.run` over the same three bars finishes with `total_trades == 1` (red first: `0 == 1`, the position stayed open). It needs the sandbox to start the position tracker, or the risk check never sees the position. | 08, 09 |
| S7 resting stop | go | `test_spike_stop.py`, spread 0, slippage 0: a LONG stop at 101 rests as `submitted` and the placing bar never fills it; the next bar (open 100.8, high 101.2) fills it at 101 with one `OrderFilledEvent`; a gap open at 102 fills at 102; a new signal leaves the old order `cancelled` and one resting order; a stop re-placed every bar (101.0, 101.1, 101.2) fills at 101.1 on bar 3 before the probe decides, the bar-3 signal is rejected with `position open`, and no order rests; `stop_strategy`, `unload_strategy` and engine `stop(5)` each leave the order `cancelled` and a later touching bar fills nothing; `take_over()` cancels a stored `submitted` stop, restores none, and the probe's next signal places a new one; with `trading_until = None` a touching bar fills nothing; a market LONG with `on_order_update` subscribed publishes exactly one fill (removing the PENDING early return makes it 0). Verify: `10 passed`. | 09 |
| S8 manual action | go | `test_spike_manual_action.py` on the test Mongo: a running paper subscription loaded by the reconcile loop; `manual_action="close"` written on its document; one `_reconcile()` closes the position (order event reason `manual_close`) and the stored `manual_action` is `None`. `"cancel"` cancels the resting stop (`cancelled`, broker holds none) and clears the field. Verify: `2 passed`. Added after the phase checkpoint: `test_a_manual_close_waits_for_the_lease` sets `trading_until = None`; after one tick the position is still open and the stored value is still `"close"` (the file then reports `3 passed`). | 11 |
| S9 snapshot to UI | go | `test_the_snapshot_ring_is_served_after_two_live_bars`: an engine with a real `Cache` (redis container) runs two live bars of a probe that sets `snapshot`; `GET /api/v1/subscriptions/{id}/snapshot` through `app_client` returns 2 entries with different `bar_start`, each with `readings` and `decision`. The card polls every 5 s and renders the raw JSON. Verify (second run): `1 passed`, `2 src/components/monitor/job-status-palette.ts`, `build=0`. The first run showed 9 extra tsc errors from the missing generated `routeTree.gen.ts` (see Traps). | 11, 13 |
| S10 Exness spec and fence | go | All three operations are in the spec (see `## Exness spec`). `test_placing_a_pending_order_needs_the_live_flag`: `LIVE_TRADING_DISABLED` and no request sent. `test_closing_a_position_is_sent_while_the_live_flag_is_off`: one `DELETE /v1/trading/accounts/1/positions/777`. `test_cancelling_a_pending_order_is_sent_while_the_live_flag_is_off`: one `DELETE /v1/trading/accounts/1/orders/555`. Red first: `KeyError` for all three ops. Verify: `3 passed`. | 10 |

### S4 diagnosis

- With the context read limit at 500, 100 and 40 bars, `t_mtf_s` was 9.53, 5.08 and 4.24 against `t_stf_s` of about 1.1 (local Docker Mongo).
- A cProfile of the 500-bar MTF run attributes 8.6 s of 9.6 s to `_context_for`, 7.6 s to `BarRepository.find`, and 4.9 s to 294,740 `Bar.from_mongo` calls. Each rollover re-reads and re-parses the whole window.
- Per rollover the overhead is about 9.3, 4.3 and 3.4 ms for the three limits. The bound allows about 1.3 ms per rollover (1.17 s / 900). Inference (kongming counsel): the floor of about 3 ms is the cost of one Mongo `find` round trip, so any design with one read per rollover misses this bound. An incremental-append variant was not measured, because it still reads once per rollover.
- The probe does no work, so the STF baseline is close to the bare replay cost. This makes the ratio as harsh as it can be.
- The remedy, for example a backtest-side prefetch and in-memory slice as warm-up already does, or a different bound, is the owner's decision at Phase 02.

## Exness spec

Read from `https://www.exness-api.com/exness_api.yaml` on 2026-11-01 (4503 lines, saved to `.cache/exness_api.yaml`). Line numbers refer to that file.

- `placePendingOrder`: `POST /v1/trading/accounts/{account_id}/orders` (path line 397, method line 398, operationId line 457). Order types listed: `limit`, `stop` and `sltp` (lines 404-406); market orders are not accepted. Unavailable when `trade_mode` is `trading_disabled` (line 412) and when `account_status` is `close_only`, except for SLTP orders (line 413). Errors include `MARKET_SESSION_CLOSED` and `MARKET_NO_QUOTES` (lines 440-441).
- `cancelPendingOrder`: `DELETE /v1/trading/accounts/{account_id}/orders/{order_id}` (path line 526, method line 626, operationId line 650), summary "Cancel pending or SLTP order". Unavailable only when `trade_mode` is `trading_disabled` (line 634).
- `closePosition`: `DELETE /v1/trading/accounts/{account_id}/positions/{position_id}` (path line 830, method line 831, operationId line 866). Unavailable only when `trade_mode` is `trading_disabled` (line 839). Errors include `MARKET_SESSION_CLOSED` and `MARKET_NO_QUOTES` (lines 888-889).
- `close_only` means "only closing positions and cancelling orders is allowed" (line 2861). `trading_disabled` disables trading operations (line 2889). So `trade_mode=trading_disabled` is the mode that makes close and cancel unavailable.
- Fill link: "deal-to-order relation is exposed through `deal.order_id`, when applicable" (line 1333, in the `getDealsHistory` description). Error codes: 4003 `MARKET_SESSION_CLOSED`, 4004 `MARKET_NO_QUOTES` (lines 2647-2648).

## Traps found

- The red step did not fail with `KeyError: 'context'` first. It failed on `build_backtest_sandbox()` taking no arguments and on `KeyError: 'interval'` in `_config_from_dict`, because a payload with only `intervals` has no `interval`.
- `Subscription.interval` is still read by `strategy_reconcile_app_service.py:149` and `strategy_query_service.py:49`. The spike kept a property `interval = intervals[0]`. The reconcile service also builds `StrategyConfig` without `intervals`, so the real live path would hand strategies an empty context until it passes them.
- The old unique index `ix_subscriptions_dedup_triple` covers `interval`. New documents carry no `interval`, so two of them would collide on null under the old index. It must be dropped before new documents land, as the prod migration verdict says.
- `BarRepository.find(end_date=instant)` uses `$lte`, so the read returns the partial current bucket. The closed filter must remove it, and the tests seed a partial 01:00 1h bar to catch that.
- The spike cache filters the window's bars at `window_start`, not at `instant`. This is the same on the 24/7 grid the tests use. It was not checked for Exness session calendars, so the build should filter at `instant` per the verdict and use the window only as the cache key.
- The spike cache is `(window_start, bars)` with no `complete` flag. Prod BTCUSD cascade lag reaches p99 257.5 s on 1h, longer than a 1m entry bar, so the verdict's re-query on a miss will read more than once per rollover. That needs its own test; the S3 test asserts exactly 2 reads.
- The governance rule says a higher bar may be read once it closed by the close of the decided bar. The verdict uses the decided bar's start, which is stricter by one entry bar at each rollover (the 00:59 1m bar does not see the 00:00 1h bar). This is safe against look-ahead and matches the measured lag of about 18-20 s.
- All three paths ran through `build_backtest_sandbox`; the real live wiring (dishka engine and reconcile loop) was not exercised.
- cProfile counts each coroutine resumption as a call, so `ncalls` for coroutines is inflated; only `tottime` and `cumtime` were used.
- Phase 02: `on_order_update` subscribed for every broker needs its early return on a stored order still `PENDING`. Without it, a market fill raises `PENDING -> FILLED` inside `submit_order`, the order is rejected and no fill is published (the S7 market test shows 0 fills).
- Phase 02: the risk check let a same-side entry through up to the exposure cap. The S7 re-placed stop needs any entry against an open position rejected (`position open`). `tests/engine_test/test_risk_check.py::test_a_same_side_entry_still_reaches_the_exposure_check` and the EXIT rejection case fail on that change; the build rewrites them.
- Phase 02: subscribing `on_order_update` for paper breaks `test_async_broker_fill_wiring.py::test_paper_broker_is_not_subscribed_to_order_updates` and 7 tests in `test_contract_spec_wiring.py`, whose `_RecordingOrderService` double has no `on_order_update`.
- Phase 02: the backtest path uses `inject_prepared_strategy`, which never subscribes `on_order_update`. A resting stop filled in a backtest would reach the broker's position but publish no `OrderFilledEvent`, so the tracker and the strategy would not see it. Phase 09 must wire it for the sandbox broker too.
- Phase 02: `take_over` cancels every stored pending order. Only paper stops exist today; once Exness pending orders exist (Phase 10) a takeover must cancel them at the venue, not only in Mongo.
- Phase 02: a stop fill skips the `_can_afford` check that market fills pass. The build should check balance at fill time.
- Phase 02: the spike sizes a stop entry at its stop price (`entry_price`), not at the bar close.
- Phase 02: a manual action runs only while the engine holds the lease (`trading_until` in the future); otherwise the stored value stays for the lease holder. The reconcile loop reads it each tick, so a value that keeps failing is retried every 5 s and logged each time.
- Phase 02: `close_position` on paper prices the exit at the last bar close the broker saw (`_current_prices`), set by the broker's own bar handler after strategies run.
- Phase 02: `cancel_resting` emits no `OrderCancelledEvent`, so the strategy is not told its replaced stop was cancelled. A stop cancelled by the engine on stop, unload or takeover is also silent.
- Phase 02: the web gate on a fresh checkout must generate `web/src/routeTree.gen.ts` (gitignored, generated by `TanStackRouterVite` during `vite build`) before `tsc -b`. Without it `tsc -b` reports 9 extra errors in `main.tsx` and `routes/*`; kongming reproduced this by deleting and restoring the file. `npm run build` is `tsc -b && vite build`, so a clean CI clone has the same exposure.
- Phase 02: `_PRIORITY_OPS` is `_ORDER_OPS | {"getOperationStatus"}`, so `closePosition` and `cancelPendingOrder` are not priority-paced. Phase 10 should decide whether exposure-reducing calls get priority.
- Phase 02: `placePendingOrder` also lists `sltp` as an order type; the fence covers it because the fence is per operation.
- Phase 02: the risk check tests the balance before the EXIT branch, so a position whose available balance is at or below 0 cannot be exited by signal, which is when an exit matters most. The build must validate EXIT before any balance or equity check.
- Phase 02: `_process_signal` cancels the resting stop before the risk check. A replacement signal that the risk check rejects leaves the subscription with no stop. Phase 09 decides the order of validate, cancel and place.
- Phase 02: `manual_action` reports success and the field is cleared when the subscription is not loaded in the engine. For paper this is harmless, because unload drops the position. For a stopped Exness subscription that still holds a venue position, a manual close would be dropped silently. Phase 11 must send the close to the venue or reject it visibly.
- Phase 02: the snapshot ring lives in process memory and `Cache.set` overwrites the Redis value with it. After a restart or handover the first bar writes a ring of one entry and the previous entries are lost. Phase 11 should seed the ring from Redis on start or append in Redis.
- Phase 02: `take_over` marks every stored pending order `cancelled` in Mongo with no broker call. This also covers a venue market order that the previous trader sent and the venue had not filled yet; its fill would land on an order the store calls cancelled. Phase 10 must reconcile with the venue before cancelling in Mongo.
- Phase 02: two "live only" rules are implicit. Snapshots are written only when the event has a `bar_end` (backtest events have none) and the sandbox passes no cache. Resting stops fill in a backtest only because the sandbox engine keeps the `datetime.max` default for `trading_until`. Phase 08 and 09 should make the sandbox trading mode explicit. The sandbox builder comment says the position tracker is deliberately not started; the spike starts it, so Phase 08 rewrites the comment and re-checks the cross-talk reason it gives.
- Phase 02, checked and not an issue: the `on_order_update` early return on a `PENDING` order does not drop Exness fills, because the Exness adapter holds a fill that arrives before `submit` records `SUBMITTED` and delivers it afterwards (kongming read of `exness_broker_adapter.py`). The early return therefore relies on every async broker doing that hand-off.

## Kept vs rewritten

- Kept: this report, the numbers above, the Exness spec facts, and the test scenarios as prose (S1-S10).
- Rewritten: all code and tests, including the Phase 02 EXIT path, resting stop, manual action, snapshot route, web card and Exness ops. Nothing from `spike/mtf` is cherry-picked, merged, checked out by path or copied into `develop`.

## Owner answers

- S4, asked through the coordinator on 2026-11-01 (question in Vietnamese). Answer: "A: Phase 08 prefetch + in-memory slice, giữ giới hạn 2x (owner chọn: Sửa ở Phase 08)." Meaning: Phase 08 prefetches each context interval once and slices in memory, as warm-up does, and keeps the `t_mtf_s <= 2 * t_stf_s` bound.
