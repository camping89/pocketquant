---
phase: 6
title: "Tests + bidirectional plan link update"
status: pending
priority: P2
effort: "0.5-1d"
dependencies: [4, 5]
---

# Phase 6: Tests + bidirectional plan link update

## Overview

Comprehensive test coverage for new semantics + collection split + migration. Also update bidirectional cross-plan link to `260511-1408-backtest-analysis-panel` (mark it `blockedBy: [260523-1850-backtest-storage-refactor]`) so future planning sees the dependency.

## Requirements

- Functional: All existing tests pass (or are updated for new shape and pass)
- Functional: New tests cover: LIMIT non-fill EXPIRED, LIMIT delayed-fill, CANCELLED, REJECTED, SL/TP auto-fill OrderEvent stream, multi-fill (PARTIAL — flag as future), end-to-end backtest persistence (orders + trades + run all written)
- Functional: Migration test seeds old-shape fixtures → runs → asserts new-shape + idempotency
- Non-functional: Test coverage of new repos via in-memory roundtrip (save → load → equal)
- Non-functional: No mocks for MongoDB writes — use existing `conftest.py` ephemeral containers pattern

## Architecture

### Test inventory after this phase

```
packages/pocketquant-backtest/tests/
├── conftest.py                                          (existing — extend if needed)
├── engine/
│   ├── test_hitnrun2_backtest.py                        (UPDATE assertions)
│   ├── test_lot_tracker.py                              (UPDATE if Lot.entry_order_id added)
│   ├── test_result_collector_fifo.py                    (UPDATE for Trade/Fill types)
│   ├── test_backtest_app_service_persistence.py         (NEW — end-to-end persist verification)
│   ├── test_paper_broker_limit_orders.py                (NEW — Phase 2 LIMIT behaviors)
│   └── test_paper_broker_order_events.py                (NEW — Phase 2 event emission)
├── persistence/
│   ├── test_order_repository.py                         (NEW — CRUD + index)
│   ├── test_trade_repository.py                         (NEW — CRUD + index)
│   └── test_backtest_repository_slimmed.py              (NEW — verify shape)
└── domain/
    └── test_value_objects_roundtrip.py                  (NEW — to_mongo/from_mongo)

scripts/tests/
└── test_one_time_split_backtest_collections.py          (NEW — migration)
```

### Key test scenarios

**`test_paper_broker_limit_orders.py`:**
- T1: BUY LIMIT @ unreachable price (above current) → status SUBMITTED → expire_pending_orders → status EXPIRED
- T2: BUY LIMIT @ reachable (below current) → status FILLED same-bar with reason `limit_cross`
- T3: BUY LIMIT @ price reached in bar+5 → SUBMITTED for 5 bars → FILLED on bar 5 with `limit_cross`
- T4: cancel_order on pending LIMIT → status CANCELLED with reason `user_cancel`
- T5: cancel_order on already-FILLED order → noop (idempotent)
- T6: BUY LIMIT with price=None → status REJECTED with reason `invalid_limit_price`

**`test_paper_broker_order_events.py`:**
- T1: MARKET fill → events = [(None→SUBMITTED, submit), (SUBMITTED→FILLED, market_fill)]
- T2: LIMIT delayed fill → events have correct timestamps spanning bars
- T3: SL auto-fill on bar event → synthetic exit order has events [(None→SUBMITTED, submit), (SUBMITTED→FILLED, auto_sl)]
- T4: REJECT (insufficient balance) → events = [(None→SUBMITTED, submit), (SUBMITTED→REJECTED, insufficient_balance)]
- T5: subscribe_order_event callback gets every event in order

**`test_backtest_app_service_persistence.py`:**
- Run a minimal backtest (e.g., 2 bars, 1 round-trip with hitnrun2 or synthetic strategy)
- Assert `backtest_runs` doc: has metrics/equity_curve/open_positions; no `trades`/`positions` fields
- Assert `backtest_orders` collection: has 2 orders (entry + exit); each has 2+ events, 1+ fill, `status=FILLED`
- Assert `backtest_trades` collection: has 1 trade; `entry_order_id` matches first order; `exit_order_id` matches second; pnl matches
- Assert `Order.resulting_trade_id` populated on the exit order

**`test_order_repository.py`:**
- Roundtrip: save Order → get → equal
- `list_by_run` returns correct subset
- `list_by_strategy_status` filters correctly
- `delete_by_run` cascades correctly
- `ensure_indexes` creates all 4 indexes

**`test_trade_repository.py`:**
- Same pattern as order repo

**`test_value_objects_roundtrip.py`:**
- Each VO (Fill, Trade, Order, OrderEvent, OpenLot, BacktestMetrics, EquityPoint, OptimizationResultEntry):
  - Construct → to_mongo → from_mongo → equal (by field-wise compare)
- Edge cases: optional fields None, datetime tz-aware preserved

**`test_one_time_split_backtest_collections.py`:**
- Setup: seed 3 old-shape `backtest_runs` docs (one completed full, one with mixed open+closed positions, one failed with empty arrays)
- Setup: seed 1 `optimization_runs` doc
- Run migration with `dry_run=True` → no writes occurred
- Run migration with `dry_run=False`:
  - Verify backup collections created (`backtest_runs_backup_*`, `optimization_runs_backup_*`)
  - Verify `backtest_orders` count = sum of old fills
  - Verify `backtest_trades` count = sum of closed positions
  - Verify `backtest_runs` slimmed (no `trades`, no `positions`)
  - Verify `open_positions` only contains lots with `exit_price=None`
  - Verify `backtest_optimization_runs` exists; `optimization_runs` dropped/renamed
  - Verify idempotency marker set on every run doc
