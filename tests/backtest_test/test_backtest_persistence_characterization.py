"""Characterization — pins engine persist + run_id + list invariant.

Locks the behaviour the queue/optimize/run-all removal must preserve:

- ``run_single`` → 3-collection persist (``backtest_runs`` + ``backtest_orders``
  + ``backtest_trades``) with the expected doc shape.
- The shared-run_id invariant: the run doc ``_id`` equals every persisted
  ``backtest_orders.run_id`` and ``backtest_trades.run_id``.
- ``list_by_strategy_code`` returns a run that just finished (the status-filter
  contract).
- Sandbox isolation: replaying historical bars in a backtest never drives a
  live engine subscribed to the same bar/fill events.

If a later refactor breaks the engine path, the persisted data shape, the
run_id threading, or the list filter, one of these assertions turns red.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.backtest.workers.backtest_dispatch import (
    BacktestDispatchDeps,
    run_single,
)
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.brokers.interfaces import IBroker
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker import PaperBroker
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_order_repository import (
    BacktestOrderRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)
from pocketquant.core.infra.persistence.repositories.backtest_trade_repository import (
    BacktestTradeRepository,
)
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.engine.app_services.order_app_service import OrderAppService
from pocketquant.engine.app_services.position_app_service import PositionAppService
from pocketquant.engine.app_services.strategy_app_service import StrategyAppService
from pocketquant.engine.handlers.risk.check_risk.handler import RiskCheckHandler

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_METRIC_KEYS = (
    "total_return",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_trades",
    "total_commission",
)


@pytest.fixture(autouse=True)
def _reset_sim_time() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


class _InMemoryOrderRepo:
    def __init__(self) -> None:
        self._items: dict[str, OrderAggregate] = {}

    async def save(self, order: OrderAggregate) -> None:
        self._items[str(order.id)] = order

    async def get(self, order_id: str) -> OrderAggregate | None:
        return self._items.get(order_id)

    async def find_by_subscription(
        self, subscription_id: str, limit: int = 1000
    ) -> list[OrderAggregate]:
        return [o for o in self._items.values() if o.subscription_id == subscription_id][:limit]

    async def find_pending(self, limit: int = 500) -> list[OrderAggregate]:
        return []


class _InMemoryPositionRepo:
    def __init__(self) -> None:
        self._items: dict[str, PositionAggregate] = {}

    async def save(self, position: PositionAggregate) -> None:
        self._items[str(position.id)] = position

    async def get(self, position_id: str) -> PositionAggregate | None:
        return self._items.get(position_id)

    async def get_by_subscription(self, subscription_id: str) -> PositionAggregate | None:
        for p in self._items.values():
            if p.subscription_id == subscription_id and not p.is_closed:
                return p
        return None

    async def find_open(self, limit: int = 200) -> list[PositionAggregate]:
        return [p for p in self._items.values() if not p.is_closed][:limit]


class _StubBrokerFactory:
    def __init__(self, broker: IBroker) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBroker:
        return self._broker


def _bar(idx: int, *, o: float, h: float, lo: float, c: float) -> Bar:
    return Bar(
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        datetime=_T0 + timedelta(minutes=idx),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1.0,
        tick_count=1,
    )


def _flat(idx: int) -> Bar:
    return _bar(idx, o=100.0, h=100.2, lo=99.8, c=100.0)


def _engulfing_long_cycle_bars(cycles: int = 3, lookback: int = 5) -> list[Bar]:
    """Warmup, then repeated bullish-engulfing → TP round trips.

    Mirrors the engine integration fixture: each cycle is a red prev bar, a
    strong-green engulfing entry, a spike clearing the TP, then flat fillers to
    roll the spike out of the lookback window.
    """
    bars: list[Bar] = []
    idx = 0
    for _ in range(lookback + 1):
        bars.append(_flat(idx))
        idx += 1
    for _ in range(cycles):
        bars.append(_bar(idx, o=100.5, h=100.6, lo=99.4, c=99.5))  # red prev
        idx += 1
        bars.append(_bar(idx, o=99.4, h=101.1, lo=99.3, c=101.0))  # green engulf entry
        idx += 1
        bars.append(_bar(idx, o=101.0, h=103.0, lo=100.5, c=102.5))  # spike clears TP
        idx += 1
        for _ in range(lookback + 1):
            bars.append(_flat(idx))
            idx += 1
    return bars


async def _seed_bars(database: Database, bars: list[Bar]) -> None:
    coll = database.get_collection("bars")
    await coll.delete_many({"symbol": _SYM, "interval": Interval.MINUTE_1.value})
    await coll.insert_many([b.to_mongo() for b in bars])


async def _build_live_engine() -> tuple[
    StrategyAppService, PaperBroker, _InMemoryOrderRepo, _InMemoryPositionRepo
]:
    """A live engine on its own bus, with an engulfing strategy listening.

    If a backtest leaked replayed bars onto a shared bus, this engine's injected
    strategy would emit orders — so an empty live order book after the run is the
    isolation proof.
    """
    bus = EventBus()
    order_repo = _InMemoryOrderRepo()
    position_repo = _InMemoryPositionRepo()
    order_svc = OrderAppService(bus, order_repo)  # pyright: ignore[reportArgumentType]
    position_svc = PositionAppService(bus, position_repo)  # pyright: ignore[reportArgumentType]
    await position_svc.start()

    broker = PaperBroker(
        initial_balance=10_000.0, slippage_percent=0.0, fill_delay_ms=0, event_bus=bus
    )
    engine = StrategyAppService(
        event_bus=bus,
        broker_factory=_StubBrokerFactory(broker),  # pyright: ignore[reportArgumentType]
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
    )
    await engine.start()

    live_cfg = StrategyConfig(
        id="engulfing-live",
        name="engulfing",
        symbol=_SYM,
        interval="1m",
        trigger="bar",
        broker="paper",
        parameters={"direction": "long", "key_level_lookback_bars": 5},
    )
    live_strategy = STRATEGY_REGISTRY["engulfing"](live_cfg)
    await engine.inject_prepared_strategy(live_strategy.id, live_strategy, broker, live_cfg)
    return engine, broker, order_repo, position_repo


@pytest.mark.asyncio
async def test_run_single_persists_three_collections_with_shared_run_id(
    database: Database,
) -> None:
    await _seed_bars(database, _engulfing_long_cycle_bars(cycles=3, lookback=5))

    # A live engine on its own bus runs in parallel; run_single builds its own
    # isolated sandbox, so the live engine must see none of the replayed bars.
    _live_engine, live_broker, live_orders, live_positions = await _build_live_engine()

    deps = BacktestDispatchDeps(
        bar_repo=BarRepository(database),
        backtest_repo=BacktestRepository(database),
        order_repo=BacktestOrderRepository(database),
        trade_repo=BacktestTradeRepository(database),
    )
    config_payload = {
        "strategy_code": "engulfing",
        "symbol": _SYM,
        "interval": "1m",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "initial_capital": 10_000.0,
        "slippage_bps": 0.0,
        "commission_bps": 0.0,
        "parameters": {
            "direction": "long",
            "key_level_lookback_bars": 5,
            "sl_buffer_pct": 0.001,
            "max_rejection_wick_pct": 0.30,
        },
    }

    result = await run_single(deps, config_payload)

    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades >= 1

    run_id = str(result.id)

    run_doc = await database.get_collection("backtest_runs").find_one({"_id": run_id})
    assert run_doc is not None
    assert run_doc["status"] == "finished"
    assert run_doc["equity_curve"], "equity curve must be non-empty"
    assert "trades" not in run_doc and "positions" not in run_doc  # slim doc
    for key in _METRIC_KEYS:
        assert key in run_doc["metrics"], f"missing metric {key!r}"

    # C2 — one run_id threads through all three collections.
    orders = await deps.order_repo.list_by_run(run_id)
    trades = await deps.trade_repo.list_by_run(run_id)
    assert orders, "expected persisted orders"
    assert trades, "expected persisted trades"
    assert all(o.run_id == run_id for o in orders)
    assert all(t.run_id == run_id for t in trades)

    # C5 — a just-finished run is returned by the strategy listing.
    listed = await deps.backtest_repo.list_by_strategy_code("engulfing")
    assert any(str(r.id) == run_id for r in listed)

    # Sandbox isolation — the live engine saw none of the replayed bars.
    assert live_orders._items == {}
    assert (await live_positions.find_open()) == []
    assert (await live_broker.get_positions()) == []
