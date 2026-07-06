# R3: Commission Abstraction — Brainstorm + Plan

**Date**: 2026-07-05 21:19
**Severity**: Low
**Component**: Commission model, PaperBrokerAdapter, OKX mapper, core.domain.trading
**Status**: Planned (not yet implemented)

---

## What Happened

Brainstorm R3 (logic track of the trading-calculation-fix initiative) — grounded by reading real code (`paper_broker_adapter.py`, `value_objects.py`, `okx_order_mapper.py`, `backtest_result_app_service.py`, `config.py`, `broker_factory.py`, `execution.py`), not just a design doc. Settled 4 open decisions → wrote a design report + 5-phase plan.

## Grounding Findings

- Confirmed **2 parallel ledgers**: broker `_balance` (futures, **no commission**) vs collector `_current_equity` (with commission, post-hoc formula `fill_price*qty*config.commission_percent`). `OrderResult` has no commission field yet. `OkxOrderMapper` misses `fee` (data already available in the payload).
- PaperBroker has **4 fill paths** that create separate `OrderResult(FILLED)`: market, limit-immediate, limit-cross (`_fill_pending_on_bar`), synthetic SL/TP exit (`_fire_synthetic_exit`) → risk #1: missing a path = losing commission on that path.

## 4 Settled Decisions (with user)

1. **Funding fee SWAP**: do NOT sim — YAGNI (no historical funding data yet), gap bounded + document. No stub interface (speculative generality).
2. **CommissionModel placement**: `core.domain.trading` (not `brokers`) — a neutral layer so R6 `PositionCalculator` (position domain) can share it, avoiding position→brokers coupling.
3. **R3 vs R5 boundary**: collector reads `result.commission` (single-source now, numbers unchanged since same value) — clears the way for R5 to delete the collector.
4. **Settings field**: add `paper_commission_percent=0.0004` in R3 (matching sibling `paper_slippage_percent`), wire through `execution.py`→`broker_factory` so live-paper has commission right away. R7 tunes value + currency.

## Architecture

`CommissionModel` (Protocol) + `PercentageCommissionModel(bps)` → `OrderResult.commission`. PaperBroker keeps 1 model; the `_execute_fill_with_commission` wrapper consolidates the `_balance` deduction across all 4 paths (guarding against misses). `_can_afford` includes commission. OKX maps `abs(float(fee))` (negative sign=fee → positive cost). import-linter stays **8/8** (no new contract).

## Not Doing (YAGNI)

Funding sim, SlippageModel, est_entry_commission (→R6), maker/taker/tiered.

## Artifacts

- Design: `plans/trading-calulation-fix/r3-commission-abstraction.md`
- Plan: `plans/260705-2119-r3-commission-abstraction/` (5 phases)
- Roadmap R3 → 📋 Planned; 2 unresolved (funding, Settings field) → RESOLVED.
- Cross-plan: MAE/MFE plan `blockedBy` R3 (soft — touches the broker SL/TP path + LotTrackingHelper that R3→R5 modifies).

## Unresolved (deferred to impl/later R)

- `feeCcy != quote` (OKB/cross-margin) — R3 assumes quote, FX gap not yet handled.
- OKX `fee` per-fill vs accumulated — chose accumulated (matches `accFillSz`), verify demo payload at impl time.
- Funding fee perpetual parity gap — open until funding data is available.
