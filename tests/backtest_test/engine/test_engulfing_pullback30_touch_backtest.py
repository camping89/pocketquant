"""Integration tests for engulfing_pullback30_touch over BacktestAppService.

Drives the real BacktestAppService + HistoricalReplayAppService + PaperBrokerAdapter +
StrategyAppService wiring (only persistence is faked). Confirms the deferred
entry: the engulfing bar arms, a pullback bar enters at its close, price clears
TP → round-trip; and that an engulfing without a following pullback yields no
trade at all (unlike the parent engulfing, which enters immediately).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.backtest import BacktestConfig, BacktestResult
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.brokers.broker_port import IBrokerPort
from pocketquant.core.domain.order import OrderAggregate
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.risk import RiskConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_app_service import BacktestAppService
from pocketquant.engine.execution.order_app_service import OrderAppService
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.execution.risk_check import RiskCheckHandler
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_CODE = "engulfing_pullback30_touch"


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


class _InMemoryBacktestRepo:
    def __init__(self) -> None:
        self.saved: list[BacktestResult] = []

    async def save(self, result: BacktestResult) -> str:
        self.saved.append(result)
        return getattr(result, "run_id", "in-memory")


class _FakeBarRepo:
    def __init__(self, bars: list[Bar]) -> None:
        self._bars = bars

    async def stream(
        self,
        symbol: str,
        interval: Interval,
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
    ) -> AsyncIterator[Bar]:
        for b in self._bars:
            yield b

    async def find_datetimes(self, *args, **kwargs) -> list:
        return []


class _StubBrokerFactory:
    def __init__(self, broker: IBrokerPort) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
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
    )


def _flat(idx: int) -> Bar:
    return _bar(idx, o=100.0, h=100.2, lo=99.8, c=100.0)


def _pullback_long_cycle_bars(cycles: int = 2, lookback: int = 5) -> list[Bar]:
    """Warmup, then repeated arm → pullback entry → TP round trips.

    Each cycle: red prev, green engulfing (arms at level=100.52, SL~99.2), a
    pullback bar dipping to low=100.3 (<= level, > SL) and closing at 100.6 →
    enters at that close, a spike whose high clears the ~102 TP, then flat
    fillers to roll the spike high out of the lookback window.
    """
    bars: list[Bar] = []
    idx = 0
    for _ in range(lookback + 1):
        bars.append(_flat(idx))
        idx += 1
    for _ in range(cycles):
        bars.append(_bar(idx, o=100.5, h=100.6, lo=99.4, c=99.5))  # red prev
        idx += 1
        bars.append(_bar(idx, o=99.4, h=101.1, lo=99.3, c=101.0))  # green engulf → arm
        idx += 1
        bars.append(_bar(idx, o=101.0, h=101.0, lo=100.3, c=100.6))  # pullback → enter
        idx += 1
        bars.append(_bar(idx, o=100.6, h=103.0, lo=100.4, c=102.5))  # spike clears TP
        idx += 1
        for _ in range(lookback + 1):
            bars.append(_flat(idx))
            idx += 1
    return bars


def _no_pullback_bars(lookback: int = 5) -> list[Bar]:
    """Engulfing arms but the next bar never dips to the level → discarded."""
    bars: list[Bar] = []
    idx = 0
    for _ in range(lookback + 1):
        bars.append(_flat(idx))
        idx += 1
    bars.append(_bar(idx, o=100.5, h=100.6, lo=99.4, c=99.5))  # red prev
    idx += 1
    bars.append(_bar(idx, o=99.4, h=101.1, lo=99.3, c=101.0))  # green engulf → arm
    idx += 1
    bars.append(_bar(idx, o=101.0, h=101.5, lo=100.8, c=101.2))  # no touch (low > 100.52)
    idx += 1
    for _ in range(lookback + 1):
        bars.append(_flat(idx))
        idx += 1
    return bars


async def _run_backtest(
    bars: list[Bar],
    *,
    direction: str = "long",
    lookback: int = 5,
    pullback_pct: float = 0.30,
    max_exposure_percent: float = 1.0,
) -> tuple[BacktestResult, PaperBrokerAdapter]:
    bus = EventBus()
    order_repo = _InMemoryOrderRepo()
    position_repo = _InMemoryPositionRepo()
    bt_repo = _InMemoryBacktestRepo()

    order_svc = OrderAppService(bus, order_repo)  # pyright: ignore[reportArgumentType]
    position_svc = PositionAppService(bus, position_repo)  # pyright: ignore[reportArgumentType]
    await position_svc.start()

    broker = PaperBrokerAdapter(
        initial_balance=10_000.0,
        slippage_percent=0.0,
        fill_delay_ms=0,
        event_bus=bus,
    )
    broker_factory = _StubBrokerFactory(broker)

    strategy_svc = StrategyAppService(
        event_bus=bus,
        broker_factory=broker_factory,  # pyright: ignore[reportArgumentType]
        order_app_service=order_svc,
        position_app_service=position_svc,
        risk_check_handler=RiskCheckHandler(),
    )
    await strategy_svc.start()

    strategy_cls = STRATEGY_REGISTRY[_CODE]
    strategy_cfg = StrategyConfig(
        id=_CODE,
        name=_CODE,
        symbol=_SYM,
        interval="1m",
        trigger="bar",
        broker="paper",
        parameters={
            "direction": direction,
            "key_level_lookback_bars": lookback,
            "sl_buffer_pct": 0.001,
            "max_rejection_wick_pct": 0.30,
            "pullback_pct": pullback_pct,
        },
        risk=RiskConfig(max_exposure_percent=max_exposure_percent),
    )
    strategy = strategy_cls(strategy_cfg)
    await strategy_svc.inject_prepared_strategy(strategy.id, strategy, broker, strategy_cfg)

    runner = BacktestAppService(
        event_bus=bus,
        broker=broker,
        backtest_repository=bt_repo,  # pyright: ignore[reportArgumentType]
        bar_repository=_FakeBarRepo(bars),  # pyright: ignore[reportArgumentType]
        persist_results=False,
    )
    config = BacktestConfig(
        strategy_code=_CODE,
        symbol=_SYM,
        interval="1m",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 12, 31),
        initial_capital=10_000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )
    result = await runner.run(config)
    return result, broker


async def test_registered_in_strategy_registry() -> None:
    assert _CODE in STRATEGY_REGISTRY


async def test_pullback_cycle_opens_and_round_trips() -> None:
    bars = _pullback_long_cycle_bars(cycles=2, lookback=5)
    result, broker = await _run_backtest(bars, direction="long", lookback=5)
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades >= 1
    assert (await broker.get_positions()) == []

    m = result.metrics
    realized = m.avg_win * m.winning_trades + m.avg_loss * m.losing_trades
    balance = await broker.get_balance()
    assert balance.available_balance == pytest.approx(10_000.0 + realized)


async def test_no_pullback_no_trade() -> None:
    bars = _no_pullback_bars(lookback=5)
    result, broker = await _run_backtest(bars, direction="long", lookback=5)
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades == 0
    assert (await broker.get_positions()) == []
