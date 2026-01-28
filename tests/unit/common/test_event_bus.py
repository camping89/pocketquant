"""Tests for EventBus."""

import pytest

from src.common.messaging import EventBus
from src.domain.shared.events import DomainEvent


class TestEvent(DomainEvent):
    """Test domain event."""

    def __init__(self, data: str) -> None:
        super().__init__()
        self.data = data


@pytest.mark.asyncio
async def test_event_bus_delivers_to_subscribers():
    """Test event bus delivers events to all subscribers."""
    bus = EventBus()
    received = []

    async def handler(event: TestEvent) -> None:
        received.append(event)

    bus.subscribe(TestEvent, handler)

    event = TestEvent("test")
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].data == "test"


@pytest.mark.asyncio
async def test_event_bus_delivers_to_multiple_subscribers():
    """Test event bus delivers to all registered subscribers."""
    bus = EventBus()
    received1 = []
    received2 = []

    async def handler1(event: TestEvent) -> None:
        received1.append(event)

    async def handler2(event: TestEvent) -> None:
        received2.append(event)

    bus.subscribe(TestEvent, handler1)
    bus.subscribe(TestEvent, handler2)

    event = TestEvent("test")
    await bus.publish(event)

    assert len(received1) == 1
    assert len(received2) == 1


@pytest.mark.asyncio
async def test_event_bus_publish_all():
    """Test event bus can publish multiple events."""
    bus = EventBus()
    received = []

    async def handler(event: TestEvent) -> None:
        received.append(event)

    bus.subscribe(TestEvent, handler)

    events = [TestEvent("a"), TestEvent("b"), TestEvent("c")]
    await bus.publish_all(events)

    assert len(received) == 3
    assert [e.data for e in received] == ["a", "b", "c"]


def test_event_bus_limits_history():
    """Test event bus respects max_history limit."""
    bus = EventBus(max_history=5)
    assert bus._history.maxlen == 5


def test_event_bus_tracks_history():
    """Test event bus stores published events in history."""
    bus = EventBus()
    event = TestEvent("test")

    # Publish synchronously for testing
    import asyncio

    asyncio.run(bus.publish(event))

    history = bus.get_history()
    assert len(history) == 1
    assert history[0] == event


def test_event_bus_unsubscribe():
    """Test event bus can unsubscribe handlers."""
    bus = EventBus()

    def handler(event: TestEvent) -> None:
        pass

    bus.subscribe(TestEvent, handler)
    assert bus.get_subscriber_count(TestEvent) == 1

    result = bus.unsubscribe(TestEvent, handler)
    assert result is True
    assert bus.get_subscriber_count(TestEvent) == 0


def test_event_bus_get_all_event_types():
    """Test event bus can list all registered event types."""
    bus = EventBus()

    def handler(event: TestEvent) -> None:
        pass

    bus.subscribe(TestEvent, handler)

    event_types = bus.get_all_event_types()
    assert TestEvent in event_types
