"""Declarative strategy handlers — start/stop write desired_state, list reads actual_state.

Integration: real SubscriptionRepository against an ephemeral Mongo container so
the desired/actual contract is proven end-to-end. start/stop are pure DB writes
(no StrategyAppService); add_symbol persists desired_state="stopped" and loads an
instance without auto-starting; list_symbols sources run-state from the DB.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.add_symbol.command import AddSymbolCommand
from pocketquant.trading.handlers.strategy.add_symbol.handler import AddSymbolHandler
from pocketquant.trading.handlers.strategy.list_symbols.handler import ListSymbolsHandler
from pocketquant.trading.handlers.strategy.list_symbols.query import ListSymbolsQuery
from pocketquant.trading.handlers.strategy.start.command import StartStrategyCommand
from pocketquant.trading.handlers.strategy.start.handler import StartStrategyHandler
from pocketquant.trading.handlers.strategy.stop.command import StopStrategyCommand
from pocketquant.trading.handlers.strategy.stop.handler import StopStrategyHandler

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(SubscriptionRepository._collection_name).drop()
    r = SubscriptionRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


def _make_sub(strategy_code: str = "hitnrun2", symbol: str = "BTCUSDT:BINANCE") -> Subscription:
    sub_id = Subscription.deterministic_id(strategy_code, symbol, Interval.HOUR_1)
    return Subscription(
        id=sub_id,
        strategy_code=strategy_code,
        symbol=symbol,
        interval=Interval.HOUR_1,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_start_handler_writes_running_desired_state(repo):
    sub = _make_sub()
    await repo.add(sub)

    handler = StartStrategyHandler(repo)
    result = await handler.handle(StartStrategyCommand(subscription_id=sub.id))

    assert result is True
    fetched = await repo.get(sub.id)
    assert fetched.desired_state == "running"
    assert fetched.actual_state == "stopped"  # reconcile converges later, not here


@pytest.mark.asyncio
async def test_start_handler_missing_sub_raises_not_found(repo):
    handler = StartStrategyHandler(repo)
    with pytest.raises(NotFoundError):
        await handler.handle(StartStrategyCommand(subscription_id="does-not-exist"))


@pytest.mark.asyncio
async def test_stop_handler_writes_stopped_desired_state(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(sub.id, "running")

    handler = StopStrategyHandler(repo)
    result = await handler.handle(StopStrategyCommand(subscription_id=sub.id))

    assert result is True
    fetched = await repo.get(sub.id)
    assert fetched.desired_state == "stopped"


@pytest.mark.asyncio
async def test_stop_handler_missing_sub_raises_not_found(repo):
    handler = StopStrategyHandler(repo)
    with pytest.raises(NotFoundError):
        await handler.handle(StopStrategyCommand(subscription_id="does-not-exist"))


@pytest.mark.asyncio
async def test_add_symbol_persists_stopped_pure_db_write(repo):
    """add_symbol is a pure Mongo write — no engine, no RAM load. The app
    control-plane materializes the instance later; the handler only persists."""
    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=True)

    handler = AddSymbolHandler(
        subscription_repository=repo,
        tracked_symbol_repository=tracked_repo,
    )

    result = await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    fetched = await repo.get(result["id"])
    assert fetched.desired_state == "stopped"
    assert fetched.actual_state == "stopped"


@pytest.mark.asyncio
async def test_list_symbols_sources_state_from_db_no_ram_read(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(sub.id, "running")
    await repo.update_actual_state(sub.id, "running")

    bt_repo = MagicMock()
    bt_repo.get_subscription_statuses = AsyncMock(return_value={})

    # No strategy_service dependency — handler must not need RAM to report state.
    handler = ListSymbolsHandler(subscription_repository=repo, backtest_repository=bt_repo)

    rows = await handler.handle(ListSymbolsQuery())

    assert len(rows) == 1
    row = rows[0]
    assert row["desired_state"] == "running"
    assert row["actual_state"] == "running"
    assert row["is_running"] is True  # derived from actual_state, not RAM


@pytest.mark.asyncio
async def test_list_symbols_is_running_false_when_actual_stopped(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(sub.id, "running")  # desired running, actual still stopped

    bt_repo = MagicMock()
    bt_repo.get_subscription_statuses = AsyncMock(return_value={})

    handler = ListSymbolsHandler(subscription_repository=repo, backtest_repository=bt_repo)
    rows = await handler.handle(ListSymbolsQuery())

    row = rows[0]
    assert row["desired_state"] == "running"
    assert row["actual_state"] == "stopped"
    assert row["is_running"] is False  # converging — actual lags desired
