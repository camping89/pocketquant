---
title: "Evidence packet: paper broker SL/TP interval mixing and gap fills"
date: 2026-10-26
status: diagnosis confirmed, fix not chosen
---

# Evidence packet: paper broker SL/TP interval mixing and gap fills

Repo: `D:/w/_me/algotrading/pocketquant` (branch `develop`). Read `CLAUDE.md` for the code
rules. This packet is identical for every candidate.

## Task

Fix two confirmed defects in `src/pocketquant/core/infra/brokers/paper/paper_broker_adapter.py`.
The root causes below are confirmed. Do not re-derive them; plan the fix.

### Defect 1: SL/TP checked against bars of every interval

- `connect()` (line 167-172) subscribes `_on_bar_completed` to every `BarCompletedEvent`.
- `_on_bar_completed` (683-718) filters positions only by `pos.symbol != event.symbol`, then
  calls `_check_sl_tp(pos, event.high, event.low)` (777-792).
- Live: `BarAppService` builds 7 intervals per symbol (`_DEFAULT_INTERVALS`, 1m..1w,
  `src/pocketquant/engine/market_data/app_services/bar_app_service.py:28-36`) and publishes one
  `BarCompletedEvent` per completed bar with its `interval` (`:151-162`). On a tick that
  closes several intervals, the list order is 1m first.
- So a position opened inside a 4h bar is checked against that 4h bar's whole range, which
  includes prices from before the entry.
- Prod evidence (ES1!:TRADINGVIEW paper, 15m engulfing, 2026-10-23,
  `plans/reports/debug-261024-0423-paper-sl-tp-fires-on-higher-interval-bars.md`): trade 1
  exited on SL 36 ms after entry (4h 22:00-02:00 high 7714.25 vs SL 7711.45; no 1m bar after
  entry reached it); trade 4 exited on TP (4h 14:00-18:00 low 7648.5 vs TP 7651.25; 1m low
  after entry 7661.5).
- The same missing filter exists in `_fill_pending_on_bar` (720-775): a pending LIMIT is
  filled against any interval's bar range. Live LIMIT entries exist when a strategy's
  `orders.entry_type != "market"` (`strategy_app_service.py:436-441`).
- Related, latent: the bar that produced the entry signal is also checked against the
  position it just opened. The strategy handler runs first, the broker subscribes last
  (`connect`, line 170), so the signal bar's high/low (which predate the entry at its close)
  can close the position. Engulfing with `sl_buffer_pct = 0` would stop out on entry; prod
  uses 0.001.

### Defect 2: gap fills at the SL/TP price

- `_check_sl_tp` returns the SL or TP level itself as the trigger price; `_fire_synthetic_exit`
  (794-849) fills at `_apply_slippage(trigger_price, exit_side)`. The bar `open` is never read
  (only high/low are passed).
- Prod evidence: ES SHORT, SL 7680.92; the CME reopen 1m bar 2026-10-25 22:00Z opened at
  7690 (high 7698.5). Fill 7681.31 = 7680.92 x 1.00005 (0.5 bps slippage). A real stop fills
  near 7690: about 8.7 points x 50 = about 430 USD better than reality.
- A favorable gap past TP is also filled at TP, not at the better open.
- SHORT triggers use ask = bid + `self._spread` (`_check_sl_tp` 788-791); the fill price is
  the level itself, not level + spread.

## Context facts

- `BarCompletedEvent` (`src/pocketquant/core/domain/bar/events.py`): `symbol, interval,
  bar_start, open, high, low, close, volume, tick_count`.
- Backtest: `HistoricalReplayAppService` (`src/pocketquant/engine/backtest/historical_replay_app_service.py:63-84`)
  publishes only `config.interval`, and calls `set_simulation_time(bar_time)` with
  `bar_time = bar_start` before publishing. So in backtests `get_current_time()` equals the
  current bar's `bar_start`, and a position opened on a bar has `opened_at == bar_start`.
