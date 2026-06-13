"""Declarative strategy command/query handlers.

Covers the pure-declarative contract of StrategyCommandService /
StrategyQueryService:

- add_symbol persists a uuid7-keyed subscription doc only (no RAM load); the app
  control-plane materializes the runtime instance later. Fail-fast 404s for
  unknown template and untracked symbol. The id-minting + validation branches are
  asserted with mock repos; the real-DB persisted shape is asserted against an
  ephemeral Mongo container.
- start/stop are pure DB writes of desired_state (reconcile converges actual_state
  later); missing subscription raises NotFoundError.
- remove_symbol / delete_strategy cascade-delete the subscription, its cached
  backtest, and queued requests, holding no engine/scheduler reference.
- list_symbols sources run-state from the DB; is_running derives from actual_state.

Handler classes below are thin shims mapping the old Handler(repo) + handle(cmd)
API onto the current command/query services, so the behavioural assertions stay
stable across the service refactor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.common.exceptions import NotFoundError
from pocketquant.core.common.uuid import UUID, generate_id
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
from pocketquant.engine.strategy_command_service import (
    AddSymbolCommand,
    DeleteStrategyCommand,
    RemoveSymbolCommand,
    StartStrategyCommand,
    StopStrategyCommand,
    StrategyCommandService,
)
from pocketquant.engine.strategy_query_service import ListSymbolsQuery


class StartStrategyHandler:
    def __init__(self, subscription_repository: Any) -> None:
        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=MagicMock(),
            backtest_request_repository=MagicMock(),
            tracked_symbol_repository=MagicMock(),
        )

    async def handle(self, request: Any) -> bool:
        return await self._svc.start(request)  # type: ignore[arg-type]


class StopStrategyHandler:
    def __init__(self, subscription_repository: Any) -> None:
        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=MagicMock(),
            backtest_request_repository=MagicMock(),
            tracked_symbol_repository=MagicMock(),
        )

    async def handle(self, request: Any) -> bool:
        return await self._svc.stop(request)  # type: ignore[arg-type]


class AddSymbolHandler:
    def __init__(
        self,
        subscription_repository: Any,
        tracked_symbol_repository: Any,
    ) -> None:
        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=MagicMock(),
            backtest_request_repository=MagicMock(),
            tracked_symbol_repository=tracked_symbol_repository,
        )

    async def handle(self, request: Any) -> dict:
        return await self._svc.add_symbol(request)  # type: ignore[arg-type]


class ListSymbolsHandler:
    def __init__(
        self,
        subscription_repository: Any,
        backtest_repository: Any,
    ) -> None:
        from pocketquant.engine.strategy_query_service import StrategyQueryService

        self._svc = StrategyQueryService(
            subscription_repository=subscription_repository,
            backtest_repository=backtest_repository,
            position_repository=MagicMock(),
        )

    async def handle(self, request: Any) -> list:
        return await self._svc.list_symbols(request)  # type: ignore[arg-type]


class RemoveSymbolHandler:
    """Map old (bt_repo, request_repo, sub_repo) args to StrategyCommandService."""

    def __init__(
        self,
        backtest_repository: Any,
        backtest_request_repository: Any,
        subscription_repository: Any,
    ) -> None:
        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=backtest_repository,
            backtest_request_repository=backtest_request_repository,
            tracked_symbol_repository=MagicMock(),
        )

    async def handle(self, request: RemoveSymbolCommand) -> None:
        await self._svc.remove_symbol(request)


class DeleteStrategyHandler:
    """Map old (sub_repo, bt_repo, request_repo) args to StrategyCommandService."""

    def __init__(
        self,
        subscription_repository: Any,
        backtest_repository: Any,
        backtest_request_repository: Any,
    ) -> None:
        self._svc = StrategyCommandService(
            subscription_repository=subscription_repository,
            backtest_repository=backtest_repository,
            backtest_request_repository=backtest_request_repository,
            tracked_symbol_repository=MagicMock(),
        )

    async def handle(self, request: DeleteStrategyCommand) -> None:
        await self._svc.delete_strategy(request)


_STRATEGY = "hitnrun2"
_SYMBOL = "BTCUSDT:BINANCE"


def _make_sub(
    strategy_code: str = _STRATEGY,
    symbol: str = _SYMBOL,
    interval: Interval = Interval.HOUR_1,
) -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code=strategy_code,
        symbol=symbol,
        interval=interval,
        created_at=datetime.now(UTC),
    )


def _queued(sub_id: str) -> BacktestRequest:
    return BacktestRequest(
        id=generate_id(),
        kind="subscription",
        status="pending",
        requested_at=datetime.now(UTC),
        sub_id=sub_id,
        strategy_code=_STRATEGY,
    )


def _has_no_attr(handler: Any, *names: str) -> None:
    """Assert the handler carries no engine/scheduler reference."""
    for attr in vars(handler):
        val = getattr(handler, attr)
        cls = type(val).__name__
        assert cls not in names, f"{attr} is a {cls} — handler must not depend on it"


@pytest.fixture
async def repo(settings):
    """Single SubscriptionRepository against an ephemeral Mongo container."""
    db = Database()
    await db.connect(settings)
    await db.get_collection(SubscriptionRepository._collection_name).drop()
    r = SubscriptionRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


@pytest.fixture
async def repos(settings):
    """(sub_repo, bt_repo, request_repo) trio for cascade-delete tests."""
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


def _make_mock_add_handler(
    *,
    tracked_exists: bool = True,
) -> tuple[AddSymbolHandler, AsyncMock, AsyncMock]:
    sub_repo = MagicMock()
    sub_repo.add = AsyncMock()

    tracked_repo = MagicMock()
    tracked_repo.exists = AsyncMock(return_value=tracked_exists)

    handler = AddSymbolHandler(
        subscription_repository=sub_repo,
        tracked_symbol_repository=tracked_repo,
    )
    return handler, sub_repo.add, tracked_repo.exists


# --- add_symbol: pure-mock unit assertions (no DB, no container) ---


@pytest.mark.asyncio
async def test_add_symbol_persists_subscription_keyed_by_uuid7() -> None:
    handler, sub_add, _ = _make_mock_add_handler(tracked_exists=True)

    result = await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    sub_add.assert_awaited_once()
    assert sub_add.await_args is not None
    persisted: Any = sub_add.await_args.args[0]
    assert UUID(str(persisted.id)).version == 7
    assert persisted.strategy_code == "hitnrun2"
    assert persisted.desired_state == "stopped"
    assert persisted.actual_state == "stopped"
    assert result["id"] == str(persisted.id)
    assert result["strategy_code"] == "hitnrun2"


@pytest.mark.asyncio
async def test_add_symbol_two_adds_same_triple_get_distinct_ids() -> None:
    """Ids are random per add — dedup is the repo's compound index, not the id."""
    handler, sub_add, _ = _make_mock_add_handler(tracked_exists=True)

    await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )
    await handler.handle(
        AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
    )

    first, second = (call.args[0] for call in sub_add.await_args_list)
    assert first.id != second.id