- Run migration AGAIN → counts unchanged; logs `skip` for each run

### Bidirectional cross-plan link

Edit `plans/260511-1408-backtest-analysis-panel/plan.md` frontmatter:
```yaml
blockedBy: [260523-1850-backtest-storage-refactor]
blocks: []
```
And add a note in Overview/Goal section:

```
> **Schema migration pending:** This plan's Phase 2-7 (API types + FE panel) consume the schema being refactored by `260523-1850-backtest-storage-refactor`. Wait for completion of that plan before resuming. Phase 1 (FIFO lot tracking) is already complete in current codebase.
```

## Related Code Files

- **Create:**
  - `packages/pocketquant-backtest/tests/engine/test_paper_broker_limit_orders.py`
  - `packages/pocketquant-backtest/tests/engine/test_paper_broker_order_events.py`
  - `packages/pocketquant-backtest/tests/engine/test_backtest_app_service_persistence.py`
  - `packages/pocketquant-backtest/tests/persistence/test_order_repository.py`
  - `packages/pocketquant-backtest/tests/persistence/test_trade_repository.py`
  - `packages/pocketquant-backtest/tests/persistence/test_backtest_repository_slimmed.py`
  - `packages/pocketquant-backtest/tests/domain/test_value_objects_roundtrip.py`
  - `packages/pocketquant-backtest/tests/persistence/__init__.py` (if needed)
  - `packages/pocketquant-backtest/tests/domain/__init__.py` (if needed)
- **Modify:**
  - `packages/pocketquant-backtest/tests/engine/test_hitnrun2_backtest.py` — update assertions for new shape
  - `packages/pocketquant-backtest/tests/engine/test_lot_tracker.py` — update if `Lot.entry_order_id` added
  - `packages/pocketquant-backtest/tests/engine/test_result_collector_fifo.py` — update assertions
  - `plans/260511-1408-backtest-analysis-panel/plan.md` — set `blockedBy`, add migration-pending note
- **Delete:** none

## Implementation Steps

1. Inventory existing failing tests after Phases 1-5 — list every assertion that broke. Fix per test, one at a time.
2. Add `test_value_objects_roundtrip.py` first (fast feedback on Phase 1 correctness).
3. Add `test_paper_broker_limit_orders.py` + `test_paper_broker_order_events.py` — verify Phase 2 contracts.
4. Add `test_order_repository.py` + `test_trade_repository.py` — verify Phase 3 contracts.
5. Add `test_backtest_app_service_persistence.py` — end-to-end Phase 4 verification.
6. Add `test_one_time_split_backtest_collections.py` — verify Phase 5 migration.
7. Run full suite: `cd packages/pocketquant-backtest && pytest -xvs`
8. Run target coverage: `pytest --cov=pocketquant.backtest --cov=pocketquant.core.infrastructure.brokers.paper --cov-report=term`
9. Update `plans/260511-1408-backtest-analysis-panel/plan.md` frontmatter + Overview note.
10. Commit message: `refactor(backtest): align Order/Fill/Trade semantics with Backtrader/QC + split storage into 4 collections`

## Coverage Target

- New code (Phase 1-5 created files): ≥90% line coverage
- Migration script: 100% — only one chance to run correctly on prod
- Modified files: maintain prior coverage; don't regress

## Decision Point — Performance regression test

Question: Should we measure backtest runtime before/after refactor? Three more repository writes (orders, trades, run) could slow per-run time. Probably immaterial for 1-strategy local runs but optimization (grid search) could feel it.

Recommend: skip formal perf test this phase; add `logger.info("persist_duration_ms", ...)` log line in `BacktestAppService.run()` and watch prod numbers post-deploy. Add formal benchmark later if needed.

## Success Criteria

- [ ] All existing tests in `packages/pocketquant-backtest/tests/` pass with updated assertions
- [ ] 7 new test files created, all passing
- [ ] Migration test demonstrates dry-run → real run → re-run-noop flow
- [ ] Coverage ≥90% on new code (Phase 1-5 created files)
- [ ] `plans/260511-1408-backtest-analysis-panel/plan.md` has `blockedBy: [260523-1850-backtest-storage-refactor]` in frontmatter
- [ ] CI green
- [ ] Manual smoke: run `hitnrun2` backtest end-to-end on local dev; verify 3 collections populated correctly via `mongosh`

## Risk Assessment

- **Test flakiness with testcontainers:** Existing `conftest.py` pattern works (per scout). Risk: new tests in `persistence/` and `domain/` subfolders need same conftest scope — may need `tests/conftest.py` propagation. Mitigation: replicate or restructure conftest if pytest can't find fixtures.
- **End-to-end persistence test slow:** Spinning Mongo container per test class adds seconds. Mitigation: session-scoped fixture (already used per scout L51 of `conftest.py`).
- **Cross-plan link update conflicts with active work on 260511-1408:** Low risk since that plan is `pending` (no in-progress phases). Confirm before merge.
- **Coverage threshold tooling:** If repo doesn't have `pytest-cov` configured, skip the explicit coverage gate; rely on test-passes-and-code-reviewed.
