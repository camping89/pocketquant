---
title: "DDD Aggregate Cleanup + Real-Time Event Wiring"
description: "Delete dead aggregates (OHLCVAggregate, QuoteAggregate), clean SymbolAggregate, wire BarCompletedEvent/QuoteReceivedEvent for live trading"
status: pending
priority: P1
effort: 3h
branch: feat/strategy-init
tags: [refactor, ddd, events, real-time, cleanup]
created: 2026-03-15
depends_on: [260315-0037-persistence-schema-consolidation]
---

# DDD Aggregate Cleanup + Real-Time Event Wiring

## Motivation

DDD strategic map audit (see `docs/ddd-strategic-map.md`) revealed:
1. **Dead aggregates**: `OHLCVAggregate` (event factory shell, used once), `QuoteAggregate` (zero instantiations)
2. **Dead event infra**: `SymbolAggregate._events` never used
3. **Real-time gap**: `BarCompletedEvent` and `QuoteReceivedEvent` are subscribed to by `StrategyAppService` but never emitted in live mode — only backtesting works

## Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | [Delete OHLCVAggregate](./phase-01-delete-ohlcv-aggregate.md) | pending |
| 2 | [Delete QuoteAggregate](./phase-02-delete-quote-aggregate.md) | pending |
| 3 | [Clean SymbolAggregate](./phase-03-clean-symbol-aggregate.md) | pending |
| 4 | [Wire Real-Time Events](./phase-04-wire-realtime-events.md) | pending |

## Risk Mitigation

- Compile check after each phase
- Run `pytest` after each phase
- One commit per phase for easy rollback

## Open Questions

1. Should `SyncStatus` get a proper `_id` field? Currently upserts by compound key `(symbol, exchange, interval)`.
2. Should `SymbolAggregate` be flattened to a plain entity (removing `SymbolInfo` VO wrapping)?
3. Event persistence (event store) — needed for audit/replay at scale? Defer for now.
4. Multi-strategy broker isolation sustainability at 50+ strategies — defer for now.
