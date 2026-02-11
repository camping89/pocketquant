---
phase: 4
title: "Update App Startup"
status: pending
effort: 60m
---

# Phase 4: Update App Startup

## Context Links

- [main.py](../../src/main.py) - lifespan function
- [Phase 3: Migrate](phase-03-migrate-handlers.md)

## Overview

Update app startup to use auto-discovery pattern. Add logging for registered handlers.

## Key Insights

- Current startup already calls `position_tracker.start()` and `strategy_engine.start()`
- Those start() methods now call `register_handlers()` internally
- No changes needed to main.py for basic functionality
- Add optional debug logging for visibility

## Current Flow (main.py:176-184)

```python
# Load pending orders from database
await order_manager.load_pending_orders()

# Start position tracker (subscribes to OrderFilled, loads open positions)
await position_tracker.start()

# Start strategy engine (subscribes to BarCompleted, QuoteReceived)
await strategy_engine.start()

logger.info("strategy_engine_initialized")
```

## Updated Flow

No changes to main.py required! The start() methods handle registration internally.

Optional: Add debug logging to verify handlers registered:

```python
# Start position tracker
await position_tracker.start()
logger.debug("position_tracker_handlers_registered",
             count=event_bus.get_subscriber_count(OrderFilledEvent))

# Start strategy engine
await strategy_engine.start()
logger.debug("strategy_engine_handlers_registered",
             bar_handlers=event_bus.get_subscriber_count(BarCompletedEvent),
             quote_handlers=event_bus.get_subscriber_count(QuoteReceivedEvent))
```

## Add Tests

### Unit Tests for Event Registry

```python
# tests/unit/common/test_event_registry.py

import pytest
from src.common.messaging import EventBus, EventRegistry, event_handler
from src.domain.shared.domain_event import DomainEvent


class SampleEvent(DomainEvent):
    """Test event."""
    value: int = 0


class AnotherEvent(DomainEvent):
    """Another test event."""
    message: str = ""


class TestEventHandler:
    """Test fixture for event_handler decorator."""

    def test_decorator_marks_method_with_event_types(self):
        """Decorator adds _event_types attribute to method."""
        class Handler:
            @event_handler(SampleEvent)
            async def handle(self, event: SampleEvent) -> None:
                pass

        assert hasattr(Handler.handle, "_event_types")
        assert SampleEvent in Handler.handle._event_types

    def test_decorator_supports_multiple_event_types(self):
        """Single decorator can handle multiple event types."""
        class Handler:
            @event_handler(SampleEvent, AnotherEvent)
            async def handle(self, event: DomainEvent) -> None:
                pass

        assert SampleEvent in Handler.handle._event_types
        assert AnotherEvent in Handler.handle._event_types


class TestEventRegistry:
    """Test EventRegistry class."""

    @pytest.fixture
    def bus(self) -> EventBus:
        return EventBus()

    @pytest.fixture
    def registry(self) -> EventRegistry:
        reg = EventRegistry()
        yield reg
        reg.clear()

    def test_register_instance_returns_handler_count(self, bus, registry):
        """register_instance returns number of handlers registered."""
        class Handler:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                pass

        handler = Handler()
        count = registry.register_instance(handler, bus)

        assert count == 1

    def test_register_instance_subscribes_to_event_bus(self, bus, registry):
        """Registered handlers are subscribed to EventBus."""
        class Handler:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                pass

        handler = Handler()
        registry.register_instance(handler, bus)

        assert bus.get_subscriber_count(SampleEvent) == 1

    @pytest.mark.asyncio
    async def test_registered_handler_receives_events(self, bus, registry):
        """Registered handler receives published events."""
        received = []

        class Handler:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                received.append(event)

        handler = Handler()
        registry.register_instance(handler, bus)

        event = SampleEvent(value=42)
        await bus.publish(event)

        assert len(received) == 1
        assert received[0].value == 42

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_event(self, bus, registry):
        """Multiple handlers can subscribe to same event."""
        received_a = []
        received_b = []

        class HandlerA:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                received_a.append(event)

        class HandlerB:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                received_b.append(event)

        handler_a = HandlerA()
        handler_b = HandlerB()
        registry.register_instance(handler_a, bus)
        registry.register_instance(handler_b, bus)

        await bus.publish(SampleEvent(value=1))

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_handler_multiple_events(self, bus, registry):
        """Single handler with multiple event types receives all."""
        received = []

        class Handler:
            @event_handler(SampleEvent, AnotherEvent)
            async def _on_any(self, event: DomainEvent) -> None:
                received.append(event)

        handler = Handler()
        registry.register_instance(handler, bus)

        await bus.publish(SampleEvent(value=1))
        await bus.publish(AnotherEvent(message="hello"))

        assert len(received) == 2

    def test_sync_handler_works(self, bus, registry):
        """Sync handlers work (not just async)."""
        received = []

        class Handler:
            @event_handler(SampleEvent)
            def _on_sample(self, event: SampleEvent) -> None:
                received.append(event)

        handler = Handler()
        count = registry.register_instance(handler, bus)

        assert count == 1

    def test_get_registered_returns_tracking_info(self, bus, registry):
        """get_registered returns list of registered handlers."""
        class Handler:
            @event_handler(SampleEvent)
            async def _on_sample(self, event: SampleEvent) -> None:
                pass

        handler = Handler()
        registry.register_instance(handler, bus)

        registered = registry.get_registered()
        assert len(registered) == 1
        assert registered[0][0] == SampleEvent
        assert registered[0][1] is handler
        assert registered[0][2] == "_on_sample"
```

