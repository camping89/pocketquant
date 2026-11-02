from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

_STRATEGY_CODE = "probe"
_SYMBOL = "BTCUSDT:BINANCE"


# The DELETE and cascade handlers are pure Mongo, so only DB isolation is needed; there is
# no in-RAM StrategyAppService state to reset.
@pytest.fixture(autouse=True)
async def load_strategy(app_client, probe_registry):
    from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
    from pocketquant.core.infra.persistence.repositories.backtest_repository import (
        BacktestRepository,
    )
    from pocketquant.core.infra.persistence.repositories.subscription_repository import (
        SubscriptionRepository,
    )
    from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)
    tracked_repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)
    await tracked_repo.upsert(TrackedSymbol(symbol=_SYMBOL, seeded_from="test"))

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
        json={"symbol": "BTC-USDT:BINANCE", "intervals": ["1h"], "broker": "okx"},
    )

    assert r.status_code == 422, r.text


async def _create(app_client, intervals: list[str], parameters: dict | None = None):
    return await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": _SYMBOL, "intervals": intervals, "parameters": parameters or {}},
    )


@pytest.mark.asyncio
async def test_two_interval_sets_sharing_the_entry_interval_both_create(app_client):
    assert (await _create(app_client, ["15m", "1h"])).status_code == 201
    assert (await _create(app_client, ["15m", "4h"])).status_code == 201
    dup = await _create(app_client, ["15m", "1h"])
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"]["code"] == "SUBSCRIPTION_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_create_rejects_an_unsorted_interval_list(app_client):
    r = await _create(app_client, ["1h", "15m"])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "INVALID_INTERVALS"


@pytest.mark.asyncio
async def test_create_rejects_a_parameter_of_the_wrong_type(app_client):
    r = await _create(app_client, ["1h"], {"min_bars": "3"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "INVALID_PARAMETERS"


@pytest.mark.asyncio
async def test_edit_changes_a_stopped_subscription(app_client):
    created = await _create(app_client, ["15m"])
    sub_id = created.json()["id"]
    r = await app_client.patch(
        f"/api/v1/subscriptions/{sub_id}",
        json={"intervals": ["15m", "1h"], "parameters": {"min_bars": 2}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["intervals"] == ["15m", "1h"]
    assert r.json()["parameters"] == {"min_bars": 2}


@pytest.mark.asyncio
async def test_the_template_serves_its_default_parameters(app_client):
    r = await app_client.get(f"/api/v1/strategies/{_STRATEGY_CODE}")
    assert r.status_code == 200, r.text
    assert r.json()["parameters"] == {"min_bars": 0}


@pytest.mark.asyncio
async def test_close_returns_202_then_409_while_pending(app_client):
    sub_id = (await _create(app_client, ["15m"])).json()["id"]

    first = await app_client.post(f"/api/v1/subscriptions/{sub_id}/close")
    assert first.status_code == 202, first.text
    assert first.json() == {"subscription_id": sub_id, "action": "close"}

    second = await app_client.post(f"/api/v1/subscriptions/{sub_id}/cancel")
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "ACTION_PENDING"


@pytest.mark.asyncio
async def test_cancel_on_a_missing_subscription_is_404(app_client):
    r = await app_client.post("/api/v1/subscriptions/no-such-id/cancel")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_snapshot_is_an_empty_list_before_any_bar(app_client):
    sub_id = (await _create(app_client, ["15m"])).json()["id"]

    r = await app_client.get(f"/api/v1/subscriptions/{sub_id}/snapshot")

    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_orders_limit_is_bounded(app_client):
    sub_id = (await _create(app_client, ["15m"])).json()["id"]

    assert (await app_client.get(f"/api/v1/subscriptions/{sub_id}/orders")).json() == []
    r = await app_client.get(f"/api/v1/subscriptions/{sub_id}/orders?limit=0")
    assert r.status_code == 422, r.text
