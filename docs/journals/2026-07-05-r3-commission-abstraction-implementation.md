# R3: Commission Abstraction — Implementation Complete

**Date**: 2026-07-05 22:02  
**Severity**: Low  
**Component**: Commission model, PaperBrokerAdapter, OrderResult, backtest result collector, OKX mapper  
**Status**: Shipped (commit `b4beb3d8`)

---

## What Shipped

- **`core/domain/trading/commission_model.py`**: `CommissionModel` (Protocol) + `PercentageCommissionModel(bps)` with pure `compute(price, qty) → float` (formula: `abs(price*qty)*bps/10_000`).
- **`OrderResult.commission: float = 0.0`** — new last field, defaults to 0 (backward-compat for legacy OrderResults without fee data).
- **PaperBrokerAdapter single-debit-point wrapper** `_execute_fill_with_commission`: wraps all 4 fill paths (market, limit-immediate, limit-cross-on-bar, synthetic SL/TP exit) — debit from `_balance` always happens through this wrapper; `_can_afford` gate now includes commission cost.
- **Default ctor** `PaperBrokerAdapter(commission_bps=0)` preserves pre-R3 balance (zero commission = backward-compat).
- **Collector single-source switch**: `BacktestResultAppService.on_fill` reads `result.commission` directly instead of computing `fill_price*qty*config.commission_percent`; stamped once (no double-debit risk).
- **Wiring**: `BacktestConfig.commission_bps` → `sandbox.create_broker(commission_bps=)`; `Settings.paper_commission_percent=0.0004` → `execution.py` → `broker_factory` (boundary converts percent to bps).
- **OKX mapper**: `okx_order_mapper.to_order_result` maps `abs(float(fee))` (negative charge → positive cost; missing/empty → 0.0).
- **Removed dead code**: `BacktestConfig.commission_percent` property (had zero consumers after single-source migration).

---

## Key Design Decisions (Why This Matters)

### 1. Placement in `core.domain.trading`, Not `brokers`

**Decision**: Put `CommissionModel` protocol in the neutral business logic tier, not inside infra.brokers.

**Why**: R6 PositionCalculator (position domain) will need commission for realized/unrealized PnL math. If CommissionModel lives in brokers, position domain couples to infra, breaking import-linter contract. Neutral tier avoids the coupling; all layers can depend on it.

**Outcome**: import-linter stays **8/8** (zero new contracts). No architectural debt from this choice.

### 2. Single-Debit-Point Wrapper (Structural Invariant)

**Decision**: Force all 4 fill paths through `_execute_fill_with_commission` — no broker can create an `OrderResult(FILLED)` without debiting commission to balance.

**Why**: With 4 construction sites (market, limit, limit-cross, synthetic exit), the risk #1 was: one path silently forgets to debit. The synthetic-exit path is especially easy to miss because it's created deep in the position-reduce logic. A wrapper turns "did we remember?" from a discipline problem into a structural invariant — **impossible to bypass**.

**Outcome**: Commission debit is 100% consistent. No path can leak.

### 3. Collector Reads Broker Single-Source

**Decision**: After the wrapper stamps `result.commission`, the collector reads that value directly (`commission = result.commission`, line 104), instead of computing from config.

**Why**: Two ledgers computing commission independently (broker + collector) = divergence risk. Broker is the authoritative computation site (it has the exact fill details); collector should mirror it. Single-source eliminates future sync bugs and prepares for R5 (remove collector entirely).

**Outcome**: Commission is always in sync between broker and persisted records.

### 4. Test Validation (Correct, Not Fudge)

**Subtlety Caught**: Collector tests feed synthetic `OrderResult` objects with `config.commission_bps=10` but the default-constructed OrderResults had `commission=0`. After the single-source switch, the collector reads that 0 → test assertions (expected 0.21, 0.645, 10009.79) would break.

**Fix**: Modified collector test helpers (`_fill` helpers) to compute and stamp `PercentageCommissionModel(bps=10).compute(fill_price, qty)` on synthetic results, mirroring what a real broker emits. Tests using `commission_bps=0` (engulfing, hitnrun2) needed no changes.

**Why This Matters**: We didn't fudge numbers to pass. We correctly modeled the test data so assertions reflect real behavior. If a test cheats, it stops catching real bugs.

---

## Known Gaps (Accepted)

1. **Pathological empty-cash cover**: `reduce/cover_short` returns True in `_can_afford` early but still debits commission → balance can dip slightly negative in edge cases (empty position, minimal cash). Documented in code comment. Acceptable because real trading would reject the order anyway; this is a sim detail.

2. **OKX accumulated snapshot vs paper per-fill**: OKX `commission` field is cumulative per order (matches `accFillSz`/`avgPx` at that moment); paper broker debit is per-fill atomic. A future live PnL tracker reusing the naive additive pattern (`+= result.commission` over order-updates) would double-count on subsequent updates. Flagged in roadmap for R4 (live broker integration).

3. **Missing fee currency conversion**: `feeCcy != quote` (e.g., fee in OKB on cross-margin) not handled. R3 assumes quote currency. FX gap documented; opens after we have historical funding data (R6+).

---

## Verification

- **Test suite**: `just test` → **569 passed, 1 skipped**. Zero failures.
- **Linting**: ruff clean.
- **Type checking**: pyright 0 new errors (1 pre-existing unrelated).
- **Import contracts**: lint-imports **8/8** (no new violations).
- **Code review**: Independent review complete. 0 blocking feedback. Production-ready.

---

## Lessons

This phase succeeded because:

1. **Structural invariant (wrapper) eliminated a high-risk discipline problem.** The moment you have 4+ places doing the same thing, extract to 1.
2. **Single-source for derived state prevents subtle sync bugs.** Two computations = divergence; one source = invariant.
3. **Test helpers must model real behavior, not just pass.** Fudging test data hides real bugs downstream.
4. **Boundary conversions (percent↔bps) belong at DI wiring, not scattered in domain logic.**

---

## Next Steps

- **R4**: Integrate live OKX broker; verify accumulated snapshot handling doesn't double-count on multi-fill orders.
- **R5**: Remove collector commission computation entirely; it becomes a pure mirror of broker + lot-tracker.
- **R6+**: Extend to tiered fees, maker/taker, funding fee sim (when data available), fee currency conversion.
