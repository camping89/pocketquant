# Phase 02 report: Spike B, money path and UI

S5-S10 are `go`. The stop-rule rows S2, S3, S5, S6 and S10 are all `go`, so no stop-rule [ASK] was needed. S4 stays `no-go`, and the owner chose to fix it in Phase 08. The spike worktree and branch are deleted; only the reports reach `develop`.

## Facts

- Entry gate: `dirty=0 synced=yes`, `Result: PASS`, `spike/mtf`, `4`, `docker-ok`.
- Spike base: `../pocketquant-spike` on `spike/mtf` at `1430946b`, with the Phase 01 diff still in place. Phase 02 added rough code on top and new tests under `tests/spike_test/`. Nothing was committed, cherry-picked or copied from it.
- Exness spec read on 2026-11-01 from `https://www.exness-api.com/exness_api.yaml` into `.cache/exness_api.yaml` (4503 lines; data only, never executed). The facts are in `spike-go-no-go.md` under `## Exness spec`.
- Worktree removed with `git worktree remove --force ../pocketquant-spike`; branch deleted (`Deleted branch spike/mtf (was 1430946b)`).

## Verify outputs (Tasks 02.1-02.6)

```
02.1: 2 passed, 2 warnings in 5.06s
02.2: 10 passed, 1 warning in 0.06s
02.3: 2 passed, 2 warnings in 5.12s
02.4 first run:
1 passed, 4 warnings in 6.05s
      2 src/components/monitor/job-status-palette.ts
      1 src/main.tsx
      1 src/routes/backtest.{-$runId}.{-$tab}.tsx
      1 src/routes/backtest_.compare.tsx
      2 src/routes/index.tsx
      1 src/routes/monitor.tsx
      1 src/routes/monitor_.jobs.$jobId.tsx
      1 src/routes/strategies.tsx
build=0
02.4 second run:
1 passed, 4 warnings in 5.14s
      2 src/components/monitor/job-status-palette.ts
build=0
02.5 first run (before the spec section was written): spec=0 tests=3 passed, 1 warning in 0.14s
02.5: spec=5 tests=3 passed, 1 warning in 0.11s
02.6: rows=10 stop_rule_go=5
```

All spike tests together: `25 passed`. After the phase checkpoint one S8 test was added (`test_a_manual_close_waits_for_the_lease`); the S8 file then reported `3 passed`.

## Go/no-go table

Copied from `spike-go-no-go.md`.


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


## [ASK] and owner answer

No stop-rule row was `no-go`. S4 was carried to this phase as an owner decision, so it was asked through the coordinator in Vietnamese:

> Phase 02 (spike B): S4 backtest cost là no-go từ Phase 01 và được ghi 'owner decision tại Phase 02'. Số đo: t_mtf_s=9.57 so với t_stf_s=1.17 (giới hạn 2x = 2.34 s); số lần find 900 <= 902 đạt. [...] Đề xuất: Phase 08 (backtest sandbox) tự prefetch mỗi context interval một lần và cắt trong bộ nhớ như warm-up đã làm, giữ nguyên giới hạn 2x và thêm test thời gian đó vào Phase 08. Chủ sở hữu chọn phương án nào?

Answer: "A: Phase 08 prefetch + in-memory slice, giữ giới hạn 2x (owner chọn: Sửa ở Phase 08)."

## Advisory counsel

- The first S9 Verify run missed its pass condition (9 extra tsc errors). `kongming` reproduced the cause: `web/src/routeTree.gen.ts` is gitignored and generated by `vite build`, and without it `tsc -b` reports exactly those errors. Its advice was to re-run the Verify command unchanged, which then passed, and to record the ordering trap for Phase 04.
- Phase checkpoint before the irreversible Task 02.7: `kongming` said go. It found that every `go` row is backed by a test that fails when the behaviour breaks, except the S8 lease fence, which had no test. That test was added and passes. It also listed traps visible only in the spike diff; they are in `spike-go-no-go.md`.
- Next risk it named for Phase 03 (its inference, not checked here): on session calendars the cascade 1d bar and the Exness REST 1d bar may differ by a few ticks, so the two writers could flip OHLCV and `source` on the same day. A read-only prod count of 1d rows whose `source` changed twice in a day would show it.

## Traps found

See `spike-go-no-go.md` `## Traps found`, lines marked `Phase 02`. The main ones: `on_order_update` for every broker needs the `PENDING` early return; any entry against an open position must be rejected for the re-placed stop to work; EXIT is checked after the balance check; the resting stop is cancelled before the risk check; the backtest path never subscribes `on_order_update`; `take_over` cancels pending orders only in Mongo; the snapshot ring restarts empty after a handover; the web gate must generate the route tree before `tsc -b`.

## Deviations

- S9's red step failed on `StrategyAppService.__init__() got an unexpected keyword argument 'cache'`, not on `404`.
- The live EXIT test builds `StrategyAppService` directly with a started `PositionAppService`, not through the backtest sandbox. Through the sandbox, the "no open position" assertion would pass trivially before the change.
- Spike tests read private state (`broker._resting`, `repo._collection()`), which is acceptable only in throwaway code.

## Unresolved questions

- None for this phase. S4 now belongs to Phase 08 with the 2x bound kept.

Result: PASS
