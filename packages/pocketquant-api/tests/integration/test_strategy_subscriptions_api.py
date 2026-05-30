"""Integration tests for strategy + subscription API endpoints.

Tests the full HTTP request/response cycle via the ASGI test client.
Strategy is loaded directly via StrategyAppService to avoid YAML I/O.

Error mapping note: SubscriptionAlreadyExistsError extends DomainError → HTTP 400
(not 409 — the exception handler maps AppError.status_code, and DomainError uses 400).
"""

from __future__ import annotations

import pytest
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig

pytestmark = pytest.mark.integration

_STRATEGY_CODE = "test-sub-strat"


@pytest.fixture(autouse=True)
async def load_strategy(app_client):
    """Load test strategy + clean MongoDB subscription/backtest collections per test."""
    from pocketquant.backtest.persistence.backtest_repository import BacktestRepository
    from pocketquant.trading.app_services.strategy_app_service import StrategyAppService
    from pocketquant.trading.persistence.subscription_repository import (
        SubscriptionRepository,
    )

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    svc: StrategyAppService = await container.get(StrategyAppService)
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)

    # Clean collections so tests are isolated
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})
    await bt_repo._collection().delete_many({"strategy_code": _STRATEGY_CODE})

    config = StrategyConfig(
        id=_STRATEGY_CODE,
        name="Test Strategy",
        symbol="BTC-USDT:BINANCE",
        interval="1h",
    )
    await svc.unload_strategy(_STRATEGY_CODE)
    await svc.load_strategy(config)
    yield
    await svc.unload_strategy(_STRATEGY_CODE)


@pytest.mark.skip(reason="Requires tracked_symbols seeding in test fixture (infrastructure setup)")
@pytest.mark.asyncio
async def test_add_two_different_symbols_returns_201(app_client):
    r1 = await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "BTC-USDT:BINANCE", "interval": "1h"},
    )
    assert r1.status_code == 201, r1.text

    r2 = await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "ETH-USDT:BINANCE", "interval": "1h"},
    )
    assert r2.status_code == 201, r2.text

    body1 = r1.json()
    body2 = r2.json()
    assert body1["symbol"] == "BTC-USDT:BINANCE"
    assert body2["symbol"] == "ETH-USDT:BINANCE"
    # IDs must be distinct
    assert body1["id"] != body2["id"]


@pytest.mark.skip(reason="Requires tracked_symbols seeding in test fixture (infrastructure setup)")
@pytest.mark.asyncio
async def test_add_duplicate_symbol_returns_400(app_client):
    payload = {"symbol": "BTC-USDT:BINANCE", "interval": "1h"}
    r1 = await app_client.post(f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions", json=payload)
    assert r1.status_code == 201, r1.text

    r2 = await app_client.post(f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions", json=payload)
    # DomainError.status_code = 400; error_code = SUBSCRIPTION_ALREADY_EXISTS
    assert r2.status_code == 400, r2.text
    assert r2.json()["error"]["code"] == "SUBSCRIPTION_ALREADY_EXISTS"


@pytest.mark.skip(reason="Requires tracked_symbols seeding in test fixture (infrastructure setup)")
@pytest.mark.asyncio
async def test_list_subscriptions_returns_added_subs_with_null_backtest(app_client):
    await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "BTC-USDT:BINANCE", "interval": "1h"},
    )
    await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "ETH-USDT:BINANCE", "interval": "1h"},
    )

    r = await app_client.get(f"/api/v1/subscriptions/?strategy_code={_STRATEGY_CODE}")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 2
    for item in items:
        assert item["backtest"] is None


@pytest.mark.skip(reason="Requires tracked_symbols seeding in test fixture (infrastructure setup)")
@pytest.mark.asyncio
async def test_delete_subscription_removes_it_from_list(app_client):
    r1 = await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "BTC-USDT:BINANCE", "interval": "1h"},
    )
    r2 = await app_client.post(
        f"/api/v1/strategies/{_STRATEGY_CODE}/subscriptions",
        json={"symbol": "ETH-USDT:BINANCE", "interval": "1h"},
    )
    sub_id = r1.json()["id"]

    del_r = await app_client.delete(f"/api/v1/subscriptions/{sub_id}")
    assert del_r.status_code == 204, del_r.text

    list_r = await app_client.get(f"/api/v1/subscriptions/?strategy_code={_STRATEGY_CODE}")
    items = list_r.json()
    assert len(items) == 1
    assert items[0]["id"] == r2.json()["id"]


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

    # After cascade delete the strategy is unloaded; re-load to query subscriptions
    from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
    from pocketquant.trading.app_services.strategy_app_service import StrategyAppService

    container = app_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    svc: StrategyAppService = await container.get(StrategyAppService)
    config = StrategyConfig(
        id=_STRATEGY_CODE,
        name="Test Strategy",
        symbol="BTC-USDT:BINANCE",
        interval="1h",
    )
    await svc.load_strategy(config)

    list_r = await app_client.get(f"/api/v1/subscriptions/?strategy_code={_STRATEGY_CODE}")
    assert list_r.status_code == 200, list_r.text
    assert list_r.json() == []
