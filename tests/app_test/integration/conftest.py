"""Fixtures for pocketquant-app integration tests.

Strategy: Build a FastAPI test app using the shared `make_test_app` factory
from app_factory.py which injects the testcontainer Settings directly into
dishka, bypassing the module-level `app = create_app()` in main.py.

The `settings` fixture (function-scoped) is defined in the parent conftest.py.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pocketquant.core.config import Settings

from .app_factory import make_test_app
from .bff_factory import make_bff_test_app


@pytest_asyncio.fixture
async def app_client(settings: Settings):
    """ASGI test client with full FastAPI lifespan against testcontainer DB/Redis."""
    app = make_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def bff_client(settings: Settings):
    """ASGI test client for bff — stateless, all feature routes registered."""
    app = make_bff_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
