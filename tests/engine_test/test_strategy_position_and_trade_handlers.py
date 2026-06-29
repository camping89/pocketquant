"""Unit tests for GetStrategyPositionsHandler and GetStrategyTradesHandler."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.core.domain.position.entities import PositionAggregate
from pocketquant.core.domain.position.enums import PositionSide
from pocketquant.engine.strategy_query_service import (
    GetStrategyPositionsQuery,
    GetStrategyTradesQuery,
)


class GetStrategyPositionsHandler:
    """Shim: map old Handler(position_repository) + handle(query) to StrategyQueryService."""

    def __init__(self, position_repository: Any) -> None:
        from unittest.mock import MagicMock

        from pocketquant.engine.strategy_query_service import StrategyQueryService

        self._svc = StrategyQueryService(
            subscription_repository=MagicMock(),
            position_repository=position_repository,
        )

    async def handle(self, request: Any) -> list[dict]:
        return await self._svc.get_positions(request)  # type: ignore[arg-type]


class GetStrategyTradesHandler:
    """Shim: map old Handler(position_repository) + handle(query) to StrategyQueryService."""

    def __init__(self, position_repository: Any) -> None:
        from unittest.mock import MagicMock

        from pocketquant.engine.strategy_query_service import StrategyQueryService

        self._svc = StrategyQueryService(
            subscription_repository=MagicMock(),
            position_repository=position_repository,
        )

    async def handle(self, request: Any) -> list[dict]:
        return await self._svc.get_trades(request)  # type: ignore[arg-type]


def _open_position(subscription_id: str = "strat-1") -> PositionAggregate:
    return PositionAggregate(
        id=uuid5(NAMESPACE_OID, "pos-open"),
        subscription_id=subscription_id,
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=2.0,
        current_price=110.0,  # unrealized = (110-100)*2 = 20
        opened_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        sl_price=95.0,
        tp_price=120.0,
    )


def _closed_position(idx: int, *, subscription_id: str = "strat-1") -> PositionAggregate:
    return PositionAggregate(
        id=uuid5(NAMESPACE_OID, f"pos-closed-{idx}"),
        subscription_id=subscription_id,
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.SHORT,
        entry_price=200.0,
        quantity=0.0,  # closed
        current_price=180.0,  # exit price set on close
        realized_pnl=20.0,
        is_closed=True,
        opened_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
        closed_at=datetime(2026, 5, 1, 11, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_positions_handler_returns_open_only_as_dicts() -> None:
    repo = MagicMock()
    repo.find_open_by_subscription = AsyncMock(return_value=[_open_position()])

    handler = GetStrategyPositionsHandler(position_repository=repo)
    result = await handler.handle(GetStrategyPositionsQuery(subscription_id="strat-1"))

    repo.find_open_by_subscription.assert_awaited_once_with("strat-1")
    assert len(result) == 1
    row = result[0]
    assert row["symbol"] == "BTCUSDT:BINANCE"
    assert row["direction"] == "LONG"
    assert row["entry_price"] == 100.0
    assert row["quantity"] == 2.0
    assert row["unrealized_pnl"] == 20.0
    assert row["sl_price"] == 95.0
    assert row["tp_price"] == 120.0
    assert row["entry_time"].startswith("2026-05-01T12:00")


@pytest.mark.asyncio
async def test_positions_handler_returns_empty_list_when_none_open() -> None:
    repo = MagicMock()
    repo.find_open_by_subscription = AsyncMock(return_value=[])

    handler = GetStrategyPositionsHandler(position_repository=repo)
    result = await handler.handle(GetStrategyPositionsQuery(subscription_id="strat-1"))

    assert result == []


@pytest.mark.asyncio
async def test_trades_handler_maps_closed_positions_to_strategy_trade_shape() -> None:
    repo = MagicMock()
    repo.find_closed_by_subscription = AsyncMock(
        return_value=[_closed_position(1), _closed_position(2)]
    )

    handler = GetStrategyTradesHandler(position_repository=repo)
    result = await handler.handle(GetStrategyTradesQuery(subscription_id="strat-1", limit=50))

    repo.find_closed_by_subscription.assert_awaited_once_with("strat-1", limit=50)
    assert len(result) == 2
    row = result[0]
    assert row["id"] == str(uuid5(NAMESPACE_OID, "pos-closed-1"))
    assert row["direction"] == "SHORT"
    assert row["entry_price"] == 200.0
    assert row["exit_price"] == 180.0
    assert row["pnl"] == 20.0
    assert row["entry_time"].startswith("2026-05-01T10:00")
    assert row["exit_time"].startswith("2026-05-01T11:00")


@pytest.mark.asyncio
async def test_trades_handler_empty_when_no_closed_positions() -> None:
    repo = MagicMock()
    repo.find_closed_by_subscription = AsyncMock(return_value=[])

    handler = GetStrategyTradesHandler(position_repository=repo)
    result = await handler.handle(GetStrategyTradesQuery(subscription_id="strat-1"))

    assert result == []
