"""Tests for CQRS Mediator."""

import pytest

from src.common.mediator import Handler, HandlerNotFoundError, Mediator


class TestCommand:
    """Test command."""

    def __init__(self, value: str) -> None:
        self.value = value


class TestHandler(Handler[TestCommand, str]):
    """Test handler."""

    async def handle(self, request: TestCommand) -> str:
        return f"handled: {request.value}"


@pytest.mark.asyncio
async def test_mediator_dispatches_to_handler():
    """Test mediator routes request to registered handler."""
    mediator = Mediator()
    mediator.register(TestCommand, TestHandler())

    result = await mediator.send(TestCommand("test"))
    assert result == "handled: test"


@pytest.mark.asyncio
async def test_mediator_raises_for_unknown_request():
    """Test mediator raises HandlerNotFoundError for unknown request type."""
    mediator = Mediator()

    with pytest.raises(HandlerNotFoundError):
        await mediator.send(TestCommand("test"))


def test_mediator_tracks_registered_types():
    """Test mediator can list registered request types."""
    mediator = Mediator()
    mediator.register(TestCommand, TestHandler())

    types = mediator.get_registered_types()
    assert TestCommand in types
    assert mediator.has_handler(TestCommand)


def test_mediator_register_alternative_signature():
    """Test alternative register_handler signature."""
    mediator = Mediator()
    handler = TestHandler()
    mediator.register_handler(handler, TestCommand)

    assert mediator.has_handler(TestCommand)
