---
title: "Live paper broker checks SL/TP against every interval's bars"
date: 2026-10-24
status: diagnosed, not fixed
plan: plans/archive/260921-1436-asset-class-index-futures (found while measuring G2 in Phase 9)
counsel: plans/reports/kongming-261024-0412-g2-paper-sl-interval-mixing.md
---

# Live paper broker checks SL/TP against every interval's bars

## Summary

The live paper broker closes positions on stop-loss and take-profit levels that the price
never reached after entry. `PaperBrokerAdapter._on_bar_completed` checks every open position
of a symbol against every `BarCompletedEvent` for that symbol, whatever its interval. The live
bar builder publishes one event per interval (1m, 5m, 15m, 1h, 4h, 1d, 1w). So a position
opened inside a 4h bar is checked against that 4h bar's full high and low when it closes, and
that range includes prices from before the entry.

In the G2 session, 2 of 4 exits came from this. Diagnosed read-only; no code changed.

## Impact

Facts:

- Paper subscription `01a16440-fdc8-745c-8a9e-7c2b6223de0d` (`engulfing`, 15m, ES1!:TRADINGVIEW)
  closed 4 trades on 2026-10-23. Trade 1 (stop) and trade 4 (target) were triggered by prices no
  1m bar after entry reached. Trade 4 was the session's only winner (+1,174.18 USD).
- The stored `pnl` of every trade is still arithmetically right:
  `(exit - entry) x 50 x contracts`, signed by side. Only the exit trigger is wrong.

Inference (not measured):

- Every live paper subscription is affected, crypto included. A 1m position is checked
  against the 5m-1w bars too, so it is hit more often than a 15m one. Live paper results so
  far are not trustworthy.
- Backtests are not affected: historical replay publishes only the configured interval
  (`src/pocketquant/engine/backtest/historical_replay_app_service.py:74-77`). This is from
  reading the code, not from running a backtest.
- Exness live orders are not affected: SL/TP are sent to the venue in the order body
  (`src/pocketquant/core/infra/brokers/exness/exness_broker_adapter.py:239-242`), and that
  adapter has no `BarCompletedEvent` handler.

## Evidence

Trades in Mongo `trades`, `run_id = 01a16440-fdc8-745c-8a9e-7c2b6223de0d`, all quantity 1.
Times are UTC, 2026-10-23. Prod slippage is 0.5 bps, so a synthetic exit fills at the trigger
price x (1 +/- 0.00005).

| # | Side | Entry | Exit | SL | TP | pnl (USD) | Commission |
|---|---|---|---|---|---|---|---|
| 1 | SHORT | 02:11:16.257 @ 7690.8654 | 02:11:16.293 @ 7711.8393 | 7711.4537 | 7671.0463 | -1048.69 | 4.62 |
| 2 | LONG | 06:25:16 @ 7701.1350 | 10:12:42 @ 7683.9238 | 7684.3080 | 7717.1920 | -860.56 | 4.62 |
| 3 | LONG | 11:55:29 @ 7688.1344 | 12:42:43 @ 7673.6845 | 7674.0683 | 7711.2500 | -722.49 | 4.61 |
| 4 | SHORT | 17:10:57 @ 7675.1162 | 18:10:18 @ 7651.6326 | 7696.4387 | 7651.2500 | +1174.18 | 4.60 |

Trade ids: `01a16686-dac5-764d-b9f8-ce858a138e42`, `01a1683f-9dd2-73f8-be7d-0b05900f30e5`,
`01a168c8-f994-7678-8f5c-af6329d43de6`, `01a169f4-e070-7791-ae02-dda068ea0891`.

A fifth position, SHORT opened 18:55:32, was still open when the CME session closed at
21:00Z.

Stored 1m bars from 15 minutes before each entry (the free feed is about 10 minutes behind)
to the exit, against the 4h bar that closed at the exit:

