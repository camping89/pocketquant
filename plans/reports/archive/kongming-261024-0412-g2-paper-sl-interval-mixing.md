---
title: "G2 verdict and the paper broker's higher-interval SL/TP defect"
date: 2026-10-24
status: advisory, read-only
plan: plans/archive/260921-1436-asset-class-index-futures (Phase 9 Task 3, Phase 10)
---

# G2 verdict and the paper broker's higher-interval SL/TP defect

## TL;DR

The diagnosis is sound and the code confirms it: the paper broker scans SL/TP on every
`BarCompletedEvent` for its symbol, and the live `BarAppService` emits one event per
interval (1m, 5m, 15m, 1h, 4h, 1d, 1w) from the same tick. Record G2 as **Pass on the
metric as written** (4 of 4 USD conversions exact) **with a recorded defect** (exit
triggers mix intervals), file the defect as a separate debug report, close and archive the
plan now. Deleting the subscription is safe for the evidence: the DELETE route drops only
the subscription document. The commission finding is a per-symbol data gap, not a code
bug; record it in one line.

## Verified facts (file:line)

- `PaperBrokerAdapter._on_bar_completed` filters positions by `pos.symbol != event.symbol`
  only; no interval check
  (`src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py:697-706`). The broker
  subscribes to every `BarCompletedEvent` on connect (`:171`).
- `_check_sl_tp` compares the full bar `high`/`low` to SL then TP (`:777-792`), and
  `_fire_synthetic_exit` fills at the trigger price plus slippage (`:801`). Trade 1's exit
  7711.8393 = 7711.4537 x (1 + 0.00005), i.e. an `auto_sl` fill at prod's 0.5 bps slippage
  (`core/config.py:145`). Trade 4's exit 7651.6326 = 7651.25 x 1.00005 is an `auto_tp`.
- The live bar builder runs seven intervals per tick in order 1m, 5m, 15m, 1h, 4h, 1d, 1w
  (`engine/market_data/app_services/bar_app_service.py:28-36,91-92`) and publishes one
  event per completed bar with its `interval` (`:151-162`). DI passes no interval list
  (`app/di/services.py:90-95`), so prod builds all seven.
- `StrategyAppService` filters events by `strategy.config.interval`
  (`engine/strategy/strategy_app_service.py:240,352`). The broker does not.
- Backtest emits only `config.interval` (`engine/backtest/historical_replay_app_service.py:74-77`),
  so backtests are not affected. Verified by reading the replay, not by running one.
- Paper brokers are pooled per `(broker_type, contract_spec)`
  (`strategy_app_service.py:463-467`): ES has its own instance; all LINEAR-spec paper
  subscriptions (BTCUSDT 1m, EURUSD 1h, ...) share one. The per-symbol filter keeps
  positions apart; the interval mixing hits every live paper subscription.
- Exness sends SL/TP to the venue in the order body
  (`core/infra/brokers/exness/exness_broker_adapter.py:239-242`) and has no
  `BarCompletedEvent` handler. Not affected.
- Subscription DELETE: `app/routes/strategy.py:144-150` -> `remove_symbol`
  (`engine/strategy/strategy_command_service.py:112-120`) -> `delete_one` on
  `subscriptions` (`core/infra/persistence/repositories/subscription_repository.py:78-82`).
  Nothing else is touched. The cascade in memory is the tracked-symbol removal
  (`engine/market_data/tracked_symbols_service.py:151-158`), which does delete `trades`
  and `positions` for the symbol.
- Trades reads do not look up the subscription doc: `GET .../trades` reads closed
  positions by subscription id (`engine/strategy/strategy_query_service.py:87-93`);
  `TradeRepository.list_by_subscription` reads `trades` by `run_id`
  (`core/infra/persistence/repositories/trade_repository.py:32-35`).
- Commission: `PercentageCommissionModel.compute = |price x qty| x bps / 10_000`
  (`core/domain/trading/commission_model.py:12-13`), no multiplier. The factory uses it
  only when `contract_spec.commission_per_contract` is None
  (`core/infra/brokers/broker_factory.py:52-55, :66`). The spec field is read from the
  tracked-symbol document (`core/domain/symbol/value_objects.py:44,71`), so it is data.
