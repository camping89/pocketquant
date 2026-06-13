"""Lifespan boot smoke tests.

These tests boot the FastAPI app through its full Dishka-wired lifespan
against testcontainer Mongo + Redis, asserting `/health` returns 200. They
guard the wiring contract: every startup step (index ensure, recovery,
seeding, rehydrate, worker start) resolves and runs without raising.

2 scenarios:

- fresh mongo: no collections — lifespan completes on an empty DB.
- seeded current shape: subscriptions + orders/positions in current field
  shape — boot is a clean no-op that leaves the docs untouched.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database

from .app_factory import make_test_app

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _isolate_db(settings: Settings):
    """Drop the test database between tests — session-scoped Mongo container
    means state leaks across tests otherwise."""
    db = Database()
    await db.connect(settings)
    try:
        await db.database.client.drop_database(settings.mongodb_database)
    finally:
        await db.disconnect()
    yield


async def _seed_current_shape(settings: Settings) -> None:
    """Seed subscriptions + orders/positions in the current field shape."""
    db = Database()
    await db.connect(settings)
    try:
        raw = db.database
        await raw["subscriptions"].insert_one(
            {
                "_id": "sub1",
                "strategy_code": "hitnrun2",
                "symbol": "BTCUSDT:BINANCE",
                "interval": "1m",
            }
        )
        await raw["orders"].insert_one(
            {"_id": "ord1", "subscription_id": "sub1", "status": "filled"}
        )
        await raw["positions"].insert_one(
            {"_id": "pos1", "subscription_id": "sub1", "is_closed": True}
        )
    finally:
        await db.disconnect()


async def _assert_current_shape(settings: Settings) -> None:
    """Assert the seeded docs survive boot unchanged in the current shape."""
    db = Database()
    await db.connect(settings)
    try:
        raw = db.database
        sub = await raw["subscriptions"].find_one({"_id": "sub1"})
        assert sub is not None
        assert sub.get("strategy_code") == "hitnrun2"

        ord_doc = await raw["orders"].find_one({"_id": "ord1"})
        assert ord_doc is not None
        assert ord_doc.get("subscription_id") == "sub1"

        pos = await raw["positions"].find_one({"_id": "pos1"})
        assert pos is not None
        assert pos.get("subscription_id") == "sub1"
    finally:
        await db.disconnect()


async def _boot_app(settings: Settings) -> None:
    """Run the test FastAPI app through one full lifespan cycle."""
    app = make_test_app(settings)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/health")
            assert r.status_code == 200, r.text


async def test_lifespan_boots_on_fresh_mongo(settings: Settings) -> None:
    """Empty Mongo — lifespan completes cleanly on a fresh DB."""
    await _boot_app(settings)


async def test_lifespan_idempotent_on_seeded_current_shape(
    settings: Settings,
) -> None:
    """Current-shape data — boot is a clean no-op that leaves docs untouched."""
    await _seed_current_shape(settings)
    await _boot_app(settings)
    await _assert_current_shape(settings)
