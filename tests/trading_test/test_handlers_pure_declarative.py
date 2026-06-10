"""remove_symbol + delete handlers are pure Mongo writes (no engine, no scheduler).

After the app/bff split these handlers must not touch StrategyAppService or
JobScheduler — the stateless bff serves them. They cascade-delete the
subscription, its cached backtest, and any queued backtest requests; the app
control-plane (reconcile orphan-unload) tears down the RAM instance later.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.trading.handlers.strategy.delete.command import DeleteStrategyCommand
from pocketquant.trading.handlers.strategy.delete.handler import DeleteStrategyHandler
from pocketquant.trading.handlers.strategy.remove_symbol.command import RemoveSymbolCommand
from pocketquant.trading.handlers.strategy.remove_symbol.handler import RemoveSymbolHandler

pytestmark = pytest.mark.integration

_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"


@pytest.fixture
async def repos(settings):
    db = Database()
    await db.connect(settings)
    sub_repo = SubscriptionRepository(db)
    bt_repo = BacktestRepository(db)
    request_repo = BacktestRequestRepository(db)
    for coll in ("subscriptions", "backtest_runs", "backtest_requests"):
        await db.get_collection(coll).drop()
    yield sub_repo, bt_repo, request_repo
    for coll in ("subscriptions", "backtest_runs", "backtest_requests"):
        await db.get_collection(coll).drop()
    await db.disconnect()


def _sub(interval: Interval = Interval.HOUR_1) -> Subscription:
    sub_id = Subscription.deterministic_id(_STRATEGY, _SYMBOL, interval)
    return Subscription(
        id=sub_id,
        strategy_code=_STRATEGY,
        symbol=_SYMBOL,
        interval=interval,
        created_at=datetime.now(UTC),
    )


def _queued(sub_id: str) -> BacktestRequest:
    return BacktestRequest(
        id=f"bt:{sub_id}",
        kind="subscription",
        status="pending",
        requested_at=datetime.now(UTC),
        sub_id=sub_id,
        strategy_code=_STRATEGY,
    )


def _has_no_attr(handler: object, *names: str) -> None:
    """Assert the handler carries no engine/scheduler reference."""
    for attr in vars(handler):
        val = getattr(handler, attr)
        cls = type(val).__name__
        assert cls not in names, f"{attr} is a {cls} — handler must not depend on it"


@pytest.mark.asyncio
async def test_remove_symbol_pure_db_delete(repos):
    sub_repo, bt_repo, request_repo = repos
    sub = _sub()
    await sub_repo.add(sub)
    await bt_repo.upsert_status(sub.id, strategy_code=_STRATEGY, status="completed")
    await request_repo.enqueue(_queued(sub.id))

    handler = RemoveSymbolHandler(bt_repo, request_repo, sub_repo)
    _has_no_attr(handler, "StrategyAppService", "JobScheduler")

    await handler.handle(RemoveSymbolCommand(sub_id=sub.id))

    assert await sub_repo.get(sub.id) is None
    assert await bt_repo.get_subscription_status(sub.id) is None
    assert await request_repo.get(f"bt:{sub.id}") is None


@pytest.mark.asyncio
async def test_delete_strategy_cascades_all_subs(repos):
    sub_repo, bt_repo, request_repo = repos
    sub1 = _sub(Interval.HOUR_1)
    sub2 = _sub(Interval.MINUTE_5)
    for s in (sub1, sub2):
        await sub_repo.add(s)
        await bt_repo.upsert_status(s.id, strategy_code=_STRATEGY, status="completed")
        await request_repo.enqueue(_queued(s.id))

    handler = DeleteStrategyHandler(sub_repo, bt_repo, request_repo)
    _has_no_attr(handler, "StrategyAppService", "JobScheduler")

    await handler.handle(DeleteStrategyCommand(strategy_id=_STRATEGY))

    assert await sub_repo.list_by_strategy_code(_STRATEGY) == []
    for s in (sub1, sub2):
        assert await bt_repo.get_subscription_status(s.id) is None
        assert await request_repo.get(f"bt:{s.id}") is None
