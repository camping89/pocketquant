"""Pytest configuration and fixtures."""

import pytest
from pocketquant.core.common.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings, _find_project_root


@pytest.fixture
def settings() -> Settings:
    """Load test settings from .env.test at project root."""
    env_test = _find_project_root() / ".env.test"
    return Settings(_env_file=str(env_test))  # pyright: ignore[reportCallIssue]


@pytest.fixture
def mediator() -> Mediator:
    """Get fresh Mediator instance."""
    return Mediator()


@pytest.fixture
def event_bus() -> EventBus:
    """Get fresh EventBus instance."""
    return EventBus()
