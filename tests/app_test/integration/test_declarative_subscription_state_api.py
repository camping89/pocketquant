# POST start only flips desired_state; the reconcile loop changes actual_state. The app runs
# with app_roles="api", so no reconcile loop is live and actual_state stays stopped after
# the POST.

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from pocketquant.core.common.uuid import generate_id
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


async def test_start_writes_desired_state_only(app_client: AsyncClient, settings: Settings) -> None:
    db = Database()
    await db.connect(settings)
    try:
        await db.get_collection("subscriptions").drop()
        repo = SubscriptionRepository(db)
        await repo.ensure_indexes()

        sub = Subscription(
            id=generate_id(),
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
        stored = await repo.get(str(sub.id))
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
            id=generate_id(),
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
        assert str(sub.id) in ids
    finally:
        await db.get_collection("subscriptions").drop()
        await db.disconnect()
