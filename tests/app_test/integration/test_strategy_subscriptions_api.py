from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_STRATEGY_CODE = "test-sub-strat"


# The DELETE and cascade handlers are pure Mongo, so only DB isolation is needed; there is
# no in-RAM StrategyAppService state to reset.
@pytest.fixture(autouse=True)
async def load_strategy(app_client):
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
