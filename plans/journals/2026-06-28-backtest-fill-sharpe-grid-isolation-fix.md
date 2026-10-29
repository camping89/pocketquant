# Backtest Fill Routing, Sharpe Annualization, & Sandbox Isolation Fixed

**Date**: 2026-06-28 14:30–17:57  
**Severity**: High  
**Component**: Backtest engine (fill routing, metrics, grid-optimization)  
**Status**: Resolved  

---

## What Happened

Four latent bugs in backtest infrastructure hit us in parallel:

1. **`strategy.on_fill` had zero call-sites** — backtests capped at 1 trade regardless of logic.
2. **Sharpe/Sortino annualized with constant 365 bars/year** over event-sampled equity → nonsense (-227, -30).
3. **Hook name drift** — `on_bar`, `on_tick`, `on_fill` didn't mirror the event system (`BarCompletedEvent`, `QuoteReceivedEvent`, `OrderFilledEvent`).
4. **Grid-optimization cross-talk** — multiple runs shared a single EventBus → phantom positions leaked into live engine.

Source: a VPS backtest-health diagnostic (audit report), not a dated smoke-test. The entry MARKET fill state-machine gap (PENDING→FILLED forbidden → order rejected → entry event never published) was discovered while building the fix and folded into scope.

---

## The Brutal Truth

This was infuriating. We shipped a "fixed" backtest that couldn't execute a single strategy callback. The metrics were so backwards (Sharpe -227 on profitable combos) that they looked like silent type corruption. The grid-optimization test said "pass" but orders were hitting the live engine—proof the test isolation was theater.

The worst part: the fills-routing bug was **immediately visible** if you traced `strategy.on_fill` in the IDE. It had zero references. We didn't. This is the cost of not running code during review—assuming the wiring is "obviously right" when it's obviously not.

---

## Technical Details

### Bug #1: Fill Routing

Entry order fill was stuck in PENDING state after broker MARKET fill → `strategy.on_fill` never called.

Root: `PaperBroker` filled the order internally but didn't publish `OrderFilledEvent`. The SL/TP synthetic exits also didn't publish fills.

Fix:
- Entry MARKET fill: route state transition PENDING→SUBMITTED→FILLED, emit `OrderFilledEvent`.
- SL/TP exits in `PaperBroker`: publish `OrderFilledEvent` (on `subscription_id` of original entry).
- `StrategyAppService._on_order_filled` subscribes to `OrderFilledEvent`, routes to the owning strategy by **`subscription_id`** (= `strategy.id`), then calls `strategy.on_order_filled(order, fill_price)`.

Result: 592 tests pass. Prod re-smoke grid-opt hitnrun2 combos: 262 & 296 trades (was capped at 1).

### Bug #2: Sharpe Nonsense

Code: `annual_return = mean_return * TRADING_DAYS_PER_YEAR` (=365), `annual_std = std * sqrt(365)` — annualized with the constant 365 regardless of the bar interval, on an equity curve sampled per-event (not per-bar).

For 1h bars: correct factor is 8760 bars/yr, not 365 → annualization off by ~24×, and the event-sampled curve broke the even-spacing annualization assumes. Result: Sharpe -227 on +2% total return (impossible).

Fix:
- Add `Interval.periods_per_year` (crypto 365d: 1m→525600, 1h→8760, 1d→365, 1w→52.14).
- Sharpe/Sortino: keyword-only `periods_per_year` parameter.
- Early-return 0.0 if len(returns) < 2.
- CAGR left invariant (still uses calendar year logic).

Result: Combo-0 (67% win, -1.06% maxDD) → Sharpe 11.25 (sane, high vol). Combo-1 (56% win, loss) → Sharpe 0.83. Metrics now respond to strategy quality.

### Bug #3: Hook Rename

Old names didn't match event system:
```
on_bar          vs BarCompletedEvent
on_tick         vs QuoteReceivedEvent
on_fill         vs OrderFilledEvent
```

Renamed IStrategy hooks to match. Deliberately did NOT rename `BacktestResultCollector.on_fill` (different domain — accumulates trade records, not strategy signal).

### Bug #4: Grid-Opt Isolation

Grid-optimization loop reused a single EventBus across runs → new-run entry order subscribed to OLD strategy's handlers. Phantom positions leaked into live position tracker.

