"""Tests for migrate_strategy_id_fields — boot-time Mongo migration."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from pocketquant.app.main_extensions import migrate_strategy_id_fields
from pocketquant.core.config import Settings
from pocketquant.infrastructure.persistence.mongodb import Database


class _TestProvider(Provider):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings

    @provide(scope=Scope.APP)
    def get_settings(self) -> Settings:
        return self._settings

    @provide(scope=Scope.APP)
    async def get_database(self, settings: Settings) -> AsyncIterator[Database]:
        db = Database()
        await db.connect(settings)
        yield db
        await db.disconnect()


@pytest_asyncio.fixture(autouse=True)
async def _reset_db(settings: Settings):
    """Drop test DB before each test — session-scoped Mongo container persists state."""
    db = Database()
    await db.connect(settings)
    try:
        await db.database.client.drop_database(settings.mongodb_database)
    finally:
        await db.disconnect()
    yield


@pytest_asyncio.fixture
async def container(settings: Settings):
    c = make_async_container(_TestProvider(settings))
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_renames_collection_and_fields(container, settings: Settings) -> None:
    db = await container.get(Database)
    raw = db.database

    # Seed a legacy strategy_subscriptions doc + legacy orders/positions/backtest docs.
    await raw["strategy_subscriptions"].insert_one(
        {"_id": "sub1", "strategy_id": "hitnrun2", "symbol": "BTCUSDT:BINANCE", "interval": "1m"}
    )
    await raw["orders"].insert_one({"_id": "ord1", "strategy_id": "sub1", "status": "filled"})
    await raw["positions"].insert_one({"_id": "pos1", "strategy_id": "sub1", "is_closed": False})
    await raw["backtest_runs"].insert_one(
        {"_id": "bt1", "strategy_id": "hitnrun2", "status": "completed"}
    )

    try:
        await migrate_strategy_id_fields(container)

        # Collection rename
        names = await raw.list_collection_names()
        assert "subscriptions" in names
        assert "strategy_subscriptions" not in names

        # Subscription field rename
        sub = await raw["subscriptions"].find_one({"_id": "sub1"})
        assert sub is not None
        assert sub.get("strategy_code") == "hitnrun2"
        assert "strategy_id" not in sub

        # Order/Position field rename → subscription_id
        ord_doc = await raw["orders"].find_one({"_id": "ord1"})
        assert ord_doc is not None
        assert ord_doc.get("subscription_id") == "sub1"
        assert "strategy_id" not in ord_doc

        pos = await raw["positions"].find_one({"_id": "pos1"})
        assert pos is not None
        assert pos.get("subscription_id") == "sub1"
        assert "strategy_id" not in pos

        # Backtest run field rename → strategy_code
        bt = await raw["backtest_runs"].find_one({"_id": "bt1"})
        assert bt is not None
        assert bt.get("strategy_code") == "hitnrun2"
        assert "strategy_id" not in bt
    finally:
        for coll in (
            "subscriptions",
            "strategy_subscriptions",
            "orders",
            "positions",
            "backtest_runs",
        ):
            await raw[coll].drop()


@pytest.mark.asyncio
async def test_migration_is_idempotent(container, settings: Settings) -> None:
    db = await container.get(Database)
    raw = db.database

    await raw["strategy_subscriptions"].insert_one(
        {"_id": "sub2", "strategy_id": "hitnrun2", "symbol": "BTCUSDT:BINANCE", "interval": "1m"}
    )
    await raw["orders"].insert_one({"_id": "ord2", "strategy_id": "sub2", "status": "filled"})

    try:
        await migrate_strategy_id_fields(container)
        # Second run is a no-op
        await migrate_strategy_id_fields(container)

        sub = await raw["subscriptions"].find_one({"_id": "sub2"})
        assert sub is not None
        assert sub.get("strategy_code") == "hitnrun2"
        assert "strategy_id" not in sub

        ord_doc = await raw["orders"].find_one({"_id": "ord2"})
        assert ord_doc is not None
        assert ord_doc.get("subscription_id") == "sub2"
    finally:
        for coll in ("subscriptions", "strategy_subscriptions", "orders"):
            await raw[coll].drop()


@pytest.mark.asyncio
async def test_aborts_when_both_collections_exist(container, settings: Settings) -> None:
    db = await container.get(Database)
    raw = db.database

    await raw["strategy_subscriptions"].insert_one({"_id": "subA", "strategy_id": "hitnrun2"})
    await raw["subscriptions"].insert_one({"_id": "subB", "strategy_code": "hitnrun2"})

    try:
        with pytest.raises(RuntimeError, match="Both"):
            await migrate_strategy_id_fields(container)
    finally:
        for coll in ("subscriptions", "strategy_subscriptions"):
            await raw[coll].drop()
