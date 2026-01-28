"""Pytest configuration and fixtures."""

import pytest

from src.common.mediator import Mediator
from src.common.messaging import EventBus
from src.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Get test settings."""
    return Settings(
        environment="development",
        mongodb_url="mongodb://localhost:27018/pocketquant_test",
        redis_url="redis://localhost:6379/1",
    )


@pytest.fixture
def mediator() -> Mediator:
    """Get fresh Mediator instance."""
    return Mediator()


@pytest.fixture
def event_bus() -> EventBus:
    """Get fresh EventBus instance."""
    return EventBus()
