"""Tests for EventBus."""

from dataclasses import dataclass

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.domain.shared.events import DomainEvent


@dataclass(frozen=True, eq=False)
class TestEvent(DomainEvent):
    """Test domain event."""

    data: str = ""


@pytest.mark.asyncio
async def test_event_bus_delivers_to_subscribers():
    """Test event bus delivers events to all subscribers."""
    bus = EventBus()
    received = []

    async def handler(event: TestEvent) -> None:
        received.append(event)

    bus.subscribe(TestEvent, handler)

    event = TestEvent(data="test")
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

    event = TestEvent(data="test")
    await bus.publish(event)

    assert len(received1) == 1
    assert len(received2) == 1


@pytest.mark.asyncio
async def test_raising_handler_does_not_stop_later_handlers():
    """Every handler runs; the first error is re-raised afterwards."""
    bus = EventBus()
    received = []

    def boom(event: TestEvent) -> None:
        raise ValueError("first")

    bus.subscribe(TestEvent, boom)
    bus.subscribe(TestEvent, lambda e: received.append(e))

    with pytest.raises(ValueError, match="first"):
        await bus.publish(TestEvent(data="x"))

    assert len(received) == 1


@pytest.mark.asyncio
async def test_event_bus_unsubscribe():
    """An unsubscribed handler no longer receives events."""
    bus = EventBus()
    received = []
    bus.subscribe(TestEvent, received.append)

    assert bus.unsubscribe(TestEvent, received.append) is True
    await bus.publish(TestEvent(data="x"))

    assert received == []
