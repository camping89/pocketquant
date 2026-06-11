"""Declarative control-plane invariants over the HTTP API.

POST start must only flip ``desired_state`` in Mongo — the reconcile loop (not
the request handler) is what changes ``actual_state``. The test app runs with
``enable_jobs=False`` so no reconcile loop is live, making the boundary
observable: after the POST, ``actual_state`` is still ``stopped``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from pocketquant.core.config import Settings
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

pytestmark = pytest.mark.asyncio

_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"


async def test_start_writes_desired_state_only(
    app_client: AsyncClient, settings: Settings
) -> None:
    db = Database()
    await db.connect(settings)
    try:
        await db.get_collection("subscriptions").drop()
        repo = SubscriptionRepository(db)
        await repo.ensure_indexes()

        sub = Subscription(
            id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, Interval.MINUTE_1),
            strategy_code=_STRATEGY,
            symbol=_SYMBOL,
            interval=Interval.MINUTE_1,
            created_at=datetime.now(UTC),
            desired_state="stopped",
            actual_state="stopped",
        )
        await repo.add(sub)

        resp = await app_client.post(f"{settings.api_prefix}/subscriptions/{sub.id}/start")
        assert resp.status_code == 200

        # Declarative boundary: the handler only flips desired_state. actual_state
        # stays stopped because no reconcile loop runs in this test app.
        stored = await repo.get(sub.id)
        assert stored is not None
        assert stored.desired_state == "running"
        assert stored.actual_state == "stopped"
    finally:
        await db.get_collection("subscriptions").drop()
        await db.disconnect()


async def test_serves_seeded_read(app_client: AsyncClient, settings: Settings) -> None:
    db = Database()
    await db.connect(settings)
    try:
        await db.get_collection("subscriptions").drop()
        repo = SubscriptionRepository(db)
        await repo.ensure_indexes()
        sub = Subscription(
            id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, Interval.MINUTE_1),
            strategy_code=_STRATEGY,
            symbol=_SYMBOL,
            interval=Interval.MINUTE_1,
            created_at=datetime.now(UTC),
        )
        await repo.add(sub)

        resp = await app_client.get(
            f"{settings.api_prefix}/subscriptions/", params={"strategy_code": _STRATEGY}
        )
        assert resp.status_code == 200
        ids = [row["id"] for row in resp.json()]
        assert sub.id in ids
    finally:
        await db.get_collection("subscriptions").drop()
        await db.disconnect()
