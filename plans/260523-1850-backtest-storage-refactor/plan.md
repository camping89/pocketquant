---
title: "Backtest storage & semantics refactor (Backtrader/QuantConnect alignment)"
description: "Rename Fill/Trade per industry convention; split 1-collection embedded model into 4 logical Mongo collections (backtest_runs slim, backtest_orders, backtest_trades, backtest_optimization_runs); PaperBroker emits OrderEvent + persists LIMIT non-fill for forward-test parity; one-time idempotent migration of 22 prod docs."
status: completed
priority: P2
effort: "3-5d"
branch: "develop"
tags: [backtest, storage, refactor, schema, migration]
blockedBy: []
blocks: [260511-1408-backtest-analysis-panel]
created: "2026-05-23T11:57:27.608Z"
createdBy: "ck:plan"
source: skill
brainstorm: ./reports/brainstorm-backtest-storage-and-semantics.md
related:
  - plans/260511-1408-backtest-analysis-panel/  # downstream: FE panel consumes new schema after this plan completes
  - plans/260523-1436-hitnrun2-strategy/        # upstream: strategy that surfaces the refactor need (completed)
---

# Backtest storage & semantics refactor

**Brainstorm:** [`brainstorm-backtest-storage-and-semantics.md`](./reports/brainstorm-backtest-storage-and-semantics.md)

## Goal

Align backtest domain semantics with industry convention (Backtrader + QuantConnect):

- **Order** = intention with full lifecycle (SUBMITTED → FILLED/CANCELLED/REJECTED/EXPIRED)
- **OrderEvent** = status-transition record (embedded in Order doc)
- **Fill** = atomic execution event (embedded in Order doc)
- **Trade** = round-trip economic outcome (entry+exit, separate collection)
- **Position** = current holding snapshot (open lots embedded in run doc)

Split single-collection embedded model into 4 logical NoSQL collections. PaperBroker emits OrderEvent on every status transition and persists LIMIT non-fill orders so forward-test parity is preserved. Idempotent migration handles 22 production documents.

## Out of Scope

- Frontend backtest panel (deferred to `260511-1408-backtest-analysis-panel` revision)
- Equity curve spillout to dedicated collection (defer until size cap hit)
- Live trading Order/Position refactor (live already has dedicated collections)

## Phases

| Phase | Name | Status | Blocks | Effort |
|-------|------|--------|--------|--------|
| 1 | [Domain entities rename + Order/OrderEvent VOs](./phase-01-domain-entities-rename-order-orderevent-vos.md) | Completed | 2,3 | 0.5d |
| 2 | [PaperBroker emit OrderEvent + persist LIMIT non-fill](./phase-02-paperbroker-emit-orderevent-persist-limit-non-fill.md) | Completed | 4 | 0.5d |
| 3 | [Collection split (orders/trades/optimization_runs) + repos](./phase-03-collection-split-orders-trades-optimization-runs-repos.md) | Completed | 4,5 | 1d |
| 4 | [Result collector wire-up to new repos](./phase-04-result-collector-wire-up-to-new-repos.md) | Completed | 5,6 | 0.5d |
| 5 | [One-time idempotent migration script](./phase-05-one-time-idempotent-migration-script.md) | Completed | 6 | 0.5d |
| 6 | [Tests + bidirectional plan link update](./phase-06-tests-bidirectional-plan-link-update.md) | Completed | — | 0.5-1d |

## Key Decisions (from brainstorm)

- Naming: industry standard (Backtrader/QC) — Fill (atomic), Trade (round-trip), Order (intent + lifecycle), OrderEvent (transition)
- Collection split: 4 collections all prefixed `backtest_`: `backtest_runs`, `backtest_orders`, `backtest_trades`, `backtest_optimization_runs`
- NoSQL philosophy: embed `events[]`+`fills[]` in order doc (leaves), `equity_curve[]`+`open_positions[]` in run doc; only split STANDALONE entities cross-run-queryable
- LIMIT non-fill orders persisted with proper status (CANCELLED/EXPIRED) for forward-test parity — confirmed industry standard
- Migration: idempotent script with backup-to-`*_backup_YYMMDD`, dry-run flag, residual_count verify; reconstructs orders from old `trades[]` (fills) and trades from old `positions[]` (round-trips), backfills nullable order_id when not derivable

## Cross-Plan Impact

This plan **blocks** `260511-1408-backtest-analysis-panel` Phase 2-7 (API types + FE panel). That plan must be revised post-merge to consume new schema (orders/trades collections + slimmed run doc).

Update bidirectional link in Phase 6.

## Risks

| Risk | Mitigation | Owner Phase |
|------|------------|-------------|
| Migration corrupts 22 prod docs | Backup collection before write, dry-run flag, residual_count verify, idempotent re-run | P5 |
| OrderEvent stream balloons doc size | Embed only state changes (no per-bar pings); event count bounded by lifecycle steps | P2 |
| API consumers expecting old embedded `trades`/`positions` arrays break | API layer untouched in this plan; downstream plan revises consumers | Out-of-scope |
| IBroker interface changes break OKX live broker | Additive changes only (new OrderEvent emit is broker-internal); IBroker interface preserved | P2 |
| 1-bar SL hit AND TP hit ambiguity (already handled: SL wins) | Document explicitly in OrderEvent reason; test coverage in P6 | P2/P6 |

## Success Criteria

- ✅ 4 collections in place with proper indexes
- ✅ Fill / Trade / Order / OrderEvent value objects align with Backtrader/QC vocab
- ✅ PaperBroker emits OrderEvent on every status transition (SUBMITTED, FILLED, CANCELLED, REJECTED, EXPIRED, AUTO_SL_FILLED, AUTO_TP_FILLED)
- ✅ ResultCollector writes via OrderRepository + TradeRepository + BacktestRepository
- ✅ Migration script: dry-run on 22 docs → residual_count=0 → real run → re-run no-op
- ✅ Existing tests pass: `test_hitnrun2_backtest.py`, `test_result_collector_fifo.py`, `test_lot_tracker.py`
- ✅ New tests: LIMIT non-fill persistence, OrderEvent stream completeness, migration reconstruction
- ✅ `260511-1408-backtest-analysis-panel/plan.md` updated with `blockedBy: [260523-1850-backtest-storage-refactor]`

## Dependencies

None upstream — single-repo, develop branch. Downstream consumer (260511-1408) must wait.

## Unresolved Questions

1. Live `OrderAggregate` vs backtest `Order` VO — unify with mode discriminator or keep separate types? (Default: keep separate; live untouched.)
2. Should `BacktestResult.open_positions` snapshot use `Trade` with exit=null or a lighter `OpenLot` VO? (Default: lighter `OpenLot`.)
3. Subscription-scoped cache currently uses `subscription_id` as `_id` in `backtest_runs` — preserve mechanism or split to `backtest_subscription_cache`? (Default: preserve; cache is just another doc in same collection with sub_id discriminator.)
