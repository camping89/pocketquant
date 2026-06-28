# Engulfing Strategy: Pattern Detection + Cross-Runtime Parity Lock

**Date**: 2026-06-28 18:00–23:40  
**Severity**: Medium  
**Component**: Strategy (Python), Chart toggle (TypeScript), test infrastructure (vitest)  
**Status**: Resolved  

---

## What Happened

Implemented a new `engulfing` trading strategy (commit 060e757): Python logic to detect and trade engulfing candlestick patterns, plus a TypeScript chart UI toggle that colorizes all engulfing patterns (strong/weak). Locked both runtimes against a shared golden test fixture (byte-identical JSON), enforced by vitest (the project's **first frontend test runner**).

The implementation turned on a critical finding from the prior backtest-infrastructure fix (261428-1514): strategy entry-fill lifecycle must set `_open_direction` only in `on_order_filled`, not optimistically in `on_bar_completed`. Verified that entry fills publish `OrderFilledEvent` routed by `subscription_id` before relying on the pattern.

---

## The Brutal Truth

This was low-friction and satisfying to ship. The plan was well-scoped, the prior backtest fix removed the entry-fill uncertainty, and the fixture-locking approach (vitest parity tests) caught a real cross-runtime divergence that code review alone would've missed: the Python deque window was off-by-one vs. the TS sliding window. Tests forced us to fix it.

The only moment of "wait, does this actually work?" came when wiring `on_order_filled` subscription: the prior session's hook-rename + fill-publish fix meant entry fills were routed, but we didn't have proof until we wired the subscription and ran a backtest. The proof came immediately (623 passed), but there was a 10-second window of "what if the subscription_id routing doesn't work?" We could have cut that window smaller with a quick integration test before implementing the strategy, but the risk was low because the prior fix was already proven in prod re-smoke.

---

## Technical Details

### Design: Set-After-Fill Open-Direction Lifecycle

Unlike `hitnrun2` (which sets `_open_direction` optimistically in `on_bar_completed` after entry signal, risking a wedged position cap if the entry order is rejected or zero-size), `EngulfingStrategy` sets it only in `on_order_filled`:

- **Flat + entry fill received** → set `_open_direction = LONG` (entry side)
- **Open position + opposite-side fill received** → clear `_open_direction = None` (exit side)

Rationale: entry order rejection leaves position cap untouched. Verified before relying on it: `order_app_service` publishes `OrderFilledEvent` with `subscription_id = strategy.id`, routed to `strategy.on_order_filled(order, fill_price)` in `StrategyAppService._on_order_filled`.

### Key-Level Off-by-One: Deque Window Snapshot Timing

Python uses `deque(maxlen=N)` (not N+1), with window **snapshotted BEFORE appending the current bar**:

```python
# Inside on_bar_completed(bar):
key_level_high = max(d[i].high for i in range(len(self._prior_bars)))  # N bars, excludes current
self._prior_bars.append(bar)  # Then append
```

Result: TP key-level (max highs / min lows of prior N bars) is strictly the N bars before the pattern, never including the pattern bar itself. This matches TS logic in the fixture. Off-by-one bug caught by vitest fixture diff.

### Rejection Wick Pct: Always Float (Sentinel 1.0, Never None)

JSON has no canonical null. `pytest.approx(None)` crashes. Keeping `rejection_wick_pct` numeric (sentinel 1.0 for non-engulfing) ensures one comparison path across both runtimes at exactly the edge cases:

```python
# Python
rejection_wick_pct = 1.0 if not is_engulfing else actual_wick_pct

# TS
rejectionWickPct: !isEngulfing ? 1.0 : actualWickPct
```

Fixture JSON parses to identical float values; comparison is deterministic.

### Cross-Plan Dependency Gate: Commit Verification

This plan was blocked by plan 260628-1514 (hook rename + fill-publish fix). The gate required that plan 260628-1514 be **COMMITTED** (not dirty-tree), verified via:

```bash
git log --oneline | grep -q "fix(backtest): wire strategy fill hook"  # HEAD = 222daad ✓
git show 222daad:src/pocketquant/backtest/engine/backtest_engine_sandbox.py | grep -c "EventRegistry"  # > 0 ✓
```

A grep-based gate (searching `on_order_filled` in working tree) would false-pass on uncommitted working-tree code. Git log verification was unambiguous.

### TS Test Setup Without Breaking tsc -b

Added three surgical changes:

1. **`web/tsconfig.test.json`** — extends `tsconfig.app.json`, excludes `test/**/*.test.ts` from `tsc -b` (vitest consumes test files, production build does not).
2. **eslintrc override** — adds vitest globals (`describe`, `it`, `expect`) to `.eslintignore-test` for `test/**/*.test.ts`.
3. **Golden fixture import-as-JSON** — fixture lives in `web/src/__fixtures__/engulfing-parity.json` (imported as data, not cross-root node:fs), ensuring bundler (vite) can trace the dependency.

Result: `tsc -b` and `vite build` both green; vitest 9/9 parity cases pass.

---

## What We Tried

| Attempt | Result |
|---|---|
| Set `_open_direction` in `on_bar_completed` (hitnrun2 pattern) | Rejected: position cap wedge risk if entry rejected. Used `on_order_filled` instead (proven by prior fix). |
| Use deque(maxlen=N+1) and snapshot after append | Fixture diff: TS had N bars, Python had N+1. Changed to snapshot BEFORE append; parity locked. |
| Allow `rejection_wick_pct = None` for non-engulfing | JSON null / `pytest.approx(None)` crashes. Changed to sentinel 1.0 (float). |
| Cross-import fixture with node:fs in TS | Breaks vite bundler. Copied fixture into `web/` as `.json` file instead. |
| Run vitest without `tsconfig.test.json` | `tsc -b` would fail (test files in compile scope). Added test config, `eslintrc` override. |

---

## Root Cause Analysis

### Why implementation went smooth:

1. **Prior backtest fix removed uncertainty.** The hook-rename + fill-publish work proved that `on_order_filled` is called and routed correctly (prod re-smoke with 262+ trades). We didn't have to gamble on entry-fill wiring.

2. **Fixture-locked early.** Vitest + golden JSON caught the deque off-by-one before it shipped. Code review would've missed it (both implementations "look right" in isolation).

3. **Plan scope was tight.** No refactoring, no new abstractions, no shared-state complexity. Straight pattern detection + simple position lifecycle.

### Why vitest was worth the setup cost:

- TS chart toggle + Python backtest logic are coupled via the pattern definition.
- Byte-identical JSON fixture enforces that the definitions stay in sync.
- Without the fixture, we'd have two independent implementations diverging silently until a manual trade contradicts the chart (bad UX, worse debugging).
- Vitest integration was a one-time cost; future strategies benefit immediately.

---

## Lessons Learned

1. **Fixture-lock paired runtimes early.** If two independent implementations must agree on a definition (pattern, calculation, state machine), encode it as a golden data file + test that both parse it identically. This catches semantic drift that code review misses.

2. **Deque window semantics matter.** Snapshot-before-append vs. snapshot-after-append changes which bars enter the window. Document the boundary assumption. A single off-by-one breaks backtests silently (results look "close enough").

3. **Entry-fill lifecycle: set in on_order_filled, not on_bar_completed.** Position-cap wedge risk is real. Use the event that proves the fill happened, not a signal heuristic.

4. **Sentinel values beat None in JSON fixtures.** Null is ambiguous across runtimes. Use a numeric sentinel (1.0 for "non-engulfing") and compare the same way everywhere.

5. **TS test infrastructure is now live.** First vitest setup is the hardest. Future tests are friction-free (tsconfig already in place, eslint configured, fixture pattern proven).

---

## Next Steps

1. **Monitor backtest performance.** Engulfing backtest exercises `performance_calculator.divide_by_zero` warnings on flat equity curves (pre-existing engine code, not an engulfing defect). File a follow-up ticket if it becomes noise.

2. **TP key-level validation.** The max-highs / min-lows deque is correct, but TP selection (1:1 RR vs. key level) deserves a trade-audit review once live signals come in.

3. **Fixture catalog.** Document the parity-fixture pattern in `docs/code-standards.md` so future strategy pairs follow it automatically.

---

## Verification

| Check | Result |
|---|---|
| Backend tests | 623 passed, 1 skipped; ruff clean; import-linter 7/7; OpenAPI snapshot unchanged. |
| Frontend tests | lint 0 errors; `tsc -b` green; `vite build` green; vitest 9/9 parity cases pass. |
| Code review (subagent) | 7 pinned invariants verified; no critical/high; no regression. |
| Integration | Live backtest: entry fills routed correctly, position cap not wedged, TP set at correct key level. |

---

Status: DONE  
Summary: Engulfing strategy shipped with fixture-locked Python↔TS parity (9/9 vitest cases pass). Entry-fill lifecycle proven safe by prior backtest fix; deque off-by-one caught by fixture diff. Vitest setup complete; future strategies inherit the infrastructure.  
Concerns: None. All acceptance criteria met; no regressions.
