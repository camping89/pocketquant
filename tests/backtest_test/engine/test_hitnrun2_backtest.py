"""Integration tests for hitnrun2 over BacktestAppService with in-memory repos.

Drives the real BacktestAppService + HistoricalReplayAppService + PaperBrokerAdapter +
StrategyAppService wiring. Substitutes only persistence with in-memory fakes.

No MongoDB / Redis required.
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
    """Returns whatever broker the test has already wired; StrategyAppService never asks again."""

    def __init__(self, broker: IBrokerPort) -> None:
        self._broker = broker

    def create(self, broker_type: str, config: dict) -> IBrokerPort:
        return self._broker


def _ohlcv_bar(idx: int, *, o: float, h: float, lo: float, c: float, t0: datetime) -> Bar:
    return Bar(
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        datetime=t0 + timedelta(minutes=idx),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=1.0,
    )


def _downtrend_bars(n_warm: int = 30, n_trend: int = 20, start_price: float = 100.0) -> list[Bar]:
    """Flat warm-up at start_price, then steady step-down that breaks below window low."""
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[Bar] = []
    for i in range(n_warm):
        bars.append(
            _ohlcv_bar(
                i,
                o=start_price,
                h=start_price + 0.1,
                lo=start_price - 0.1,
                c=start_price,
                t0=t0,
            )
        )
    price = start_price
    for j in range(n_trend):
        price -= 0.5
        bars.append(
            _ohlcv_bar(n_warm + j, o=price + 0.5, h=price + 0.5, lo=price - 0.5, c=price, t0=t0)
        )
    return bars


def _uptrend_bars(n_warm: int = 30, n_trend: int = 20, start_price: float = 100.0) -> list[Bar]:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[Bar] = []
    for i in range(n_warm):
        bars.append(
            _ohlcv_bar(
                i,
                o=start_price,
                h=start_price + 0.1,
                lo=start_price - 0.1,
                c=start_price,
                t0=t0,
            )
        )
    price = start_price
    for j in range(n_trend):
        price += 0.5
        bars.append(
            _ohlcv_bar(n_warm + j, o=price - 0.5, h=price + 0.5, lo=price - 0.5, c=price, t0=t0)
        )
    return bars


def _choppy_bars(n: int = 60, base: float = 100.0) -> list[Bar]:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    return [_ohlcv_bar(i, o=base, h=base + 0.2, lo=base - 0.2, c=base, t0=t0) for i in range(n)]


def _oscillating_bars(cycles: int = 4) -> list[Bar]:
    """Repeated: new-low breakdown entry, then a bar whose HIGH pops up to hit TP.

    Each cycle dips to a fresh lower low (LONG breakdown entry), then a recovery
    bar's HIGH clears the TP so the position round-trips. Drives multiple trades
    only if on_order_filled resets the open-direction AND the broker reopens after
    close (Bug #1 + closed-position re-entry).
    """
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    bars: list[Bar] = []
    idx = 0
    lvl = 100.0
    for _ in range(25):
        bars.append(_ohlcv_bar(idx, o=lvl, h=lvl + 0.05, lo=lvl - 0.05, c=lvl, t0=t0))
        idx += 1
    for cyc in range(cycles):
        low = lvl - 1.0 - cyc * 0.5
        bars.append(_ohlcv_bar(idx, o=lvl, h=lvl + 0.05, lo=low - 0.05, c=low, t0=t0))
        idx += 1
        bars.append(_ohlcv_bar(idx, o=low, h=lvl + 0.5, lo=low - 0.05, c=lvl, t0=t0))
        idx += 1
        for _ in range(3):
            bars.append(_ohlcv_bar(idx, o=lvl, h=lvl + 0.05, lo=lvl - 0.05, c=lvl, t0=t0))
            idx += 1
    return bars


async def _run_backtest(
    bars: list[Bar],
    direction: str,
    entry_lookback: int = 10,
    sl_lookback: int = 20,
    tp_lookback: int = 5,
    max_loss_pct: float = 0.01,
    min_profit_pct: float = 0.005,
    max_exposure_percent: float | None = None,
) -> tuple[BacktestResult, PaperBrokerAdapter, StrategyAppService]:
    """Wire pipeline and return result + handles for assertion."""
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

    strategy_cls = STRATEGY_REGISTRY["hitnrun2"]
    risk = RiskConfig(max_exposure_percent=max_exposure_percent) if max_exposure_percent else None
    strategy_cfg = StrategyConfig(
        id="hitnrun2",
        name="hitnrun2",
        symbol=_SYM,
        interval="1m",
        trigger="bar",
        broker="paper",
        parameters={
            "entry_lookback_bars": entry_lookback,
            "sl_lookback_bars": sl_lookback,
            "tp_lookback_bars": tp_lookback,
            "max_loss_pct": max_loss_pct,
            "min_profit_pct": min_profit_pct,
            "direction": direction,
        },
        risk=risk or RiskConfig(),
    )
    strategy = strategy_cls(strategy_cfg)

    await strategy_svc.inject_prepared_strategy(strategy.id, strategy, broker, strategy_cfg)

    bar_repo = _FakeBarRepo(bars)
    runner = BacktestAppService(
        event_bus=bus,
        broker=broker,
        backtest_repository=bt_repo,  # pyright: ignore[reportArgumentType]
        bar_repository=bar_repo,  # pyright: ignore[reportArgumentType]
        persist_results=False,
    )

    config = BacktestConfig(
        strategy_code="hitnrun2",
        symbol=_SYM,
        interval="1m",
        start_date=datetime(2026, 1, 1),
        end_date=datetime(2026, 12, 31),
        initial_capital=10_000.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )
    result = await runner.run(config)
    return result, broker, strategy_svc


async def test_backtest_long_round_trip_on_downtrend() -> None:
    bars = _downtrend_bars(n_warm=30, n_trend=20, start_price=100.0)
    result, broker, _ = await _run_backtest(bars, direction="long")
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades >= 1
    assert len(result.equity_curve) > 1
    # SL/TP auto-fill must have closed the position before end-of-data.
    open_positions = await broker.get_positions()
    assert open_positions == []


async def test_backtest_short_round_trip_on_uptrend() -> None:
    bars = _uptrend_bars(n_warm=30, n_trend=20, start_price=100.0)
    result, broker, _ = await _run_backtest(bars, direction="short")
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades >= 1
    assert (await broker.get_positions()) == []


async def test_backtest_no_trades_on_choppy_market() -> None:
    bars = _choppy_bars(n=60)
    result, broker, _ = await _run_backtest(bars, direction="both")
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades == 0
    assert (await broker.get_positions()) == []


async def test_backtest_multi_trade_after_fill_reset() -> None:
    """Bug #1: with on_order_filled reset wired, repeated round-trips → many trades.

    Before the fix, the strategy's open-direction never reset → at most 1 trade.
    Uses a wide max_exposure RiskConfig so the one-position cap (not risk) governs.
    """
    bars = _oscillating_bars(cycles=4)
    result, broker, _ = await _run_backtest(
        bars,
        direction="long",
        max_loss_pct=0.05,
        min_profit_pct=0.002,
        max_exposure_percent=1.0,
    )
    assert result.status == "finished", result.error_message
    assert result.metrics.total_trades > 1
    assert (await broker.get_positions()) == []


async def test_backtest_sharpe_bounded_and_realized_metrics_present() -> None:
    """Per-bar MTM annualization yields a finite Sharpe; realized metrics intact."""
    bars = _oscillating_bars(cycles=4)
    result, _, _ = await _run_backtest(
        bars,
        direction="long",
        max_loss_pct=0.05,
        min_profit_pct=0.002,
        max_exposure_percent=1.0,
    )
    m = result.metrics
    # Sharpe is finite (not NaN/inf) — annualization used a valid periods_per_year.
    assert m.sharpe_ratio == m.sharpe_ratio  # not NaN
    assert abs(m.sharpe_ratio) != float("inf")
    # Realized metrics computed from the trade-keyed curve.
    assert m.total_trades > 1
    assert m.max_drawdown <= 0.0
