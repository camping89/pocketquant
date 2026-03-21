"""Pytest configuration and fixtures."""

import pytest

from pocketquant.core.common.mediator import Mediator
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Get test settings."""
    return Settings(
        app_name="pocketquant-test",
        app_version="0.0.1",
        environment="development",
        mongodb_url="mongodb://localhost:27018",  # type: ignore[arg-type]
        mongodb_database="pocketquant_test",
        mongodb_min_pool_size=1,
        mongodb_max_pool_size=10,
        redis_url="redis://localhost:6379/1",  # type: ignore[arg-type]
        redis_cache_ttl=3600,
        log_level="DEBUG",
        log_format="console",
        job_worker_count=1,
    )


@pytest.fixture
def mediator() -> Mediator:
    """Get fresh Mediator instance."""
    return Mediator()


@pytest.fixture
def event_bus() -> EventBus:
    """Get fresh EventBus instance."""
    return EventBus()