@pytest.mark.asyncio
async def test_add_symbol_404_when_unknown_template() -> None:
    handler, sub_add, _ = _make_mock_add_handler(tracked_exists=True)

    with pytest.raises(NotFoundError):
        await handler.handle(
            AddSymbolCommand(strategy_id="does-not-exist", symbol="BTCUSDT:BINANCE", interval="1h")
        )

    sub_add.assert_not_called()


@pytest.mark.asyncio
async def test_add_symbol_404_when_symbol_not_tracked() -> None:
    handler, sub_add, _ = _make_mock_add_handler(tracked_exists=False)

    with pytest.raises(NotFoundError) as exc:
        await handler.handle(
            AddSymbolCommand(strategy_id="hitnrun2", symbol="BTCUSDT:BINANCE", interval="1h")
        )
    assert exc.value.error_code == "SYMBOL_NOT_TRACKED"
    sub_add.assert_not_called()


# --- start / stop: desired_state writes against real Mongo ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_handler_writes_running_desired_state(repo):
    sub = _make_sub()
    await repo.add(sub)

    handler = StartStrategyHandler(repo)
    result = await handler.handle(StartStrategyCommand(subscription_id=str(sub.id)))

    assert result is True
    fetched = await repo.get(str(sub.id))
    assert fetched.desired_state == "running"
    assert fetched.actual_state == "stopped"  # reconcile converges later, not here


