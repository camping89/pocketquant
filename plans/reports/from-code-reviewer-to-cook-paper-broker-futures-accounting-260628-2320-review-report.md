# Code Review — PaperBroker futures accounting fix

From: code-reviewer → cook
Date: 2026-06-28 23:20
Plan: `plans/260628-2013-paper-broker-futures-accounting/`

## Scope reviewed (7 in-scope files)
- `src/pocketquant/core/infra/brokers/paper/paper_broker.py`
- `src/pocketquant/backtest/domain/services/performance_calculator.py`
- `tests/core_test/infra/brokers/paper_broker_futures_accounting_test.py` (new, 9 tests)
- `tests/core_test/infra/brokers/paper_broker_fills_characterization_test.py`
- `tests/backtest_test/engine/test_engulfing_backtest.py`
- `tests/backtest_test/domain/test_performance_calculator_annualization.py`
- `docs/system-architecture.md`

## Verification run
- `pytest tests/backtest_test tests/core_test` → 394 passed
- targeted modified tests → 27 passed
- `ruff check` (changed files) → clean
- `pyright` (changed files) → 0 errors
- `lint-imports` → 7 contracts kept

## Acceptance criteria
- (a) open/add no `_balance` touch; close/reduce `_balance += Δrealized` via `_reduce_and_credit` capturing before/after → PASS. Partial-close ×2 + add-then-reduce both sides verified no triple-count.
- (b) `total_equity = _balance + Σ unrealized`; per-bar mark in `_on_bar_completed`; `get_balance` pure read → PASS.
- (c) `available_balance == _balance` unchanged → PASS.
- (d) SL/TP synthetic exit accounting via same `_execute_fill` path → PASS (balance asserted).
- (e) no public contract break (`_execute_fill` sig, `get_balance`→AccountBalance, `_can_afford` unchanged) → PASS.
- (f) guard does not change numerics on valid curve (`np.divide` where=prev!=0 identical when no zeros) → PASS.
- (g) no new lint/type/import-linter errors → PASS.

## Ordering / concurrency
- Broker subscribes `BarCompletedEvent` in `connect()`, called inside `inject_prepared_strategy` (strategy_app_service.py:193) BEFORE `BacktestAppService.run()` subscribes `_mtm_on_bar` (line 103). EventBus dispatches FIFO → broker marks positions first, `_mtm_on_bar` reads marked equity. Ordering correct.
- Price-prop loop runs after `_fire_synthetic_exit`; closed positions skipped via `not pos.is_closed`. SL/TP always full-closes (`pos.quantity`), so no re-mark of exited positions.
- Single-task assumption holds; lock split between SL/TP block and price-prop block is safe under that contract (consistent with existing pattern).
- Symbol filter `pos.symbol == event.symbol` matches pre-existing SL/TP filter; both composite `{code}:{exchange}`. Backtest is single-symbol.

## Findings

### High (latent, not active for current strategies)
- **`_can_afford` can block a losing short-cover under futures** — paper_broker.py:441-444 + callsites 200/262/612. A short-cover is `OrderSide.BUY`, so it routes through `_can_afford` (`fill_price*qty <= _balance`). Under the old spot model opening a short credited `_balance`, masking this; under futures `_balance` stays at initial, so covering a short at a price where `notional > _balance` (a loss, or any qty*price above balance) gets REJECTED → position stuck open. NOT triggered today: engulfing + hitnrun2 close shorts ONLY via broker SL/TP (`_fire_synthetic_exit`, line 683), which bypasses `_can_afford`. Risk activates only if a future strategy emits an explicit opposite-side BUY to close a short. Plan red-team (C3/C7) consciously deferred the `_can_afford` rewrite to keep scope tight — defensible, but the latent trap should be tracked (a one-line guard: skip the affordability check when the BUY reduces/covers an existing short).

### Low (non-blocking)
- **Stale docstring** — `paper_broker_fills_characterization_test.py:6-10` still says MARKET "opens a LONG position, and debits balance". The futures change removed the debit; the test it describes now asserts no-debit. Docstring contradicts the assertion. Cosmetic.
- **Working-tree scope mixing** — the uncommitted working tree also contains engulfing-related changes NOT part of this task (`engulfing_detector.py`, `engulfing.py`, `web/src/lib/indicators/engulfing.ts`, two `engulfing_golden_fixture.json`, `docs/swing-pivot-key-level.md`). They are green against the suite but belong to a separate workstream — split before commit so the accounting fix lands as a focused commit.

## Positive (risk calibration)
- Tests are behavioral, not phantom: concrete arithmetic per case, both long/short, all-in, partial-close double-count, add-then-reduce both sides, SL/TP exit, per-bar mark. Engulfing test re-derives `initial + Σ realized` from the run's own stats (no hard-pin) and asserts Sharpe/Sortino finite. Guard test elevates RuntimeWarning→error to prove no divide-by-zero.
- `_reduce_and_credit` delta-capture is correct even on full close (`realized_pnl += realized` precedes the `quantity == 0` close branch in entities.py).
- OKXBroker untouched; live balance path unaffected.
- Docs section accurate, AS-IS, honestly discloses `available_balance` semantics + pyramiding behavior change.

## Unresolved questions
- Should the latent `_can_afford` short-cover trap get a minimal guard now (skip affordability when BUY reduces an existing short), or be tracked as tech-debt until a strategy emits explicit short-close orders? Plan deferred it; flagging for an explicit decision.

Status: DONE_WITH_CONCERNS
Summary: Accounting fix is correct, well-tested, and passes all gates (394 tests, ruff/pyright/import-linter clean). One latent High (`_can_afford` can block an explicit losing short-cover under futures — inert for current SL/TP-only strategies) plus a stale docstring and working-tree scope mixing.
Concerns/Blockers:
- High (latent): paper_broker.py:441-444 — `_can_afford` may reject explicit short-cover BUY when notional > `_balance`; not hit by engulfing/hitnrun2 (SL/TP exits bypass it).
- Low: paper_broker_fills_characterization_test.py:6-10 stale "debits balance" docstring.
- Low: working tree mixes unrelated engulfing changes; split before commit.
