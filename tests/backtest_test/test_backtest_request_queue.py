"""Backtest request queue — repo atomic claim + worker dispatch round-trips.

Covers the queue mechanism that replaced APScheduler bt:* jobs:
  - enqueue → pending; claim_next atomic flip → running; 2nd claim → None.
  - dedup re-enqueue: (sub_id, status=pending) upsert collapses concurrent
    fan-outs to one pending doc per subscription (partial unique index).
  - cleanup-on-enqueue: terminal done/failed docs for the sub are dropped.
  - single-kind requests are independent — never deduped.
  - worker subscription dispatch → backtest_runs result + request done.
  - worker single dispatch → request doc carries embedded FE result + done.
  - per-request failure isolation: one bad request, the next still runs.
  - stale running reclaim → back to pending.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio

from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.common.uuid import UUID, generate_id
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.brokers.interfaces import IBroker
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.infra.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler

_STRATEGY = "hitnrun2"  # must be in STRATEGY_REGISTRY
_SYMBOL = "BTCUSDT:BINANCE"
_INTERVAL = "1h"


@pytest.fixture(autouse=True)
def _reset_sim() -> Iterator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


def _request(kind: str, **kwargs) -> BacktestRequest:
    return BacktestRequest(
        id=kwargs.pop("id", generate_id()),
        kind=kind,  # type: ignore[arg-type]
        status="pending",
        requested_at=kwargs.pop("requested_at", datetime.now(UTC)),
        **kwargs,
    )


def _synthetic_bars(n: int = 60) -> list[Bar]:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    price = 40_000.0
    bars: list[Bar] = []
    for i in range(n):
        bars.append(
            Bar(
                symbol=_SYMBOL,
                interval=Interval.HOUR_1,
                datetime=base + timedelta(hours=i),
                open=price,
                high=price * 1.002,
                low=price * 0.998,
                close=price * 1.001,
                volume=10.0 + i,
                tick_count=60,
            )
        )
        price *= 1.0005
    return bars


@pytest_asyncio.fixture
async def request_repo(database: Database) -> AsyncIterator[BacktestRequestRepository]:
    repo = BacktestRequestRepository(database)
    # The partial unique index on (sub_id, status=pending) is the DB-level
    # dedup guarantee the enqueue tests below exercise.
    await repo.ensure_indexes()
    try:
        yield repo
    finally:
        await database.get_collection("backtest_requests").drop()


# ---------------------------------------------------------------------------
# Repo-level: atomic claim + idempotent enqueue + stale reclaim
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_then_claim_is_atomic(request_repo: BacktestRequestRepository) -> None:
    req = _request("single", config={"strategy_code": _STRATEGY})
    await request_repo.enqueue(req)

    stored = await request_repo.get(str(req.id))
    assert stored is not None
    assert stored.status == "pending"

    claimed = await request_repo.claim_next()
    assert claimed is not None
    assert claimed.id == req.id
    assert claimed.status == "running"
    assert claimed.started_at is not None

    # Second claim finds nothing pending — the doc was atomically flipped.
    assert await request_repo.claim_next() is None


@pytest.mark.asyncio
async def test_claim_orders_by_requested_at(request_repo: BacktestRequestRepository) -> None:
    older = _request("single", requested_at=datetime(2024, 1, 1, tzinfo=UTC))
    newer = _request("single", requested_at=datetime(2024, 6, 1, tzinfo=UTC))
    await request_repo.enqueue(newer)
    await request_repo.enqueue(older)

    first = await request_repo.claim_next()
    assert first is not None and first.id == older.id


@pytest.mark.asyncio
async def test_subscription_request_id_is_uuid(
    request_repo: BacktestRequestRepository,
) -> None:
    req = _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    returned_id = await request_repo.enqueue(req)

    doc = await request_repo._collection().find_one({"sub_id": "sub1"})
    assert doc is not None
    assert doc["_id"] == returned_id
    assert UUID(doc["_id"]).version == 7
    assert not doc["_id"].startswith("bt:")


@pytest.mark.asyncio
async def test_subscription_reenqueue_collapses_to_one_pending(
    request_repo: BacktestRequestRepository,
) -> None:
    """Re-enqueue while a pending doc exists resets it in place — one pending
    per subscription, same idempotency the old deterministic-id upsert gave."""
    first_id = await request_repo.enqueue(
        _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    )
    second_id = await request_repo.enqueue(
        _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    )

    assert second_id == first_id  # collapsed onto the existing pending doc
    coll = request_repo._collection()
    assert await coll.count_documents({"sub_id": "sub1", "status": "pending"}) == 1


@pytest.mark.asyncio
async def test_concurrent_enqueue_single_pending_no_exception(
    request_repo: BacktestRequestRepository,
) -> None:
    """Two racing enqueues for the same sub: the partial unique index makes
    one upsert lose; the repo absorbs the DuplicateKeyError — callers always
    get an id, and exactly one pending doc exists."""
    reqs = [_request("subscription", sub_id="sub1", strategy_code=_STRATEGY) for _ in range(2)]
    ids = await asyncio.gather(*(request_repo.enqueue(r) for r in reqs))

    coll = request_repo._collection()
    docs = await coll.find({"sub_id": "sub1", "status": "pending"}).to_list(length=10)
    assert len(docs) == 1
    assert set(ids) == {docs[0]["_id"]}


@pytest.mark.asyncio
async def test_enqueue_cleans_terminal_docs_for_sub(
    request_repo: BacktestRequestRepository,
) -> None:
    """A fresh enqueue drops the sub's done/failed history — storage stays
    bounded at one generation of terminal docs per subscription."""
    first_id = await request_repo.enqueue(
        _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    )
    await request_repo.claim_next()
    await request_repo.mark_done(first_id)

    second_id = await request_repo.enqueue(
        _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    )

    coll = request_repo._collection()
    docs = await coll.find({"sub_id": "sub1"}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["_id"] == second_id
    assert docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_single_kind_requests_never_deduped(
    request_repo: BacktestRequestRepository,
) -> None:
    """Ad-hoc single runs are independent work items — two enqueues, two docs."""
    await request_repo.enqueue(_request("single", config={"strategy_code": _STRATEGY}))
    await request_repo.enqueue(_request("single", config={"strategy_code": _STRATEGY}))

    coll = request_repo._collection()
    assert await coll.count_documents({"kind": "single", "status": "pending"}) == 2


@pytest.mark.asyncio
async def test_mark_done_and_failed(request_repo: BacktestRequestRepository) -> None:
    req = _request("single")
    await request_repo.enqueue(req)
    await request_repo.claim_next()

    await request_repo.mark_done(str(req.id), result={"run_id": "x", "status": "completed"})
    done = await request_repo.get(str(req.id))
    assert done is not None and done.status == "done"
    assert done.result == {"run_id": "x", "status": "completed"}
    assert done.finished_at is not None

    other = _request("single")
    await request_repo.enqueue(other)
    await request_repo.claim_next()
    await request_repo.mark_failed(str(other.id), "boom")
    failed = await request_repo.get(str(other.id))
    assert failed is not None and failed.status == "failed"
    assert failed.error == "boom"


@pytest.mark.asyncio
async def test_reclaim_stale_running(request_repo: BacktestRequestRepository) -> None:
    req = _request("single")
    await request_repo.enqueue(req)
    claimed = await request_repo.claim_next()
    assert claimed is not None

    # Backdate started_at past the staleness threshold.
    await request_repo._collection().update_one(
        {"_id": str(req.id)},
        {"$set": {"started_at": datetime.now(UTC) - timedelta(minutes=30)}},
    )

    reclaimed = await request_repo.reclaim_stale_running(threshold_minutes=10)
    assert reclaimed == 1
    back = await request_repo.get(str(req.id))
    assert back is not None and back.status == "pending"
    # A fresh claim picks it up again.
    assert (await request_repo.claim_next()) is not None


@pytest.mark.asyncio
async def test_fresh_running_not_reclaimed(request_repo: BacktestRequestRepository) -> None:
    req = _request("single")
    await request_repo.enqueue(req)
    await request_repo.claim_next()
    assert await request_repo.reclaim_stale_running(threshold_minutes=10) == 0


@pytest.mark.asyncio
async def test_reclaim_with_newer_pending_marks_stale_failed(
    request_repo: BacktestRequestRepository,
) -> None:
    """Stale running + newer pending for the same sub: flipping the stale doc
    back to pending would collide in the unique index. The sweep must not
    raise — the newer request supersedes, the stale doc is marked failed."""
    stale = _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    await request_repo.enqueue(stale)
    claimed = await request_repo.claim_next()
    assert claimed is not None
    await request_repo._collection().update_one(
        {"_id": str(claimed.id)},
        {"$set": {"started_at": datetime.now(UTC) - timedelta(minutes=30)}},
    )

    # Enqueue while the stale one is "running" → a second, pending doc.
    pending_id = await request_repo.enqueue(
        _request("subscription", sub_id="sub1", strategy_code=_STRATEGY)
    )
    assert pending_id != str(claimed.id)

    swept = await request_repo.reclaim_stale_running(threshold_minutes=10)
    assert swept == 1

    coll = request_repo._collection()
    stale_doc = await coll.find_one({"_id": str(claimed.id)})
    assert stale_doc is not None and stale_doc["status"] == "failed"
    assert await coll.count_documents({"sub_id": "sub1", "status": "pending"}) == 1
    # The queue keeps draining — the pending doc is claimable.
    next_claim = await request_repo.claim_next()
    assert next_claim is not None and str(next_claim.id) == pending_id


# ---------------------------------------------------------------------------
# Worker dispatch: subscription + single round-trips against real engine
# ---------------------------------------------------------------------------


class _StubBrokerFactory:
    """Returns the pre-wired broker; the engine never asks the factory again."""

    def __init__(self, broker: IBroker) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBroker:
        return self._broker


@pytest_asyncio.fixture
async def engine_setup(database: Database):
    """Seed bars + a real engine with the base strategy config in memory.

    The subscription-backtest dispatch reads ``get_config(strategy_code)`` and
    builds its own synthetic-id PaperBroker, so the base config must be
    registered. Mirrors the construction in test_hitnrun2_backtest.
    """
    bar_repo = BarRepository(database)
    bt_repo = BacktestRepository(database)
    order_repo = BacktestOrderRepository(database)
    trade_repo = BacktestTradeRepository(database)
    sub_repo = SubscriptionRepository(database)
    event_bus = EventBus(max_history=100)

    await bar_repo.insert_many(_synthetic_bars(), source="test")

    order_svc = OrderAppService(event_bus, OrderRepository(database))
    await order_svc.load_pending_orders()
    position_svc = PositionAppService(event_bus, PositionRepository(database))
    await position_svc.start()

    base_broker = PaperBroker(initial_balance=10_000.0, slippage_percent=0.0, event_bus=event_bus)
    strategy_service = StrategyAppService(
        event_bus=event_bus,
        broker_factory=_StubBrokerFactory(base_broker),  # type: ignore[arg-type]
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
    )
    await strategy_service.start()

    base_cfg = StrategyConfig(
        id=_STRATEGY,
        name=_STRATEGY,
        symbol=_SYMBOL,
        interval=_INTERVAL,
        trigger="bar",
        broker="paper",
        parameters={
            "entry_lookback_bars": 10,
            "sl_lookback_bars": 20,
            "tp_lookback_bars": 5,
        },
    )
    from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY

    base_instance = STRATEGY_REGISTRY[_STRATEGY](base_cfg)
    await strategy_service.inject_prepared_strategy(_STRATEGY, base_instance, base_broker, base_cfg)

    deps = BacktestDispatchDeps(
        event_bus=event_bus,
        bar_repo=bar_repo,
        backtest_repo=bt_repo,
        order_repo=order_repo,
        trade_repo=trade_repo,
        strategy_app_service=strategy_service,
        subscription_repo=sub_repo,
    )

    try:
        yield deps, sub_repo, bt_repo
    finally:
        await strategy_service.stop()
        for coll in (
            "backtest_runs",
            "backtest_orders",
            "backtest_trades",
            "bars",
            "subscriptions",
            "backtest_requests",
            "orders",
            "positions",
        ):
            try:
                await database.get_collection(coll).drop()
            except Exception:  # noqa: BLE001
                pass


@pytest.mark.asyncio
async def test_worker_dispatches_subscription(database: Database, engine_setup) -> None:
    deps, sub_repo, bt_repo = engine_setup
    request_repo = BacktestRequestRepository(database)

    sub = Subscription(
        id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, _INTERVAL),
        strategy_code=_STRATEGY,
        symbol=_SYMBOL,
        interval=Interval(_INTERVAL),
        created_at=datetime.now(UTC),
    )
    await sub_repo.add(sub)

    req = _request("subscription", sub_id=sub.id, strategy_code=_STRATEGY)
    await request_repo.enqueue(req)

    worker = BacktestRequestWorker(request_repo, deps)
    processed = await worker._drain_once()
    assert processed is True

    done = await request_repo.get(str(req.id))
    assert done is not None and done.status == "done"

    status = await bt_repo.get_subscription_status(sub.id)
    assert status is not None and status["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_dispatches_subscription_without_template_config(
    database: Database, engine_setup
) -> None:
    """No template-keyed config in RAM (the post-restart state: rehydrate and
    reconcile register configs under sub.id only) — dispatch must fall back to
    strategy-class defaults instead of failing the request."""
    deps, sub_repo, bt_repo = engine_setup
    request_repo = BacktestRequestRepository(database)

    # Drop the template-keyed entry the fixture injected.
    await deps.strategy_app_service.unload_strategy(_STRATEGY)
    assert deps.strategy_app_service.get_config(_STRATEGY) is None

    sub = Subscription(
        id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, _INTERVAL),
        strategy_code=_STRATEGY,
        symbol=_SYMBOL,
        interval=Interval(_INTERVAL),
        created_at=datetime.now(UTC),
    )
    await sub_repo.add(sub)

    req = _request("subscription", sub_id=sub.id, strategy_code=_STRATEGY)
    await request_repo.enqueue(req)

    worker = BacktestRequestWorker(request_repo, deps)
    assert await worker._drain_once() is True

    done = await request_repo.get(str(req.id))
    assert done is not None and done.status == "done"

    status = await bt_repo.get_subscription_status(sub.id)
    assert status is not None and status["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_dispatches_single_with_embedded_result(
    database: Database, engine_setup
) -> None:
    deps, _sub_repo, _bt_repo = engine_setup
    request_repo = BacktestRequestRepository(database)

    config = {
        "strategy_code": _STRATEGY,
        "symbol": _SYMBOL,
        "interval": _INTERVAL,
        "start_date": date(2024, 1, 1).isoformat(),
        "end_date": date(2024, 1, 31).isoformat(),
        "initial_capital": 10_000.0,
        "slippage_bps": 10.0,
        "commission_bps": 10.0,
        "parameters": {
            "entry_lookback_bars": 10,
            "sl_lookback_bars": 20,
            "tp_lookback_bars": 5,
        },
    }
    req = _request("single", strategy_code=_STRATEGY, config=config)
    await request_repo.enqueue(req)

    worker = BacktestRequestWorker(request_repo, deps)
    assert await worker._drain_once() is True

    done = await request_repo.get(str(req.id))
    assert done is not None and done.status == "done"
    assert done.result is not None
    # Embedded FE response shape the chart renders unchanged.
    assert done.result["status"] == "completed"
    assert "run_id" in done.result
    assert "metrics" in done.result
    assert isinstance(done.result["positions"], list)


@pytest.mark.asyncio
async def test_worker_failure_isolation(database: Database, engine_setup) -> None:
    """A bad request is marked failed; a subsequent good one still completes."""
    deps, sub_repo, _bt_repo = engine_setup
    request_repo = BacktestRequestRepository(database)

    # Bad: subscription request whose sub doc does not exist → run_subscription
    # bails as not-found, marks done (no-op), so use an unknown-kind to force fail.
    bad = _request("single", strategy_code="does-not-exist", config={"strategy_code": "nope"})
    await request_repo.enqueue(bad)
    assert await worker_drain(request_repo, deps) is True
    bad_doc = await request_repo.get(str(bad.id))
    assert bad_doc is not None and bad_doc.status == "failed"

    # Good: a valid subscription request still processes next.
    sub = Subscription(
        id=Subscription.deterministic_id(_STRATEGY, _SYMBOL, _INTERVAL),
        strategy_code=_STRATEGY,
        symbol=_SYMBOL,
        interval=Interval(_INTERVAL),
        created_at=datetime.now(UTC),
    )
    await sub_repo.add(sub)
    good = _request("subscription", sub_id=sub.id, strategy_code=_STRATEGY)
    await request_repo.enqueue(good)
    assert await worker_drain(request_repo, deps) is True
    good_doc = await request_repo.get(str(good.id))
    assert good_doc is not None and good_doc.status == "done"


async def worker_drain(repo: BacktestRequestRepository, deps: BacktestDispatchDeps) -> bool:
    return await BacktestRequestWorker(repo, deps)._drain_once()
