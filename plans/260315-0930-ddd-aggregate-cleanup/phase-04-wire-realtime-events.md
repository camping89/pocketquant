# Phase 4: Wire Real-Time Events

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context

`StrategyAppService` subscribes to `BarCompletedEvent` and `QuoteReceivedEvent` to trigger strategy execution. In backtesting, `HistoricalReplayAppService` emits `BarCompletedEvent` from stored bars. But in **live mode**, neither event is emitted:

- `BarAppService._save_completed_bar()` saves bars to MongoDB but does NOT emit `BarCompletedEvent`
- `QuoteAppService.on_quote_update()` caches quotes to Redis but does NOT emit `QuoteReceivedEvent`

This means live strategy execution via events does not work.

## Key Design Decision

Events should be emitted from app services (not domain aggregates). The app services already have all context needed. This follows the pragmatic pattern established in the DDD map: events at the service boundary, not in throwaway aggregates.

## Files to Modify

| File | Action |
|------|--------|
| `src/application/market_data/bar_app_service.py` | Emit `BarCompletedEvent` after saving completed bar |
| `src/application/market_data/quote_app_service.py` | Emit `QuoteReceivedEvent` after caching quote |

## Implementation Steps

### 1. Check EventBus API

Determine available methods:
- `publish(event)` — single event
- `publish_all(events)` — list of events
- Check `src/common/messaging/event_bus.py` for interface

### 2. Wire `BarCompletedEvent` in `BarAppService`

In `_save_completed_bar()`, after `await self._ohlcv_repo.upsert_bar(domain_bar)`:

```python
event = BarCompletedEvent(
    symbol=bar.symbol,
    exchange=bar.exchange,
    interval=bar.interval.value,
    bar_start=bar.bar_start,
    open=bar.open,
    high=bar.high,
    low=bar.low,
    close=bar.close,
    volume=bar.volume,
    tick_count=bar.tick_count,
)
await self._event_bus.publish(event)
```

**Dependency**: `BarAppService.__init__` needs `event_bus: EventBus` parameter. Check DI provider (`src/providers/`) to wire it.

### 3. Wire `QuoteReceivedEvent` in `QuoteAppService`

In `on_quote_update()`, after caching the quote:

```python
event = QuoteReceivedEvent(
    symbol=symbol,
    exchange=exchange,
    price=last_price,
    volume=quote_data.get("volume"),
    timestamp=quote.timestamp,
)
await self._event_bus.publish(event)
```

**Dependency**: `QuoteAppService.__init__` needs `event_bus: EventBus` parameter. Check DI provider to wire it.

### 4. Update DI providers

Add `EventBus` to `BarAppService` and `QuoteAppService` constructor injection in the relevant dishka provider.

### 5. Compile check + test

### 6. Verify event flow

After wiring, the live event flow should be:
```
QuoteTick → BarAppService → Bar saved → BarCompletedEvent → StrategyAppService
QuoteUpdate → QuoteAppService → Quote cached → QuoteReceivedEvent → StrategyAppService
```

## Open Questions

1. **Event throttling**: Should `QuoteReceivedEvent` be throttled? High-frequency ticks could flood the event bus. Consider debounce or sample interval.
2. **EventBus thread safety**: Is `EventBus.publish()` async-safe under high tick rates? Check implementation.
3. **Backtest isolation**: When backtesting, `HistoricalReplayAppService` already emits `BarCompletedEvent`. Ensure live event wiring doesn't interfere with backtest mode (likely fine — different app service instances).

## Success Criteria

- [ ] `BarCompletedEvent` emitted from `BarAppService._save_completed_bar()`
- [ ] `QuoteReceivedEvent` emitted from `QuoteAppService.on_quote_update()`
- [ ] Both events reach `StrategyAppService` handlers
- [ ] DI providers updated with `EventBus` injection
- [ ] No regression in backtesting flow
- [ ] All tests pass
