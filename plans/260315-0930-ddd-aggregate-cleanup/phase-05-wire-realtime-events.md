# Phase 5: Wire BarCompletedEvent + Fix DI

## Overview
- **Priority**: HIGH
- **Status**: pending

## Context

`StrategyAppService` subscribes to `BarCompletedEvent` to trigger strategy execution. In backtesting, `HistoricalReplayAppService` emits it from stored bars. In **live mode**, `BarAppService._save_completed_bar()` saves bars but does NOT emit `BarCompletedEvent`.

**Backtest isolation confirmed**: `HistoricalReplayAppService` and `BarAppService` are completely separate paths. No risk of double-firing.

**DI violation**: `QuoteAppService.__init__` hardcodes `self.provider = TradingViewWebSocketClient()`. Should be injected via Dishka.

## Files to Modify

| File | Action |
|------|--------|
| `src/application/market_data/bar_app_service.py` | Add EventBus injection, emit BarCompletedEvent after saving |
| `src/application/market_data/quote_app_service.py` | Inject TradingViewWebSocketClient via constructor |
| `src/di/market_data.py` | Wire EventBus to BarAppService, inject TradingViewWebSocketClient to QuoteAppService |

## Implementation Steps

### 1. Wire `BarCompletedEvent` in `BarAppService`

Add `event_bus: EventBus` to constructor. In `_save_completed_bar()`, after `await self._ohlcv_repo.upsert_bar(domain_bar)`:

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

### 2. Fix QuoteAppService DI

Replace hardcoded `TradingViewWebSocketClient()`:
```python
# Before
def __init__(self, settings: Settings, cache: Cache, bar_manager: BarAppService):
    self.provider = TradingViewWebSocketClient()

# After
def __init__(self, settings: Settings, cache: Cache, bar_manager: BarAppService, provider: TradingViewWebSocketClient):
    self.provider = provider
```

### 3. Update DI provider (`src/di/market_data.py`)

```python
def get_bar_manager(self, cache: Cache, ohlcv_repository: OHLCVRepository, event_bus: EventBus) -> BarAppService:
    return BarAppService(cache=cache, ohlcv_repository=ohlcv_repository, event_bus=event_bus)

def get_quote_service(self, settings: Settings, cache: Cache, bar_manager: BarAppService) -> QuoteAppService:
    provider = TradingViewWebSocketClient()
    return QuoteAppService(settings=settings, cache=cache, bar_manager=bar_manager, provider=provider)
```

### 4. Compile check + test

### 5. Verify event flow

After wiring, live event flow:
```
QuoteTick → QuoteAppService → BarAppService.add_tick()
  → bar completes → _save_completed_bar() → MongoDB + BarCompletedEvent
    → StrategyAppService._on_bar_completed() → strategy.on_bar()
```

## Success Criteria

- [ ] `BarCompletedEvent` emitted from `BarAppService._save_completed_bar()`
- [ ] `EventBus` injected into `BarAppService` via Dishka
- [ ] `TradingViewWebSocketClient` injected into `QuoteAppService` via Dishka (no hardcoded instantiation)
- [ ] DI provider updated in `src/di/market_data.py`
- [ ] No regression in backtesting flow
- [ ] All tests pass