- Engulfing places SL at `pattern_high x (1 + sl_buffer_pct)` for SHORT and
  `pattern_low x (1 - sl_buffer_pct)` for LONG
  (`core/domain/strategy/services/engulfing_strategy_service.py:115,127`).

## 1. Diagnosis and a cheap confirmation

Sound. Trade 1 is proven by construction: the exit came 36 ms after the entry, so no
post-entry price existed; the only completed bar with `high >= 7711.45` at that tick is the
4h bar 22:00-02:00 (high 7714.25). The 1h bar (7709.25) would need a spread of 2.2 points;
prod spread is the constructor default 0.0 (`paper_broker_adapter.py:119,133`; the factory
passes none, `broker_factory.py:62-70`).

Timing pattern (inference, medium): all four entries land 10-11 min after a 15m boundary
(02:00, 06:15, 11:45, 17:00), consistent with the free feed's delayed venue timestamps.
Exits 1, 2 and 4 land 10-13 min after 02:00, 10:00 and 18:00, which are session-anchored
4h closes (22, 02, 06, 10, 14, 18). Exit 3 (12:30) is not an hourly boundary, so a 15m or
finer bar did that one.

Read-only check for trades 2-4 (Mongo `bars`, `ES1!:TRADINGVIEW`, interval `1m`):

- Trade 2 (LONG, SL 7684.308): min `low` of 1m bars with `bar_start` in [06:15, 09:59].
  If no 1m bar reaches 7684.308, the 4h bar 06:00-10:00 fired on its 06:00-06:15 range,
  before entry. Also read that 4h bar's `low`.
- Trade 4 (SHORT, TP 7651.25): min `low` of 1m bars in [17:00, 17:59]. If none reaches
  7651.25, the +1174 USD win came from the 4h bar 14:00-18:00's pre-entry range. The only
  profitable trade of the session may be the spurious one; worth knowing before quoting it.
- Trade 3 (LONG, SL 7674.068): min `low` of 1m bars in [11:45, 12:29]. Expected to touch;
  that exit is then valid at 1m granularity.

Use generous windows (entry wall-clock minus 15 min to exit wall-clock) if the delay
estimate is doubted. Logs cannot help: `bar_completed_event_published` is DEBUG
(`bar_app_service.py:172`), Docker keeps about 12 h, and no stored document records the
triggering interval.

## 2. G2 verdict

Record **Pass on the metric as written, with a defect**. The metric and the phase task
measure one property: stored `pnl == (exit - entry) x 50 x contracts`, signed by side. All
four match exactly; `commission` is stored separately (the task's "less commission" is
satisfied as `pnl - commission`; say so in the row, since the stored `pnl` is gross). The
exit validity is a different property, found by the session, and it belongs in the row as
a named defect with the report link, not as a Fail of the arithmetic. Calling G2 Fail would
misstate what failed; calling it Pass without the defect would hide it. Suggested row text:

> **Pass, with a defect found.** Session 2026-10-22T22:00Z to 10-23T21:00Z, subscription
> `01a16440...`, 4 closed trades, each `pnl` equal to `(exit - entry) x 50 x 1` to the
> cent; commission 4.60-4.62 USD per round trip stored separately. Defect: trade 1 exited
> 36 ms after entry on the 4h bar's pre-entry high; the paper broker checks SL/TP on every
> interval's bar (`paper_broker_adapter.py:697-706`). Report: `plans/reports/debug-...`.

## 3. Close now or stay open

Close now. The defect is in the paper broker's live exit semantics, which this plan never
touched (the handler is not futures-specific and hits the crypto 1m subscription harder: a
1m position is checked against 1d and 1w bars). The user's pattern for the 04:00 stall was
"separate plan later"; this is the same shape. Do:

1. Write `plans/reports/debug-261024-<hhmm>-paper-sl-tp-fires-on-higher-interval-bars.md`
   in the style of `debug-261023-0045-...`: summary, impact (facts vs inference), evidence
   (the four trades, the 4h bar highs/lows, the 1m check results), cause with file:line,
   fix options, no code change.
