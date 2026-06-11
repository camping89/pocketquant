"""Pin OrderPositionQueryService behavior.

Covers happy path and NotFoundError for get_order / get_position,
plus list_orders and list_positions shape parity with old handlers.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.trading.orders_positions_service import (
    GetOrderQuery,
    GetPositionQuery,
    ListOrdersQuery,
    ListPositionsQuery,
    OrderPositionQueryService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _order(
    order_id: str = "ord-1",
    subscription_id: str = "sub-1",
    symbol: str = "BTCUSDT:BINANCE",
) -> MagicMock:
    o = MagicMock()
    o.id = order_id
    o.subscription_id = subscription_id
    o.symbol = symbol
    o.side.value = "buy"
    o.order_type.value = "limit"
    o.quantity = 1.0
    o.price = 50000.0
    o.status.value = "pending"
    o.filled_quantity = 0.0
    o.filled_price = None
    return o


def _build_svc(
    *,
    orders: list | None = None,
    get_order_return: object = None,
    position_summary: object = None,
    all_summaries: list | None = None,
) -> OrderPositionQueryService:
    order_svc = MagicMock()
    order_svc.get_order.return_value = get_order_return
    order_svc.get_pending_orders.return_value = orders or []
    order_svc.get_filled_orders.return_value = []

    position_svc = MagicMock()
    position_svc.get_position_summary.return_value = position_summary
    position_svc.get_all_summaries.return_value = all_summaries or []

    return OrderPositionQueryService(
        order_app_service=order_svc,
        position_app_service=position_svc,
    )


# ---------------------------------------------------------------------------
# get_order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_order_returns_dict() -> None:
    o = _order()
    svc = _build_svc(get_order_return=o)

    result = await svc.get_order(GetOrderQuery(order_id="ord-1"))

    assert result["id"] == "ord-1"
    assert result["subscription_id"] == "sub-1"
    assert result["symbol"] == "BTCUSDT:BINANCE"
    assert result["side"] == "buy"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_get_order_raises_not_found_when_missing() -> None:
    svc = _build_svc(get_order_return=None)

    with pytest.raises(NotFoundError):
        await svc.get_order(GetOrderQuery(order_id="missing"))


# ---------------------------------------------------------------------------
# list_orders
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_orders_combines_pending_and_filled() -> None:
    o1 = _order("ord-1")
    o2 = _order("ord-2")

    order_svc = MagicMock()
    order_svc.get_pending_orders.return_value = [o1]
    order_svc.get_filled_orders.return_value = [o2]
    position_svc = MagicMock()
    position_svc.get_all_summaries.return_value = []

    svc = OrderPositionQueryService(
        order_app_service=order_svc,
        position_app_service=position_svc,
    )

    result = await svc.list_orders(ListOrdersQuery())

    assert len(result) == 2
    ids = {r["id"] for r in result}
    assert ids == {"ord-1", "ord-2"}


@pytest.mark.asyncio
async def test_list_orders_returns_empty_when_none() -> None:
    svc = _build_svc()
    result = await svc.list_orders(ListOrdersQuery())
    assert result == []


# ---------------------------------------------------------------------------
# get_position
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_position_returns_summary() -> None:
    summary = {"strategy_id": "strat-1", "pnl": 100.0}
    svc = _build_svc(position_summary=summary)

    result = await svc.get_position(GetPositionQuery(strategy_id="strat-1"))

    assert result == summary


@pytest.mark.asyncio
async def test_get_position_raises_not_found_when_missing() -> None:
    svc = _build_svc(position_summary=None)

    with pytest.raises(NotFoundError):
        await svc.get_position(GetPositionQuery(strategy_id="missing"))


# ---------------------------------------------------------------------------
# list_positions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_positions_delegates_to_app_service() -> None:
    summaries = [{"strategy_id": "s1"}, {"strategy_id": "s2"}]
    svc = _build_svc(all_summaries=summaries)

    result = await svc.list_positions(ListPositionsQuery())

    assert result == summaries


@pytest.mark.asyncio
async def test_list_positions_returns_empty_when_none() -> None:
    svc = _build_svc(all_summaries=[])
    assert await svc.list_positions(ListPositionsQuery()) == []
