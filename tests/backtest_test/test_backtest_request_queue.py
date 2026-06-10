"""Backtest request queue — repo atomic claim + worker dispatch round-trips.

Covers the queue mechanism that replaced APScheduler bt:* jobs:
  - enqueue → pending; claim_next atomic flip → running; 2nd claim → None.
  - idempotent re-enqueue (deterministic id collapses to one pending doc).
  - worker subscription dispatch → backtest_runs result + request done.
  - worker single dispatch → request doc carries embedded FE result + done.
  - per-request failure isolation: one bad request, the next still runs.
  - stale running reclaim → back to pending.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps
from pocketquant.backtest.workers.backtest_request_worker import BacktestRequestWorker
from pocketquant.core.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.backtest.request import BacktestRequest
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.brokers.interfaces import IBroker
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.persistence.mongodb import Database
from pocketquant.core.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.persistence.repositories.backtest_request_repository import (
    BacktestRequestRepository,
)
from pocketquant.core.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.persistence.repositories.order_repository import OrderRepository
from pocketquant.core.persistence.repositories.position_repository import (
    PositionRepository,
)
from pocketquant.core.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.execution.app_services.order_app_service import OrderAppService
from pocketquant.execution.app_services.position_app_service import PositionAppService
from pocketquant.execution.app_services.strategy_app_service import StrategyAppService
from pocketquant.execution.handlers.risk.check_risk.handler import RiskCheckHandler

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
        id=kwargs.pop("id", generate_id_str()),
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

    stored = await request_repo.get(req.id)
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
async def test_reenqueue_is_idempotent(request_repo: BacktestRequestRepository) -> None:
    det_id = f"bt:{_STRATEGY}:sub1"
    await request_repo.enqueue(_request("subscription", id=det_id, sub_id="sub1"))
    await request_repo.enqueue(_request("subscription", id=det_id, sub_id="sub1"))

    coll = request_repo._collection()
    assert await coll.count_documents({"_id": det_id}) == 1


@pytest.mark.asyncio
async def test_mark_done_and_failed(request_repo: BacktestRequestRepository) -> None:
    req = _request("single")
    await request_repo.enqueue(req)
    await request_repo.claim_next()

    await request_repo.mark_done(req.id, result={"run_id": "x", "status": "completed"})
    done = await request_repo.get(req.id)
    assert done is not None and done.status == "done"
    assert done.result == {"run_id": "x", "status": "completed"}
    assert done.finished_at is not None

    other = _request("single")
    await request_repo.enqueue(other)
    await request_repo.claim_next()
    await request_repo.mark_failed(other.id, "boom")
    failed = await request_repo.get(other.id)
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
        {"_id": req.id},
        {"$set": {"started_at": datetime.now(UTC) - timedelta(minutes=30)}},
    )

    reclaimed = await request_repo.reclaim_stale_running(threshold_minutes=10)
    assert reclaimed == 1
    back = await request_repo.get(req.id)
    assert back is not None and back.status == "pending"
    # A fresh claim picks it up again.
    assert (await request_repo.claim_next()) is not None


@pytest.mark.asyncio
async def test_fresh_running_not_reclaimed(request_repo: BacktestRequestRepository) -> None:
    req = _request("single")
    await request_repo.enqueue(req)
    await request_repo.claim_next()
    assert await request_repo.reclaim_stale_running(threshold_minutes=10) == 0


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
    from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY

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

    req = _request("subscription", id=f"bt:{sub.id}", sub_id=sub.id, strategy_code=_STRATEGY)
    await request_repo.enqueue(req)

    worker = BacktestRequestWorker(request_repo, deps)
    processed = await worker._drain_once()
    assert processed is True

    done = await request_repo.get(req.id)
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

    done = await request_repo.get(req.id)
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
    bad_doc = await request_repo.get(bad.id)
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
    good = _request("subscription", id=f"bt:{sub.id}", sub_id=sub.id, strategy_code=_STRATEGY)
    await request_repo.enqueue(good)
    assert await worker_drain(request_repo, deps) is True
    good_doc = await request_repo.get(good.id)
    assert good_doc is not None and good_doc.status == "done"


async def worker_drain(repo: BacktestRequestRepository, deps: BacktestDispatchDeps) -> bool:
    return await BacktestRequestWorker(repo, deps)._drain_once()
