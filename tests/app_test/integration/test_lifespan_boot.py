"""Lifespan boot smoke tests.

These tests boot the FastAPI app through its full Dishka-wired lifespan
against testcontainer Mongo + Redis. They would have caught the
`db.database` AttributeError that shipped in plan 260528-2000 — the bug
went undetected because (a) CI had no pytest job, (b) the only existing
migration test was broken at collection time with MissingReturnHintError.

3 scenarios cover the migration-pending and migration-done states:

- fresh mongo: no collections — lifespan should be a no-op for migration.
- legacy state: strategy_subscriptions + legacy strategy_id docs — lifespan
  should rename + rewrite fields without raising.
- already-migrated state: post-migration shape — lifespan should be
  idempotent (no double rename, no schema corruption).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pocketquant.core.config import Settings
from pocketquant.infrastructure.persistence.mongodb import Database

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


async def _seed_legacy_state(settings: Settings) -> None:
    """Seed the pre-migration collection + field shape."""
    db = Database()
    await db.connect(settings)
    try:
        raw = db.database
        await raw["strategy_subscriptions"].insert_one(
            {
                "_id": "sub1",
                "strategy_id": "hitnrun2",
                "symbol": "BTCUSDT:BINANCE",
                "interval": "1m",
            }
        )
        await raw["orders"].insert_one({"_id": "ord1", "strategy_id": "sub1", "status": "filled"})
        await raw["positions"].insert_one({"_id": "pos1", "strategy_id": "sub1", "is_closed": True})
    finally:
        await db.disconnect()


async def _seed_migrated_state(settings: Settings) -> None:
    """Seed the post-migration collection + field shape."""
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


async def _assert_migrated_shape(settings: Settings) -> None:
    db = Database()
    await db.connect(settings)
    try:
        raw = db.database
        names = await raw.list_collection_names()
        assert "subscriptions" in names, names
        assert "strategy_subscriptions" not in names, names

        sub = await raw["subscriptions"].find_one({"_id": "sub1"})
        assert sub is not None
        assert sub.get("strategy_code") == "hitnrun2"
        assert "strategy_id" not in sub

        ord_doc = await raw["orders"].find_one({"_id": "ord1"})
        assert ord_doc is not None
        assert ord_doc.get("subscription_id") == "sub1"
        assert "strategy_id" not in ord_doc

        pos = await raw["positions"].find_one({"_id": "pos1"})
        assert pos is not None
        assert pos.get("subscription_id") == "sub1"
        assert "strategy_id" not in pos
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
    """Empty Mongo — lifespan should complete; migration is a no-op."""
    await _boot_app(settings)


async def test_lifespan_boots_on_legacy_state(settings: Settings) -> None:
    """Legacy data — migration renames collection + fields without error."""
    await _seed_legacy_state(settings)
    await _boot_app(settings)
    await _assert_migrated_shape(settings)


async def test_lifespan_idempotent_on_already_migrated_state(
    settings: Settings,
) -> None:
    """Post-migration data — second boot must be a no-op, not a double-rename."""
    await _seed_migrated_state(settings)
    await _boot_app(settings)
    await _assert_migrated_shape(settings)
