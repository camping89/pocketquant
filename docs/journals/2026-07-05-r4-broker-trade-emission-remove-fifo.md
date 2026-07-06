# R4 — Broker Trade Emission (avg-cost) + Remove FIFO

**Date:** 2026-07-05 · **Branch:** develop · **Commits:** `ac6315b` → `b872ab9` → `d1122811` → `1bd04be7`

Consolidated 2 parallel position-accounting systems into ONE source: paper broker `PositionAggregate` (average-cost) emits `TradeClosedEvent`, the collector subscribes instead of building its own FIFO. Removed `LotTrackingHelper`. Net **−510 lines**.

## Problem

Before R4 there were 2 places that "detect close + build Trade":
- Broker reduces `PositionAggregate` (average-cost, commission debit per-fill).
- Collector builds its own FIFO `LotTrackingHelper` from the fill sequence, computes `_consumed_pnl` itself, emits `Trade` independently.

R3 just unified the *commission source* (`OrderResult.commission`) but trade emission was still dual-track. Every change to how a Trade is recorded (commission/pnl/timing) required editing 2 places; FIFO reconstruction bugs cost hours because fixing 1 ledger forgot the other.

## Changes

| Layer | Content |
|---|---|
| `core/domain/position/events.py` | `TradeClosedEvent` — frozen dataclass all-default, economic-only (`pnl` = gross delta of the chunk, `commission`, `direction`, entry/exit price+time+order_id, sl/tp, duration). |
| `core/domain/position/entities.py` | +field `entry_order_id`/`entry_commission`; `reduce_quantity(quantity, price, exit_commission=0.0, exit_order_id=None, exit_time=None)` appends `TradeClosedEvent` to `_events`; `add_quantity(..., commission=0.0)` accumulates; `open(..., entry_order_id, entry_commission, opened_at)` injects sim-time. All default-arg → old callers stay additive. |
| `core/domain/brokers/broker_port.py` | `IBrokerPort.subscribe_trades/unsubscribe_trades` + `TradeCallback`. |
| paper broker | `_execute_fill(order, price, commission)` threads commission into the position then drains `collect_events()` filtering `TradeClosedEvent`; `_execute_fill_with_commission`→`(commission, trades)`; 4 fill paths forward the trade AFTER the fill `OrderResult`. OKX `subscribe_trades` no-op (defer R8), fix `okx_order_mapper` to set `side`. |
| `backtest_result_app_service.py` | `on_fill` keeps OrderRecord/Fill + debit commission per-fill; `on_trade(event)` builds `Trade` (stamps `run_id`/`strategy_code`) + credit `pnl` + back-link `resulting_trade_id`; `open_positions` from `broker.get_positions()`. Removed `LotTrackingHelper`/`_consumed_pnl`/`_emit_trades`/`_resolve_side`/`_build_open_positions` + 2 FIFO tests. |

## Decisions (non-obvious)

- **Subscriber-stamp:** `TradeClosedEvent` is economic-only (does NOT carry run_id/strategy_code) — the subscriber owns the context. Broker infra doesn't need to know the run context. Resolves the R1/R4 open-Q about live-value mapping (defer R8). Event "dumb", handler "smart" → pluggable for backtest vs live.
- **Commission single-debit unchanged:** `on_fill` debits per-fill, `on_trade` ONLY credits gross `pnl`; `TradeClosedEvent.commission` is just for documentation. Invariant: `closing_equity = initial − Σ commission + Σ gross_pnl`. Adding commission in `on_trade` would double-count.
- **Dispatch order:** fill `OrderResult` BEFORE `TradeClosedEvent` → `on_trade` can back-link the exit `OrderRecord` (already exists). Verified by the test `fill_idx < trade_idx`.
- **Equity-curve granularity changed:** dropped the record-on-open point (an open-fill no longer creates an equity point). Accepted because: no golden-number test; the persisted curve uses per-bar `_mtm_curve` (broker `total_equity`) unchanged; `total_return`/`cagr` depend on closing equity. **A likely future surprise** — flagged in the docs.
- **OKX defer R8:** OKX's `OrderResult.commission` is an accumulated snapshot vs paper's per-fill → emitting Trade from OKX now would double-count. R4 paper-only avoids it cleanly; R8 handles the snapshot-delta when wiring live.

## Verify

- `just test`: **560 passed, 1 skipped** (e2e hitnrun2/engulfing/persistence + `mark_to_market` metrics byte-identical MTM-on vs off).
- `ruff` clean · `pyright` 0 errors · `lint-imports` **8/8 kept**.
- `git grep 'LotTrackingHelper\|_consumed_pnl'` clean in src/tests/docs-AS-IS.

## Next

- **R5:** rename `BacktestResultAppService`→`BacktestReportAppService`, fully event-driven (gut residual equity accounting).
- **R8:** OKX position→Trade emission (settle the source via demo payload), live-value for `Trade.run_id`/`strategy_code`.
- **Cross-plan:** `260630-0031` (MAE/MFE excursion) has no more hard blocker (R2/R3/R4 done) but the old approach based on `_lot_tracker.lots` has been removed → needs a redesign to track on `PositionAggregate`.