- Live: `get_current_time()` is wall-clock. The TradingView feed is about 10 minutes behind,
  so live `bar_start` values lag wall-clock by about 10+ minutes for futures; Binance lags
  little. `PositionAggregate.open(... opened_at=get_current_time())` (`_open_position`, 570-591).
- Backtests use the same `PaperBrokerAdapter`: built in
  `src/pocketquant/engine/backtest/backtest_sandbox_app_service.py:108-133` (also a
  placeholder at :153). Live paper is built in
  `src/pocketquant/core/infra/brokers/broker_factory.py:49-70`.
- Live pooling: one paper broker per `(broker_type, contract_spec)`
  (`strategy_app_service.py:463-485`), shared by every subscription with that spec. So one
  broker instance serves several symbols and intervals (for example BTCUSDT 1m and ETHUSDT 15m).
- `StrategyAppService._find_strategies` filters by the strategy's interval (`:340-358`); the
  broker does not.
- Orders carry `subscription_id, symbol, side, order_type, quantity, price, sl_price,
  tp_price`; no interval. `Interval` enum: `src/pocketquant/core/domain/shared/enums.py:17`.
  Interval seconds: `INTERVAL_SECONDS` (`src/pocketquant/core/domain/shared/value_objects.py`,
  also `src/pocketquant/core/common/constants.py:49`).
- Tests: `tests/core_test/infra/brokers/test_paper_broker_sl_tp_fill.py` (helper `_bar_event`
  sets `interval="1m"`, `bar_start=_T0`, `open=(high+low)/2`),
  `test_paper_broker_spread.py`, `paper_broker_commission_test.py`,
  `paper_broker_futures_accounting_test.py`, `tests/backtest_test/engine/test_paper_broker_*.py`,
  backtest strategy suites in `tests/backtest_test/engine/`. Baseline:
  `uv run pytest -q tests/core_test/infra/brokers` = 113 passed.

## Constraints

- CLAUDE.md code rules: KISS; a flow reads in one file; a new class, port, helper, parameter,
  flag or config key needs a second real caller today; delete dead code; prefer one readable
  function; "when a change needs more code than the code it replaces, stop and ask".
- No change to the Exness broker (venue-side SL/TP) or to persistence schemas unless the
  plan argues it is required.
- Backtest results should stay identical for bars that do not gap past SL/TP, unless the
  plan names and justifies a deliberate change (for example the signal-bar check).
- Live paper must close a position only on prices that occur after its entry.
- English code comments, short. Conventional commits. Tests must not be weakened.

## Acceptance criteria

1. Regression test: with one broker receiving a 1m stream and a coarser (for example 4h)
   bar whose range predates the entry, the position is not closed by the coarser bar; it is
   closed by a later 1m bar that crosses the level.
2. Regression tests: a bar whose open is already past SL fills at the open (with slippage,
   and spread for SHORT where applicable), LONG and SHORT; same for a favorable gap past TP.
   A bar that opens inside the range and crosses the level still fills at the level.
3. Existing broker and backtest tests pass unchanged, or any changed expectation is named
   and justified by the new rule.
4. `uv run ruff check src tests scripts` and the repo quality gate stay green.

## Open questions each candidate must answer in its plan

- Q1: Which mechanism selects the bars that may trigger SL/TP (and pending LIMIT fills)?
  The prior report lists: (a) skip bars with `bar_start < opened_at`, (b) carry the
  subscription interval to the order and position, (c) check only the finest interval the
  broker has seen for that symbol. Others are allowed. Address live feed delay, the pooled
  broker, and backtest equivalence.
- Q2: Does the plan also stop the signal bar from closing the position it just opened?
  If yes, in live only or in backtest too, and what backtest results change?
- Q3: Are pending LIMIT fills covered by the same interval rule? Do they also get a gap rule?
- Q4: Exact gap rule per side, including spread and slippage, and the order of SL vs TP
  checks when the open is past one level.
