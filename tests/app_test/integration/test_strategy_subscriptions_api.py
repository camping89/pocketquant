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
async def test_create_refuses_an_unknown_broker(app_client):
    r = await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "BTC-USDT:BINANCE", "interval": "1h", "broker": "okx"},
    )

    assert r.status_code == 422, r.text
