"""Tests for CQRS Mediator."""

import pytest

from pocketquant.core.common.mediator import (
    DuplicateHandlerError,
    Handler,
    HandlerNotFoundError,
    HandlerRegistry,
    Mediator,
    handles,
)


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


def test_mediator_raises_on_duplicate_handler():
    """One command/query can only have one handler."""
    mediator = Mediator()
    mediator.register(TestCommand, TestHandler())

    with pytest.raises(DuplicateHandlerError):
        mediator.register(TestCommand, TestHandler())


def test_handles_decorator_stores_request_type():
    """@handles decorator stores request type on class."""

    @handles(TestCommand)
    class DecoratedHandler(Handler[TestCommand, str]):
        async def handle(self, request: TestCommand) -> str:
            return "ok"

    assert hasattr(DecoratedHandler, "_handles_request_type")
    assert DecoratedHandler._handles_request_type is TestCommand


def test_handler_registry_auto_registers():
    """HandlerRegistry reads @handles metadata and registers with mediator."""

    @handles(TestCommand)
    class AutoHandler(Handler[TestCommand, str]):
        async def handle(self, request: TestCommand) -> str:
            return "auto"

    mediator = Mediator()
    registry = HandlerRegistry()
    count = registry.register_all(mediator, [AutoHandler()])

    assert count == 1
    assert mediator.has_handler(TestCommand)


def test_handler_registry_rejects_undecorated():
    """HandlerRegistry raises TypeError for handlers without @handles."""

    class PlainHandler(Handler[TestCommand, str]):
        async def handle(self, request: TestCommand) -> str:
            return "plain"

    mediator = Mediator()
    registry = HandlerRegistry()

    with pytest.raises(TypeError, match="not decorated"):
        registry.register_all(mediator, [PlainHandler()])
