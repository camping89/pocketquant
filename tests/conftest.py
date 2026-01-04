"""Pytest configuration and fixtures."""

import pytest
from src.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Get test settings."""
    return Settings(
        environment="development",
        mongodb_url="mongodb://localhost:27017/pocketquant_test",
        redis_url="redis://localhost:6379/1",
    )
