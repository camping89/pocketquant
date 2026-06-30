"""HTTP API for the research workbench reads.

Covers two additive endpoints:
- ``GET /backtest/{run_id}/orders`` — orders with embedded fills + events, keyed
  by ``order_id`` (NOT the Mongo ``_id`` leak).
- ``GET /backtest/strategy/{id}?symbol=&interval=`` — history scoped by the
  composite symbol; the DTO carries symbol/interval/date_range.

Seeds documents straight through the repositories so the tests stay independent
of the engine replay path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import AsyncClient

from pocketquant.core.common.uuid import generate_id, generate_id_str
from pocketquant.core.config import Settings
from pocketquant.core.domain.backtest import BacktestResult, Fill, Order
from pocketquant.core.domain.brokers.events import OrderEvent
from pocketquant.core.domain.order import OrderSide, OrderStatus, OrderType
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def _finished_run(strategy_code: str, symbol: str, interval: str) -> BacktestResult:
    run = BacktestResult.started(
        generate_id_str(),
        {"strategy_code": strategy_code, "symbol": symbol, "interval": interval},
    )
    run.status = "finished"
    return run


def _order_with_fill_and_event(run_id: str, symbol: str) -> Order:
    order_id = generate_id()
    return Order(
        order_id=order_id,
        run_id=run_id,
        strategy_code="hitnrun2",
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=0.5,
        price=None,
        sl_price=64000.0,
        tp_price=67000.0,
        status=OrderStatus.FILLED,
        submitted_at=NOW,
        last_updated_at=NOW,
        events=[
            OrderEvent(
                timestamp=NOW,
                from_status=OrderStatus.SUBMITTED,
                to_status=OrderStatus.FILLED,
                reason="market_fill",
            )
        ],
        fills=[
            Fill(
                fill_id=generate_id(),
                order_id=str(order_id),
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=0.5,
                price=65000.0,
                commission=0.65,
                slippage=0.0,
                timestamp=NOW,
            )
        ],
        resulting_trade_id="trade-123",
    )


async def _seed_run_with_orders(settings: Settings, *, with_orders: bool) -> str:
    db = Database()
    await db.connect(settings)
    try:
        run = _finished_run("hitnrun2", "BTCUSDT:BINANCE", "1m")
        run_id = str(run.id)
        await BacktestRepository(db).save(run)
        if with_orders:
            await BacktestOrderRepository(db).save_many(
                [_order_with_fill_and_event(run_id, "BTCUSDT:BINANCE")]
            )
        return run_id
    finally:
        await db.disconnect()


async def test_orders_endpoint_returns_fills_and_events_keyed_by_order_id(
    app_client: AsyncClient, settings: Settings
) -> None:
    run_id = await _seed_run_with_orders(settings, with_orders=True)

    resp = await app_client.get(f"{settings.api_prefix}/backtest/{run_id}/orders")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["run_id"] == run_id
    assert len(body["orders"]) == 1

    order = body["orders"][0]
    # DTO must expose order_id and never leak the Mongo _id key.
    assert "order_id" in order
    assert "_id" not in order
    UUID(order["order_id"])
    assert order["resulting_trade_id"] == "trade-123"
    assert len(order["fills"]) == 1
    assert "_id" not in order["fills"][0]
    assert order["fills"][0]["fill_id"]
    assert len(order["events"]) == 1
    assert order["events"][0]["to_status"]


async def test_orders_endpoint_empty_when_run_has_no_orders(
    app_client: AsyncClient, settings: Settings
) -> None:
    run_id = await _seed_run_with_orders(settings, with_orders=False)

    resp = await app_client.get(f"{settings.api_prefix}/backtest/{run_id}/orders")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"run_id": run_id, "orders": []}


async def test_strategy_history_filters_by_composite_symbol(
    app_client: AsyncClient, settings: Settings
) -> None:
    # Unique strategy_code isolates this assertion from other tests sharing the
    # session-scoped DB (app integration tests don't drop collections per-test).
    strategy = "scope_filter_strat"
    db = Database()
    await db.connect(settings)
    try:
        repo = BacktestRepository(db)
        await repo.save(_finished_run(strategy, "BTCUSDT:BINANCE", "1m"))
        await repo.save(_finished_run(strategy, "ETHUSDT:BINANCE", "1m"))
    finally:
        await db.disconnect()

    resp = await app_client.get(
        f"{settings.api_prefix}/backtest/strategy/{strategy}",
        params={"symbol": "BTCUSDT:BINANCE", "interval": "1m"},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "BTCUSDT:BINANCE"
    assert row["interval"] == "1m"
    assert "date_range" in row
    assert {"start", "end"} <= set(row["date_range"].keys())
    assert "verdict" in row
