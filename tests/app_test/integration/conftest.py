# make_test_app injects the testcontainer Settings into dishka directly, bypassing the
# module-level app = create_app() in main.py.

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pocketquant.core.config import Settings

from .app_factory import make_test_app


@pytest_asyncio.fixture
async def app_client(settings: Settings):
    app = make_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