| # | Level hit | 1m range in window | Reached on 1m? | 4h bar at exit |
|---|---|---|---|---|
| 1 | SL 7711.45 (high) | 7687.75 - 7694.00 | No | 22:00-02:00, high 7714.25 |
| 2 | SL 7684.31 (low) | 7681.00 - 7712.25 | Yes | 06:00-10:00, low 7684.25 |
| 3 | SL 7674.07 (low) | 7667.50 - 7690.00 | Yes | not a 4h close (12:30) |
| 4 | TP 7651.25 (low) | 7661.50 - 7679.25 | No | 14:00-18:00, low 7648.50 |

Trade 1 exited 36 ms after it opened. No price after entry existed yet, so a completed
higher-interval bar is the only possible trigger.

## Root cause

- `PaperBrokerAdapter._on_bar_completed` filters positions only by
  `pos.symbol != event.symbol`, with no interval check
  (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:697-706`).
  `_check_sl_tp` compares the whole bar's high and low with SL, then TP (`:777-792`).
- The broker subscribes to every `BarCompletedEvent` (`:171`).
- `BarAppService` builds bars for seven intervals per tick and publishes one event per
  completed bar, with its `interval` (`src/pocketquant/engine/market_data/app_services/bar_app_service.py:28-36, 151-162`).
- `StrategyAppService` does filter by the strategy's interval
  (`src/pocketquant/engine/strategy/strategy_app_service.py:240, 352`). The broker does not.

## Fix options (for the follow-up plan; not decided)

1. Skip positions opened after the bar started (`opened_at > event.bar_start`). One line, and
   backtests are unchanged. Live `opened_at` is wall-clock time while `bar_start` is delayed
   venue time, so for about the feed delay after entry no bar would be checked (inference).
2. Carry the subscription interval from signal to order to position, and check only bars of
   that interval. Exact, and the same semantics as backtests. The most code: a new field on
   `OrderAggregate` and `PositionAggregate`.
3. Check only the finest interval the broker has seen for that symbol. Backtests are
   unchanged. Live resolves at 1m, which is finer than backtests, so SL and TP inside one bar
   resolve in order rather than "SL wins". Small state, implicit rule.

The follow-up plan should also carry the daily 04:00 stall
(`plans/reports/debug-261023-0045-daily-0400-integrity-event-loop-stall.md`). This defect
matters more: it makes paper results untrustworthy, while the stall costs about seven minutes a
day.

## Related findings

- **Commission is a data gap, not a code bug.** The ES symbol document has
  `commission_per_contract: null`, so the paper broker falls back to 3 bps of the unmultiplied
  price, about 2.31 USD per side at 7,700 (`src/pocketquant/core/domain/trading/commission_model.py:12-13`,
  `src/pocketquant/core/infra/brokers/broker_factory.py:52-55`). The number is realistic by
  coincidence. The fix is to set `commission_per_contract` on the three futures documents.
- **Latent: the signal bar is checked against the position it just opened**
  (`paper_broker_adapter.py:685-690`). With `sl_buffer_pct = 0`, engulfing's stop equals the
  pattern extreme and would fire on entry. Prod's 0.1 % buffer avoided it here.

## Unresolved questions

- Which fix option should the follow-up plan take?
- How far back are live paper results affected? Every live paper subscription since this
  handler shipped, but that date is not traced here.

## Prod verification after the fix

- 2026-10-28: ES SHORT on subscription 01a178ef (entry 2026-10-27T12:55:13Z at 7739.8630, SL 7753.2455, TP 7703) closed by SL at 15:13:48Z at 7754.8877 (7754.50 x 1.00005), pnl -751.24, commission 4.65. The exit came on a 1m event: no 1m bar touched SL before the 15:00 bar, no 5m-1w bar drove it, and the signal-bar rule held. The pnl matches. The fill is 5 ticks worse than the stored REST 1m bars imply (7753.63), because the live 1m bar differs from the stored bar. The TradingView poller (`tradingview_quote_adapter.py`) emits only the vendor close once per 60 s (`poll_s=60`; a live 1m bar showed `tick_count` 1, O=H=L=C), so live 1m highs and lows under-report. The open is a sampled close, which the gap rule then fills at. The broker logic is correct on its input; the fidelity gap is in the feed.
