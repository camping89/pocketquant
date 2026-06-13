"""Integration test for strategy-delete subscription cascade via the HTTP API.

Exercises the full request/response cycle through the ASGI test client: a
DELETE on a strategy must clear all its subscriptions from Mongo, observable
via the subscriptions list endpoint reading straight from the DB.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_STRATEGY_CODE = "test-sub-strat"


@pytest.fixture(autouse=True)
async def load_strategy(app_client):
    """Clean MongoDB subscription/backtest collections per test.

    The DELETE + cascade handlers are pure Mongo, so only DB isolation is
    needed here — no in-RAM StrategyAppService state to reset.
    """
    from pocketquant.core.infra.persistence.repositories.backtest_repository import (
        BacktestRepository,
    )
    from pocketquant.core.infra.persistence.repositories.subscription_repository import (
        SubscriptionRepository,
    )

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)

    # Clean collections so tests are isolated
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})
    await bt_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})
    yield
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})
    await bt_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})


@pytest.mark.asyncio
async def test_delete_strategy_clears_all_subscriptions(app_client):
    await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "BTC-USDT:BINANCE", "interval": "1h"},
    )
    await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "ETH-USDT:BINANCE", "interval": "1h"},
    )

    del_r = await app_client.delete(f"/api/v1/strategies/{_STRATEGY_CODE}")
    assert del_r.status_code == 204, del_r.text

    # Delete is a pure Mongo cascade — it does NOT unload the RAM instance (the
    # control-plane reconcile orphan-unload does that out of band). Listing reads
    # straight from Mongo, so no re-load is needed to verify the subs are gone.
    list_r = await app_client.get(f"/api/v1/subscriptions/?strategy_code={_STRATEGY_CODE}")
    assert list_r.status_code == 200, list_r.text
    assert list_r.json() == []
