---
title: "DDD Cleanup: Dead Aggregates, Rename OHLCV→Bar, Flatten Symbol, Wire Events, Standardize _id"
description: "Delete dead aggregates, rename OHLCV domain to Bar, flatten SymbolAggregate→Symbol, wire BarCompletedEvent for live trading, fix DI, standardize UUID _id"
status: pending
priority: P1
effort: 5h
branch: feat/strategy-init
tags: [refactor, ddd, events, real-time, cleanup, persistence, rename]
created: 2026-03-15
depends_on: [260315-0037-persistence-schema-consolidation]
---

# DDD Cleanup

## Motivation

DDD strategic map audit (see `docs/ddd-strategic-map.md`) revealed:
1. **Dead aggregates**: `OHLCVAggregate` (event factory shell, used once), `QuoteAggregate` (zero instantiations)
2. **Dead event infra**: `SymbolAggregate._events` never used
3. **Naming**: "OHLCV" is verbose — entity is already called `Bar`, align the whole domain
4. **Over-engineering**: `SymbolAggregate` wraps `SymbolInfo` VO unnecessarily — not a real aggregate root (no child entities, no invariants)
5. **Real-time gap**: `BarCompletedEvent` subscribed by `StrategyAppService` but never emitted in live mode
6. **DI violation**: `QuoteAppService` hardcodes `TradingViewWebSocketClient()`
7. **Inconsistent _id**: `SyncStatus` has no `_id` field

## Decisions (from brainstorm 2026-03-15)

- **HistoricalDataSyncedEvent**: Keep commented with placeholder note for semantic meaning (may wire later for UI notifications)
- **QuoteReceivedEvent/QuoteUpdatedEvent**: Keep dead (not wired). App focuses on bar-completed processing. TODO in README to revisit tick-triggered strategies.
- **Backtest isolation**: Confirmed non-issue. `HistoricalReplayAppService` and `BarAppService` are completely separate paths.
- **_id pattern**: UUID7 everywhere. Compound unique indexes already enforced in `ensure_indexes()`.
- **OHLCV → Bar**: Rename entire subdomain. "Bar" is the entity name, simpler to discuss and refactor.
- **SymbolAggregate → Symbol**: Not an aggregate root (no child entities, no invariants). Flatten to single `Symbol` entity, drop `SymbolInfo` VO.

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Delete OHLCVAggregate](./phase-01-delete-ohlcv-aggregate.md) | pending |
| 2 | [Delete QuoteAggregate](./phase-02-delete-quote-aggregate.md) | pending |
| 3 | [Flatten SymbolAggregate → Symbol](./phase-03-flatten-symbol.md) | pending |
| 4 | [Rename OHLCV → Bar](./phase-04-rename-ohlcv-to-bar.md) | pending |
| 5 | [Wire BarCompletedEvent + Fix DI](./phase-05-wire-realtime-events.md) | pending |
| 6 | [Standardize UUID _id](./phase-06-standardize-uuid-id.md) | pending |

## Risk Mitigation

- Compile check after each phase
- Run `pytest` after each phase
- One commit per phase for easy rollback

## Open Questions (Deferred)

1. Event persistence (event store) for audit/replay at scale? — defer
2. Multi-strategy broker isolation sustainability at 50+ strategies — defer
