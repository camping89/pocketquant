"""Integration: bff run-all enqueue → worker dispatch → bff cascade delete cleans DB.

Spans the split deterministically without a dual lifespan: the stateless bff
serves the HTTP enqueue + cascade-delete, and the backtest worker dispatch is
driven directly (the app-runtime path) rather than waiting on a live poll loop.
This mirrors how the app worker drains the queue, while keeping the test fast
and flake-free.

Skippable with SKIP_SLOW_TESTS=1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from pocketquant.backtest.workers.backtest_dispatch import BacktestDispatchDeps, run_subscription
from pocketquant.core.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.concepts.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.concepts.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
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
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler

pytestmark = pytest.mark.integration

_API = "/api/v1/strategies"
_STRATEGY_ID = "hitnrun2"  # must be in STRATEGY_REGISTRY
_SYMBOL = "BTCUSDT:BINANCE"
_INTERVAL = "1h"
_N_BARS = 100


def _synthetic_bars(n: int) -> list[Bar]:
    base = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
    bars: list[Bar] = []
    price = 40_000.0
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


class _StubBrokerFactory:
    def __init__(self, broker) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict):
        return self._broker


@pytest_asyncio.fixture(autouse=True)
async def setup_strategy_and_bars(bff_client):
    """Seed bars + tracked symbol; clean prior data. Strategy load happens in the
    worker-side engine the test builds, not in bff (bff is stateless)."""
    from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
    from pocketquant.core.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    container = bff_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    bar_repo: BarRepository = await container.get(BarRepository)
    bt_repo: BacktestRepository = await container.get(BacktestRepository)
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    tracked_repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)
    db: Database = await container.get(Database)

    await tracked_repo.upsert(TrackedSymbol(symbol=_SYMBOL))
    await bar_repo.insert_many(_synthetic_bars(_N_BARS), source="test")
    await bt_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    await db.get_collection("backtest_requests").delete_many({"strategy_code": _STRATEGY_ID})

    yield

    await bar_repo._collection().delete_many({"symbol": _SYMBOL, "interval": _INTERVAL})
    await bt_repo.delete_by_strategy_code(_STRATEGY_ID)
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    await db.get_collection("backtest_requests").delete_many({"strategy_code": _STRATEGY_ID})


async def _build_worker_deps(db: Database) -> BacktestDispatchDeps:
    """Construct the app-side dispatch deps (engine + repos) sharing the test DB.

    Registers the base strategy config keyed by template code, exactly as the
    app rehydrate/reconcile path does, so run_subscription can resolve it.
    """
    event_bus = EventBus(max_history=100)
    order_svc = OrderAppService(event_bus, OrderRepository(db))
    await order_svc.load_pending_orders()
    position_svc = PositionAppService(event_bus, PositionRepository(db))
    await position_svc.start()

    base_broker = PaperBroker(initial_balance=10_000.0, slippage_percent=0.0, event_bus=event_bus)
    strategy_svc = StrategyAppService(
        event_bus=event_bus,
        broker_factory=_StubBrokerFactory(base_broker),  # type: ignore[arg-type]
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
    )
    await strategy_svc.start()
    base_cfg = StrategyConfig(
        id=_STRATEGY_ID,
        name=_STRATEGY_ID,
        symbol=_SYMBOL,
        interval=_INTERVAL,
        trigger="bar",
        broker="paper",
        parameters={"entry_lookback_bars": 10, "sl_lookback_bars": 20, "tp_lookback_bars": 5},
    )
    instance = STRATEGY_REGISTRY[_STRATEGY_ID](base_cfg)
    await strategy_svc.inject_prepared_strategy(_STRATEGY_ID, instance, base_broker, base_cfg)

    return BacktestDispatchDeps(
        event_bus=event_bus,
        bar_repo=BarRepository(db),
        backtest_repo=BacktestRepository(db),
        order_repo=BacktestOrderRepository(db),
        trade_repo=BacktestTradeRepository(db),
        strategy_app_service=strategy_svc,
        subscription_repo=SubscriptionRepository(db),
    )


@pytest.mark.asyncio
async def test_run_all_backtest_cascade_delete(bff_client):
    """bff add sub → bff run-all enqueue → worker dispatch → bff cascade delete cleans DB."""
    container = bff_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    bt_repo: BacktestRepository = await container.get(BacktestRepository)
    request_repo: BacktestRequestRepository = await container.get(BacktestRequestRepository)
    db: Database = await container.get(Database)

    # 1. Add subscription (bff, pure Mongo)
    add_r = await bff_client.post(
        f"{_API}/{_STRATEGY_ID}/subscriptions",
        json={"symbol": _SYMBOL, "interval": _INTERVAL},
    )
    assert add_r.status_code == 201, add_r.text
    sub_id = add_r.json()["id"]

    # 2. Trigger run-all (bff enqueue → backtest_requests)
    run_r = await bff_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests")
    assert run_r.status_code == 202, run_r.text
    assert len(run_r.json()["job_ids"]) == 1

    # 3. Drain the queue via the worker dispatch (the app-runtime path).
    claimed = await request_repo.claim_next()
    assert claimed is not None and claimed.sub_id == sub_id
    deps = await _build_worker_deps(db)
    try:
        await run_subscription(deps, sub_id)
    finally:
        await deps.strategy_app_service.stop()
    await request_repo.mark_done(claimed.id)

    status_doc = await bt_repo.get_subscription_status(sub_id)
    assert status_doc is not None and status_doc["status"] == "completed", (
        f"Expected 'completed', got {status_doc}"
    )

    # 4. GET backtest via bff
    bt_r = await bff_client.get(f"/api/v1/subscriptions/{sub_id}/backtest")
    assert bt_r.status_code == 200, bt_r.text
    assert bt_r.json()["status"] == "completed"

    # 5. Cascade delete (bff)
    del_r = await bff_client.delete(f"{_API}/{_STRATEGY_ID}")
    assert del_r.status_code == 204, del_r.text

    # 6. backtest cache cleared
    assert await bt_repo.find_by_subscription(sub_id) is None
