# PaperBroker Futures Accounting: Root-Cause Fix for Divide-by-Zero + Balance Corruption

**Date**: 2026-06-28 13:00–17:45  
**Severity**: Critical  
**Component**: Core (PaperBroker, performance_calculator); backtest (tests)  
**Status**: Resolved  

---

## What Happened

Executed plan 260628-2013 end-to-end (5 phases, TDD via /cook): migrated PaperBroker from spot accounting to futures/margin accounting (1× leverage). Root cause of two critical bugs traced to spot model's incompatibility with leveraged positions:

1. **`total_equity` → 0 when all-in**, collapsing Sharpe/Sortino to 0 or NaN (false metrics).
2. **`realized_pnl` double-counted** on partial closes (cumulative position.realized_pnl credited every reduce cycle).

Both flowed upstream to divide-by-zero guard in `performance_calculator.sharpe_ratio/sortino_ratio`, originally misdiagnosed as "cosmetic" guard. Real bug was accounting layer.

---

## The Brutal Truth

This was infuriating to ship because the divide-by-zero **itself was correct and unavoidable** — the accounting underneath was broken. Weeks of performance-calculator band-aids (guards, safe-divide) masked a ticking bomb in position state. The frustration: we should have traced backward from "why is equity going to zero?" instead of forward-engineering numerics safety.

Painful moment came mid-phase-02 when the debit/credit logic for partial closes had to be rewritten **twice**: first attempt cumulated realized_pnl into position object (triple-count on multi-step reduce), second fixed it with a helper `_reduce_and_credit(side, size)` that reads delta before mutation. The second rewrite was unavoidable — we had to **see** the mistake in code to fix it.

Worse: red-team phase (C3) explicitly kept `_can_afford` unchanged (preserving backward compatibility). Code reviewer raised High after implement: under futures accounting, a BUY to cover an underwater SHORT can fail `_can_afford` check (cover-notional > balance) and wedge the position. Plan said "not in scope"; we added a minimal guard anyway (BUY reduce SHORT = always afford). The tension: red-team scope vs. real blocking bug. User decision to patch it saved a forward regression.

---

## Technical Details

### Spot → Futures Accounting Switch

**Spot model (old):** every fill debits/credits `_balance` immediately.  
**Futures model (new):** only **close/reduce** fills debit/credit `_balance`; open/add fills are notional only.

- **Opening a position (LONG buy/SHORT sell):** zero `_balance` impact; position.quantity += fill_size.
- **Reducing a position:** position.quantity -= reduce_size; `_balance += realized_pnl_delta` (computed as: current position value at fill price, minus prior mark, clamped to the size being reduced).

### The _reduce_and_credit Helper

Captures realized PnL **per reduce step** to prevent cumulative position.realized_pnl from being credited multiple times:

```python
def _reduce_and_credit(self, side: OrderSide, reduce_size: float, fill_price: float) -> float:
    """Return realized delta; caller credits _balance."""
    prev_value = self._position.unrealized_pnl(self._last_mark)  # mark before reduce
    self._position.reduce(reduce_size)
    new_value = self._position.unrealized_pnl(self._last_mark)
    return prev_value - new_value  # delta this step, not cumulative
```

Usage: `_balance += _reduce_and_credit(...)`. No position.realized_pnl field touched after position init.

### Mark-to-Market Timing

Prices propagate **at end of bar** (`_on_bar_completed`, after SL/TP loop), not on-demand in getters:

```python
# backtest_app_service.py line 103
self._mtm_on_bar = backtest_event_bus.subscribe(BarCompletedEvent, self._update_equity_after_mark)
# Subscribed AFTER broker handler, so broker.get_balance() reflects marked positions
```

Ordering verified: broker publishes bar → updates mark → app queries balance → equity curve snaps per-bar price, not fill-price. Sharpe/Sortino then sees continuous curve, not gaps.

### Guard: `np.divide` with where clause

Added defense-in-depth in `performance_calculator`:

```python
np.divide(returns, denominator, out=np.zeros_like(returns), where=(denominator != 0))
```

Why: even with fixed accounting, an edge case (flat zero-return bar) could still hit zero denominator. Guard tolerates it gracefully (outputs 0.0 instead of NaN/Inf).

### Available Balance Behavior Change

Under futures: `available_balance = _balance` (not `_balance - unrealized_loss`). Sizing now follows full balance when positioned (margin availability = leverage × balance; at 1× with no unrealized loss, this is just balance).

Real-world impact: pyramiding/multi-symbol size slightly increases (full balance vs. reserve buffer). Current strategy set (engulfing, hitnrun2) doesn't pyramid; forward regression risk = 0.

---

## What We Tried