@pytest.mark.integration
@pytest.mark.asyncio
async def test_start_handler_missing_sub_raises_not_found(repo):
    handler = StartStrategyHandler(repo)
    with pytest.raises(NotFoundError):
        await handler.handle(StartStrategyCommand(subscription_id="does-not-exist"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stop_handler_writes_stopped_desired_state(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(str(sub.id), "running")

    handler = StopStrategyHandler(repo)
    result = await handler.handle(StopStrategyCommand(subscription_id=str(sub.id)))

    assert result is True
    fetched = await repo.get(str(sub.id))
    assert fetched.desired_state == "stopped"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stop_handler_missing_sub_raises_not_found(repo):
    handler = StopStrategyHandler(repo)
    with pytest.raises(NotFoundError):
        await handler.handle(StopStrategyCommand(subscription_id="does-not-exist"))


# --- add_symbol: real-DB persisted shape ---


@pytest.mark.integration
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


# --- list_symbols: run-state sourced from the DB ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_symbols_sources_state_from_db_no_ram_read(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(str(sub.id), "running")
    await repo.update_actual_state(str(sub.id), "running")

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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_symbols_is_running_false_when_actual_stopped(repo):
    sub = _make_sub()
    await repo.add(sub)
    await repo.update_desired_state(str(sub.id), "running")  # desired running, actual still stopped

    bt_repo = MagicMock()
    bt_repo.get_subscription_statuses = AsyncMock(return_value={})

    handler = ListSymbolsHandler(subscription_repository=repo, backtest_repository=bt_repo)
    rows = await handler.handle(ListSymbolsQuery())

    row = rows[0]
    assert row["desired_state"] == "running"
    assert row["actual_state"] == "stopped"
    assert row["is_running"] is False  # converging — actual lags desired


# --- remove_symbol / delete_strategy: cascade DB deletes, no engine reference ---


@pytest.mark.integration
@pytest.mark.asyncio
async def test_remove_symbol_pure_db_delete(repos):
    sub_repo, bt_repo, request_repo = repos
    sub = _make_sub()
    await sub_repo.add(sub)
    await bt_repo.upsert_status(str(sub.id), strategy_code=_STRATEGY, status="completed")
    await request_repo.enqueue(_queued(str(sub.id)))

    handler = RemoveSymbolHandler(bt_repo, request_repo, sub_repo)
    _has_no_attr(handler, "StrategyAppService", "JobScheduler")

    await handler.handle(RemoveSymbolCommand(sub_id=str(sub.id)))

    assert await sub_repo.get(str(sub.id)) is None
    assert await bt_repo.get_subscription_status(str(sub.id)) is None
    assert await request_repo._collection().count_documents({"sub_id": str(sub.id)}) == 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_strategy_cascades_all_subs(repos):
    sub_repo, bt_repo, request_repo = repos
    sub1 = _make_sub(interval=Interval.HOUR_1)
    sub2 = _make_sub(interval=Interval.MINUTE_5)
    for s in (sub1, sub2):
        await sub_repo.add(s)
        await bt_repo.upsert_status(str(s.id), strategy_code=_STRATEGY, status="completed")
        await request_repo.enqueue(_queued(str(s.id)))

    handler = DeleteStrategyHandler(sub_repo, bt_repo, request_repo)
    _has_no_attr(handler, "StrategyAppService", "JobScheduler")

    await handler.handle(DeleteStrategyCommand(strategy_id=_STRATEGY))

    assert await sub_repo.list_by_strategy_code(_STRATEGY) == []
    for s in (sub1, sub2):
        assert await bt_repo.get_subscription_status(str(s.id)) is None
        assert await request_repo._collection().count_documents({"sub_id": str(s.id)}) == 0