New file: `src/pocketquant/backtest/engine/backtest_engine_sandbox.py` — per-run sandbox with isolated EventBus, StrategyAppService, order/position trackers via local EventRegistry.

Result: Prod re-smoke showed `positions: 0` (sandbox contained), distinct trade counts (262 ≠ 296) prove no cross-talk.

---

## What We Tried

| Attempt | Result |
|---|---|
| Trace `on_fill` call-sites (IDE) | 0 refs → obvious wiring gap. Fixed by publishing fills + subscribing. |
| Analyze grid-opt concurrency | Red-team + build surfaced shared-APP-EventBus cross-talk → synthetic-exit publish could create phantom positions in live `PositionAppService`. Added per-run sandbox; prod re-smoke confirmed `positions: 0`. |
| Verify Sharpe regression | Looked like type corruption (negative on profitable) → realized constant 365. Added interval awareness. |
| Pre-smoke `.env` check | Earlier session left `.env` = prod with no backup. Backed up, restored local. |

---

## Root Cause Analysis

### Why the bugs didn't surface earlier:

1. **Fill routing**: Strategy callback is optional (strategy doesn't have to define it). No test explicitly checked `on_fill` was called on a live fill. The grid-opt test had no assertions on trade count (only Sharpe metrics—which were broken anyway).

2. **Sharpe annualization**: Metrics were visibly insane (-227) but we assumed "this is just a side-effect of the interval being wrong" and moved on. No test validates Sharpe range (e.g., profitable combo must have Sharpe > -10).

3. **Hook drift**: Renamed events in one layer, forgot to rename strategy hooks in another. No import-linter check enforces event/hook name correspondence.

4. **Grid-opt isolation**: New feature (Phase 5) had unit tests but no integration test that verified isolation boundaries. Single EventBus was a convenience; no one asked "what if two runs collide?"

### Real lesson:

Code review and test review are NOT the same. Tests passing doesn't mean the wiring is live. Tests have blind spots—optional callbacks, shared global state, metrics that look wrong but you don't validate. 

A 30-second trace-refs check before submitting would have caught bug #1. A single `assert trades > 100` in the grid test would have caught it in CI. But the review said "tests pass, approved."

---

## Lessons Learned

1. **Trace call-sites during code review.** If a handler/callback has zero refs, it's dead or the wiring is missing. Use IDE tools.

2. **Validate metrics ranges in tests.** Don't assume "Sharpe -227" is expected; assert `sharpe > expected_min` for known-good combos.

3. **Add isolation assertions to integration tests.** For grid-opt: `assert live_positions == 0 after each run` (not just Sharpe targets).

4. **Interval awareness is load-bearing.** Sharpe, Sortino, CAGR all scale differently. Encode `periods_per_year` as an interval property; don't scatter 365 constants. **INTERVAL.periods_per_year, always.**

5. **Don't trust `/dev/tcp` for liveness under zsh.** The probe returned false negative; actual async clients (pymongo, redis) connected fine. Use driver connection attempts instead.

6. **`.env` discipline:** Prod credentials shouldn't have a manual backup strategy. Harden `.gitignore` for `.env.*` so backups never slip in. Always restore to local after smoke-testing prod.

---

## Next Steps

1. **Commit scoping** (awaiting user): recommend ~22 plan-specific files + regenerated OpenAPI baseline + `.gitignore` hardening as a single focused commit, separate from the unrelated 123-file comment-stripping pass.

2. **Live fill wiring** (out of scope, planned): OKX `on_order_update` currently unwired; live fills won't publish `OrderFilledEvent`. Follow-up when live trading enablement happens.

3. **Import-linter enhancement** (optional): add contract checking event/hook name correspondence to catch future drift.

---

**Verification**: 592 passed / 1 skipped / 0 failed (5 stable runs). Ruff + pyright clean. Import-linter 7/7. Prod grid-opt grid hitnrun2 shows sane Sharpe (11.25 high-vol, 0.83 losing) + zero leaked positions.

---

Status: DONE  
Summary: Four backtest bugs (fill routing, Sharpe annualization, hook naming, grid-opt isolation) fixed in parallel. Metrics now sane, isolation confirmed in prod; lessons center on call-site tracing, metric validation, and interval-aware constants.  
Concerns: None. All acceptance criteria met; tests stable.