| Attempt | Result |
|---|---|
| Fix divide-by-zero in performance_calculator (original approach) | Guard hides symptom; equity still wrong at source (accounting). Abandoned; traced to PaperBroker. |
| Keep spot accounting, patch open-position value calculation | Partial closes still multi-credit realized_pnl. Real position balance drifts. Abandoned. |
| Cumulate realized_pnl into position object for each reduce | Triple-count on multi-step reduce (position.realized_pnl + caller credit + history). Caught by red-team test. Rewrote with _reduce_and_credit. |
| Mark prices on-demand in balance getter | Side effects in getter; race condition if called from backtest_app_service before broker handler fires. Moved to _on_bar_completed event. |
| Keep `_can_afford` unchanged, allow SHORT-cover wedge | User decision to add minimal guard: BUY reduce/cover SHORT = always afford. Avoids forward regression. Added test `test_losing_short_cover_not_blocked_by_affordability`. |

---

## Root Cause Analysis

### Why split accounting at root:

Spot model assumes all positions are cash-backed (buy = debit balance, sell = credit cash). Futures are leveraged (multiple positions share collateral). When you open a position, balance doesn't move; when you close, P&L realizes. PaperBroker was mixing both: debit on open (wrong), attempt to cumulate realized_pnl (wrong again).

The equity curve collapse (→ 0 when all-in notional ≈ balance) happened because:
- Open 10,000 units at 1.0, balance = 10,000 → spot model debits 10,000 → _balance = 0 → equity = 0 (nonsense; real futures broker shows equity > 0 due to mark).
- Futures model: open 10,000 units → position.quantity = 10,000, _balance = 10,000 (untouched) → equity = 10,000 (correct, mark not yet applied).

### Why test-first (TDD) was essential:

Five phases (characterization, red-team, implement, refine, final) forced:
1. Capture current behavior in test (why equity collapses).
2. Prove it's wrong with futures oracle (expected vs. actual).
3. Implement fix, watch tests pass.
4. Red-team the fix (SHORT cover, partial closes, multi-symbol).
5. Verify no regressions (engulfing test Sharpe finite, balance re-derives).

Without TDD, a "just patch balance calc" refactor would've shipped with silent corruption.

---

## Lessons Learned

1. **Accounting bugs hide in the layer beneath the symptom.** Divide-by-zero felt like a numerics problem; it was a state-management problem 2 layers down. Trace symptoms all the way to invariant root.

2. **Cumulative state fields (position.realized_pnl) are trap doors.** If a field gets touched by multiple paths (position init, partial reduce, caller credit), you'll triple-count. Use immutable per-step deltas; let caller decide where to store the sum.

3. **Mark-to-market timing matters for series continuity.** If prices propagate on-demand (in getters), equity curve gaps at fill times. Fix timing by wiring to event stream (after bar) so curve reflects one price per bar, matching backtest history.

4. **Spot ≠ futures accounting; don't half-implement.** Either model is correct, but mixing them is poison. Clear decision gate: are we simulating cash-only or margin positions? Encode it in the model, not in special cases.

5. **Red-team must include boundary cases.** Losing SHORT cover was a plausible edge case (position upside-down, margin call scenario). Minimal guard prevents silent wedge; paid off immediately in user patch decision.

---

## Next Steps

1. **Monitor forward strategy suite.** Engulfing/hitnrun2/future signals inherit available_balance increase. No pyramiding expected; regression risk low. Flag if strategy sizing diverges from backtest.

2. **Document accounting model.** Added section to `docs/system-architecture.md` ("PaperBroker accounting model") covering spot vs. futures, mark timing, reduce semantics. Keep updated if leverage changes.

3. **Sharpe/Sortino guard maintenance.** The `np.divide` guard is defensible (edge case, not architectural fix), but if flat-curve guards appear in other metrics, consider a utility function to consolidate.

---

## Verification

| Check | Result |
|---|---|
| Unit tests (paper_broker_test.py) | 10 new + 3 updated; all pass. Tests cover: open no-debit, close credit realized, partial reduce order, SHORT cover afford, multi-bar mark propagation. |
| Characterization test | Spot-debit → futures no-debit verified; post-mark equity matches expected (balance + mark delta). |
| Engulfing backtest test | Sharpe/Sortino finite (guard working); balance re-derives as `10000 + Σ realized` (no drift). |
| Full suite | 640 passed, 1 skipped; ruff clean; pyright strict clean; import-linter 7/7 contracts KEPT. |
| Manual backtest | Dive backtest (sample 50-bar, 5000 notional all-in): equity curve smooth, Sharpe defined, drawdown accurate (not -100%). |

---

Status: DONE  
Summary: PaperBroker futures accounting live; root cause (spot + leverage mix) fixed via _reduce_and_credit helper + mark-after-bar wiring. Divide-by-zero now true edge guard, not architectural fix. All 5 TDD phases passed; no regressions.  
Concerns: None. Forward-impact: available_balance increases (no pyramiding today); minimal _can_afford guard prevents SHORT-cover wedge.
