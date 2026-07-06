# R5 — BacktestReportAppService: Rename + Gut Shadow Equity (Broker Single-Source)

**Date:** 2026-07-06 · **Branch:** develop · **Commits:** `ac6315b` → `b872ab9` → `d1122811` → `1bd04be7` → R5 refactor

Rename `BacktestResultAppService` → `BacktestReportAppService`; remove shadow ledger `_current_equity`, `_peak_equity`, `_total_commission`. The collector is now a pure event-driven orchestrator; equity from the single broker source.

## Problem

R4 unified trade emission through the broker `PositionAggregate` but the collector still kept a parallel ledger (`_current_equity`, `_peak_equity`, `_total_commission`) for tracking. Messy:
- `on_fill` both debits commission INTO the shadow ledger and writes the OrderRecord (purpose?).
- `_current_equity` copied from the broker but as a static copy (when the broker changes balance, the shadow "lags").
- Finalize must compute `total_commission` from the shadow ledger (already available in the broker order record).

In reality the broker already has a single source (PaperBrokerAdapter `_balance`), the collector doesn't need to re-record it.

## Changes

| Layer | Content |
|---|---|
| File rename | `backtest_result_app_service.py` → `backtest_report_app_service.py` (git mv); class `BacktestResultAppService` → `BacktestReportAppService`. |
| Constructor | Inject `IBrokerPort` (already available). |
| `on_trade(event)` | Read `broker.get_balance().available_balance` at call time → `equity` (real-time). No caching. |
| `on_fill(...)` | Remove commission debit (`_current_equity -= result.commission`); only write OrderRecord + Fill doc. Commission is already debited in the broker `_execute_fill_with_commission`. |
| `finalize` | Async (was sync). Sum from order records: `total_commission = sum(fill.commission for fill in order_fills)`. Read final broker balance: `finalize_equity = broker.get_balance().available_balance`. |
| Remove | `_current_equity`, `_peak_equity`, `_total_commission` shadow fields; methods `_round_trip`, `_emit_trades`, `_build_open_positions`. |
| MTM & closing equity | Broker `_mtm_curve` per-bar + finalize closing point unchanged. Invariant: `closing_equity = initial − Σ commission + Σ gross_pnl` (proof below). |

## Decisions (non-obvious)

**Parity proof (economically exact; byte-identical on tested runs):** PaperBrokerAdapter lock-timing ensures equity consistency.
- `_execute_fill_with_commission` → debit `_balance` inside `asyncio.Lock`
- `_notify_trade_callbacks` fires (dispatch `TradeClosedEvent`) OUTSIDE lock
- When collector `on_trade` calls `broker.get_balance()`, lock released → `available_balance` = `initial − Σcommission + Σrealized_pnl`
- Old shadow ledger computed exact same formula → every metric unchanged (max_drawdown, total_return, Sharpe, gross PnL, total trades).
- **No more MTM-only collapse** — broker balance IS the truth, not approximate.
- **Caveat (ULP):** addition order changes — old `(E − commission) + pnl` (on_fill then on_trade), new `(E + realized) − commission` (broker fill). IEEE-754 non-associative → may differ by ≤1 ULP for any float (economically irrelevant, ~1e-16 rel). Engulfing/hitnrun2 characterization runs land byte-identical (numbers unchanged), so empirically byte-exact — not claiming provable in general.

**Scope:** Rename + gut only; File size ~380 lines (exceeds 200 guideline) — accepted minimal churn over splitting. Single orchestrator class.

**Finalize async:** 2 call sites in `BacktestAppService.run` (finished + failed path) → `await collector.finalize(...)`.

## Verify

| Check | Result |
|---|---|
| `just test` | **560 passed, 1 skipped** (engulfing + hitnrun2 characterization tests; `mark_to_market` fixture unchanged). |
| `ruff` | Clean. |
| `pyright` | **0 errors** in R5 files (1 pre-existing unrelated in `test_engulfing.py` untouched). |
| `lint-imports` | **8/8 contracts kept** (no new violations). |
| Metrics parity | byte-identical: `max_drawdown`, `total_return`, `sharpe_ratio`, `total_trades`, gross PnL, cumulative realized. |

## Next

- **MAE/MFE excursion (260630-0031):** R1+R2+R3+R4 complete; R5 doesn't hard-block. Old approach used `_lot_tracker.lots` (removed in R4) → needs redesign on `PositionAggregate` (soft-blocker, defer analysis).
- **R6+:** Live broker integration; fee currency, funding fee; tiered commission model.

---

**Status:** DONE  
**Summary:** R5 complete: rename service, remove shadow equity ledger, broker single-source — all metrics parity, 560 tests pass, 0 linting errors.