2. Phase 9 progress: the G2 measurement, the defect line, the report link.
3. `completion-report.md` addendum (Phase 10 Task 6): row 13 as above.
4. `plan.md` Session 12 or a short Session 13: G2 result, defect deferred to a follow-up
   plan alongside the 04:00 stall. Then Phase 10 Task 7 archive.

The follow-up plan should carry both deferred defects. Priority: this one above the
stall, because it makes every paper-trading result untrustworthy, while the stall costs
seven minutes a day.

Fix options for the follow-up (do not decide here; recorded so the plan starts informed):

- A. In `_on_bar_completed`, skip positions whose `opened_at > event.bar_start`. One line;
  backtest unchanged (`opened_at` is the signal bar's sim time,
  `historical_replay_app_service.py:72-77`). Cost: live `opened_at` is wall-clock while
  `bar_start` is delayed venue time, so stops are blind for about the feed delay after
  entry. Inference from the timing pattern above.
- B. Thread the subscription interval to the position (signal -> order -> position) and
  check only matching bars. Exact, same semantics as backtest; the most code (new field
  on `OrderAggregate` and `PositionAggregate` with one consumer, which CLAUDE.md
  discourages).
- C. Check only the finest interval the broker has seen for that symbol. Backtest sees
  one interval, so unchanged; live resolves at 1m, which is finer than backtest (SL and TP
  inside one 15m bar resolve in order instead of "SL wins", `:780`). Small state, implicit
  rule; needs an interval ordering.

Observation for the same follow-up: the broker checks the signal bar itself against the
position it just opened (`:685-690` documents this). With `sl_buffer_pct = 0`, engulfing's
SL equals the pattern extreme and `bar_high + spread >= sl` fires on entry. Trade 1's SL
over pattern high implies a 0.1 % buffer on prod, so it did not fire. Latent, both modes.

## 4. Deleting the subscription

Safe for `trades` and `positions`: the route deletes one `subscriptions` document and
nothing else. Both read paths work without the subscription document. Before deleting:

- Confirm no open position (`GET /subscriptions/{id}/positions`). An open paper position
  survives in broker RAM after the orphan unload
  (`engine/live/strategy_reconcile_app_service.py:201-221` unloads the strategy only) and
  would be checked and closed by later bars with no owner. ES closed Friday 21:00Z and
  reopens Sunday 2026-10-25T22:00Z, so there is no rush.
- Paste the four trade documents (ids, times, prices, SL/TP, pnl, commission) into the
  debug report. Git is the durable copy; Mongo is not backed up for this.
- Never remove `ES1!:TRADINGVIEW` from tracked symbols; that cascade does delete
  `trades` and `positions` (`tracked_symbols_service.py:151-158`).

## 5. The commission finding

Record it, one line, as a data gap: the ES tracked-symbol document has
`commission_per_contract: null`, so the factory falls back to 3 bps of the unmultiplied
price (about 2.31 USD per side at 7700). A multiplier-aware percent would charge about
115 USD per side, which is also wrong for futures; the right fix is to set
`commission_per_contract` on the three futures documents (CME convention,
`commission_model.py:16-23`), which is a data update, not code. Low severity: the current
number is in the realistic range by coincidence. Note that `_can_afford` uses price-unit
notional on purpose (`paper_broker_adapter.py:508`), so do not "fix" that with it.

## Assumptions

- The feed delay of about 10-11 min and the 4h-close alignment of exits 1, 2 and 4 is
  inferred from timestamps, not measured (medium). The 1m check in section 1 does not
  depend on it if the windows are widened.
- Prod `sl_buffer_pct` is about 0.001, inferred from SL / 15m high (medium). Irrelevant to
  the verdict.
- The crypto 1m paper subscription suffers the same defect (high): same handler, same
  event stream; not measured.

Status: DONE
Summary: Diagnosis confirmed at paper_broker_adapter.py:697-706 plus bar_app_service.py:28-36; record G2 as Pass-with-defect, file a debug report, close and archive now, delete the subscription after checking for an open position; commission is a per-symbol data gap.
