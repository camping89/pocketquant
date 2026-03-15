# Brainstorm: DDD Aggregate Root Audit

**Date:** 2026-03-15 | **Scope:** All 5 aggregate roots

## Problem

Schema consolidation refactor (260315-0037) eliminated persistence schemas but preserved all aggregates unchanged. User questioned: why do `OHLCVAggregate` and `Bar` coexist? Full audit requested.

## Findings

| Aggregate | Invariants | Events Used | Persisted | Instantiated | Verdict |
|-----------|-----------|-------------|-----------|-------------|---------|
| `OrderAggregate` | State machine (5 transitions) | 5 event types, all consumed | MongoDB | Heavily | **Keep** |
| `PositionAggregate` | P&L, lifecycle, scale in/out | 3 event types, all consumed | MongoDB | Heavily | **Keep** |
| `SymbolAggregate` | activate/deactivate | 0 events (dead `_events` infra) | MongoDB | Yes | **Keep, clean dead events** |
| `OHLCVAggregate` | None | 2 types defined, used once | No | Once | **Delete** |
| `QuoteAggregate` | None | 2 types defined, never published | No | Zero | **Delete** |

## Critical Discovery: Real-Time Event Gap

- `StrategyAppService` subscribes to `BarCompletedEvent` and `QuoteReceivedEvent`
- Backtesting emits `BarCompletedEvent` via `HistoricalReplayAppService` — works
- Live mode: `BarAppService` and `QuoteAppService` never emit events — **live strategies can't fire**
- Root cause: events were supposed to come from aggregates, but aggregates were never wired

## Agreed Actions

1. Delete `OHLCVAggregate` — inline event creation in sync handler
2. Delete `QuoteAggregate` — dead code
3. Clean `SymbolAggregate` — remove unused `_events` infra
4. Wire `BarCompletedEvent` emission in `BarAppService._save_completed_bar()`
5. Wire `QuoteReceivedEvent` emission in `QuoteAppService.on_quote_update()`

## Deliverables

- DDD strategic map: `docs/ddd-strategic-map.md`
- Implementation plan: `plans/260315-0930-ddd-aggregate-cleanup/`

## Open Questions

1. SyncStatus identity — should it get a proper `_id`?
2. SymbolAggregate — flatten `SymbolInfo` VO wrapping?
3. Event persistence (event store) for audit/replay — defer
4. QuoteReceivedEvent throttling under high tick rates
5. Multi-strategy broker isolation at scale — defer
