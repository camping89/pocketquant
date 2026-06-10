"""Tests for migrate_subscription_desired_state — boot-time desired/actual backfill.

Legacy subscription docs (no desired_state) auto-resume: backfilled to
desired_state="running", actual_state="stopped" (reconcile converges to running
on first tick). Modern docs that already carry desired_state are untouched.
Idempotent: only docs lacking desired_state are written.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide

from pocketquant.app.main_extensions import migrate_subscription_desired_state
from pocketquant.core.config import Settings
from pocketquant.core.infra.persistence.mongodb import Database


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


def _legacy_doc(doc_id: str, symbol: str, interval: str) -> dict:
    """Pre-migration subscription shape — no desired_state/actual_state keys."""
    return {
        "_id": doc_id,
        "strategy_code": "hitnrun2",
        "symbol": symbol,
        "interval": interval,
    }


@pytest.mark.asyncio
async def test_backfills_legacy_and_preserves_modern(container, settings: Settings) -> None:
    db = await container.get(Database)
    raw = db.database

    await raw["subscriptions"].insert_many(
        [
            _legacy_doc("legacy1", "BTCUSDT:BINANCE", "1m"),
            _legacy_doc("legacy2", "ETHUSDT:BINANCE", "5m"),
            {
                **_legacy_doc("modern1", "SOLUSDT:BINANCE", "1h"),
                "desired_state": "stopped",
                "actual_state": "stopped",
            },
        ]
    )

    await migrate_subscription_desired_state(container)

    legacy1 = await raw["subscriptions"].find_one({"_id": "legacy1"})
    assert legacy1["desired_state"] == "running"
    assert legacy1["actual_state"] == "stopped"

    legacy2 = await raw["subscriptions"].find_one({"_id": "legacy2"})
    assert legacy2["desired_state"] == "running"
    assert legacy2["actual_state"] == "stopped"

    # Modern doc keeps its explicit (human) state — not flipped to running.
    modern1 = await raw["subscriptions"].find_one({"_id": "modern1"})
    assert modern1["desired_state"] == "stopped"


@pytest.mark.asyncio
async def test_idempotent_second_run_no_changes(container, settings: Settings) -> None:
    db = await container.get(Database)
    raw = db.database

    await raw["subscriptions"].insert_one(_legacy_doc("legacy1", "BTCUSDT:BINANCE", "1m"))

    await migrate_subscription_desired_state(container)
    # Simulate a human stopping it after the first migration.
    await raw["subscriptions"].update_one(
        {"_id": "legacy1"}, {"$set": {"desired_state": "stopped"}}
    )
    # Second run must NOT re-flip to running (doc already has desired_state).
    await migrate_subscription_desired_state(container)

    doc = await raw["subscriptions"].find_one({"_id": "legacy1"})
    assert doc["desired_state"] == "stopped"