### Integration Test

```python
# tests/integration/common/test_event_discovery_integration.py

import pytest
from src.common.messaging import EventBus, event_handler, get_event_registry
from src.domain.ohlcv.ohlcv_event import BarCompletedEvent
from src.domain.order.order_event import OrderFilledEvent


class TestEventDiscoveryIntegration:
    """Integration test for event auto-discovery pattern."""

    @pytest.mark.asyncio
    async def test_strategy_engine_pattern(self):
        """Verify the pattern works like StrategyEngine."""
        bar_events = []

        class MockEngine:
            def __init__(self, event_bus: EventBus):
                self._event_bus = event_bus
                self._running = False

            async def start(self) -> None:
                if self._running:
                    return
                self._event_bus.register_handlers(self)
                self._running = True

            @event_handler(BarCompletedEvent)
            async def _on_bar(self, event: BarCompletedEvent) -> None:
                bar_events.append(event)

        bus = EventBus()
        engine = MockEngine(bus)
        await engine.start()

        # Verify subscription
        assert bus.get_subscriber_count(BarCompletedEvent) == 1

        # Verify handler called
        event = BarCompletedEvent(
            symbol="BTC",
            exchange="CRYPTO",
            interval="1m",
            bar_start=...,  # would need real values
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000.0,
        )
        await bus.publish(event)

        assert len(bar_events) == 1
```

## Todo List

- [ ] Verify main.py doesn't need changes (start() handles it)
- [ ] Create tests/unit/common/test_event_registry.py
- [ ] Create tests/integration/common/test_event_discovery_integration.py
- [ ] Run full test suite
- [ ] Update docs/system-architecture.md with new pattern

## Success Criteria

- App starts successfully
- All events routed correctly
- No regressions in existing functionality
- Tests cover decorator and registry

## Documentation Update

Add to `docs/system-architecture.md`:

```markdown
### Event Handler Auto-Discovery

Event handlers use decorator-based registration:

```python
from src.common.messaging import EventBus, event_handler

class PositionTracker:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    async def start(self) -> None:
        self._event_bus.register_handlers(self)

    @event_handler(OrderFilledEvent)
    async def _on_order_filled(self, event: OrderFilledEvent) -> None:
        # Handle order fill...
```

Benefits:
- Handler intent is clear at method definition
- No need to modify main.py for new handlers
- Type-safe event binding
```

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Missed handler | Full test coverage |
| Startup failure | Existing integration tests |
| Performance | Lazy registration, minimal overhead |

## Verification Commands

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/unit/common/test_event_registry.py -v
pytest tests/unit/common/test_event_bus.py -v

# Type check
pyright src/common/messaging/

# Start app and verify logs
just start
# Look for: strategy_engine_started, position_tracker_started
```
