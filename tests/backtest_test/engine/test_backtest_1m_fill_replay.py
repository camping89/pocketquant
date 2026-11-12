# A backtest whose symbol has 1m bars by the start replays them between the entry bars, so the
# paper broker fills stops and checks SL/TP on 1m bars in time order, as live paper does.

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.backtest import BacktestConfig
from pocketquant.core.domain.bar import BarCompletedEvent
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.shared import Interval
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_app_service import BacktestAppService
from pocketquant.engine.backtest.backtest_report_app_service import BacktestReportAppService

_SYM = "XAUUSD:EXNESS"
_SUB = "t"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_M = timedelta(minutes=1)
_Q = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def _clear_sim_time() -> Iterator[None]:
    yield
    clear_simulation_time()


def _bar(interval: str, start: datetime, o: float, h: float, lo: float, c: float) -> Bar:
    return Bar(
        symbol=_SYM, interval=Interval(interval), datetime=start, open=o, high=h, low=lo, close=c
    )


def _flat(interval: str, start: datetime, price: float = 100.0) -> Bar:
    return _bar(interval, start, price, price + 0.1, price - 0.1, price)


# A 15m bar built from its 1m bars, or flat when it has none.
def _quarter(start: datetime, ones: list[Bar]) -> Bar:
    inside = [b for b in ones if b.datetime is not None and start <= b.datetime < start + _Q]
    if not inside:
        return _flat("15m", start)
    return _bar(
        "15m",
        start,
        inside[0].open,
        max(b.high for b in inside),
        min(b.low for b in inside),
        inside[-1].close,
    )


class _Bars:
    def __init__(self, by_interval: dict[str, list[Bar]]) -> None:
        self._by = by_interval

    async def find(self, symbol: str, interval: Interval, end_date=None, limit: int = 5000):
        found = [b for b in self._by.get(interval.value, []) if b.datetime <= end_date]
        return list(reversed(found))[:limit]

    async def stream(self, symbol: str, interval: Interval, start: datetime, end: datetime):
        for b in self._by.get(interval.value, []):
            if start <= b.datetime <= end:
                yield b


class _Sink:
    def __init__(self) -> None:
        self.saved: list = []

    async def save_many(self, items: list) -> None:
        self.saved.extend(items)

    async def save(self, item: Any) -> None:
        self.saved.append(item)


# Stands in for StrategyAppService: resting stops fill before the strategy decides, and the
# strategy sees only entry-interval bars.
async def _run(
    bars: dict[str, list[Bar]],
    place,
    *,
    entry: str = "15m",
    seen: list[BarCompletedEvent] | None = None,
):
    bus = EventBus()
    broker = PaperBrokerAdapter(initial_balance=1_000_000.0, fill_delay_ms=0, event_bus=bus)

    async def engine(event: BarCompletedEvent) -> None:
        if seen is not None:
            seen.append(event)
        await broker.fill_resting_stops(event, {_SUB})
        if event.interval == entry:
            order = await place(event, broker)
            if order is not None:
                await broker.submit_order(order)

    bus.subscribe(BarCompletedEvent, engine)
    await broker.connect()
    trades = _Sink()
    runner = BacktestAppService(
        event_bus=bus,
        broker=broker,
        backtest_repository=_Sink(),  # pyright: ignore[reportArgumentType]
        bar_repository=_Bars(bars),  # pyright: ignore[reportArgumentType]
        calendar=Continuous24x7Calendar(),
        order_repository=_Sink(),  # pyright: ignore[reportArgumentType]
        trade_repository=trades,  # pyright: ignore[reportArgumentType]
    )
    config = BacktestConfig(
        strategy_code="t",
        symbol=_SYM,
        intervals=[entry],
        start_date=_T0,
        end_date=_T0 + timedelta(days=365),
        initial_capital=1_000_000.0,
        slippage_bps=0.0,
    )
    result = await runner.run(config)
    assert result.status == "finished", result.error_message
    return result, trades.saved


def _buy_stop_on_first_bar(stop: float, sl: float, tp: float | None = None):
    async def place(event: BarCompletedEvent, broker: PaperBrokerAdapter):
        if event.bar_start != _T0:
            return None
        return OrderAggregate.create(
            subscription_id=_SUB,
            symbol=_SYM,
            side=OrderSide.BUY,
            order_type=OrderType.STOP_MARKET,
            quantity=1.0,
            stop_price=stop,
            sl_price=sl,
            tp_price=tp,
        )

    return place


# Signal bucket [T0, T0+15m) is flat 1m bars; the fill bucket's 1m bars are given.
def _scenario(fill_bucket: list[tuple[float, float, float, float]]) -> dict[str, list[Bar]]:
    ones = [_flat("1m", _T0 + i * _M) for i in range(15)]
    for i, (o, h, lo, c) in enumerate(fill_bucket):
        ones.append(_bar("1m", _T0 + _Q + i * _M, o, h, lo, c))
    ones += [_flat("1m", _T0 + 2 * _Q + i * _M, 102.0) for i in range(15)]
    quarters = [_quarter(_T0 + k * _Q, ones) for k in range(3)]
    return {"1m": ones, "15m": quarters}


async def test_stop_whose_bucket_touched_sl_before_entry_is_not_stopped_out() -> None:
    # Minute 0 dips to the SL before the stop fills on minute 1; then the TP is reached.
    bars = _scenario(
        [(100.0, 100.0, 98.5, 99.5), (99.5, 101.5, 99.5, 101.2), (101.2, 103.5, 101.2, 103.2)]
    )
    _, trades = await _run(bars, _buy_stop_on_first_bar(stop=101.0, sl=99.0, tp=103.0))
    assert len(trades) == 1
    assert trades[0].entry_time == _T0 + _Q + _M
    assert trades[0].exit_price == 103.0
    assert trades[0].exit_time == _T0 + _Q + 2 * _M


async def test_stop_whose_sl_is_touched_after_entry_is_stopped_out_at_sl() -> None:
    bars = _scenario([(100.0, 101.5, 100.0, 101.2), (101.2, 101.2, 98.5, 98.8)])
    _, trades = await _run(bars, _buy_stop_on_first_bar(stop=101.0, sl=99.0))
    assert len(trades) == 1
    assert trades[0].entry_time == _T0 + _Q
    assert trades[0].exit_price == 99.0
    assert trades[0].exit_time == _T0 + _Q + _M


async def test_tp_is_checked_from_the_1m_bar_after_the_fill() -> None:
    # The fill minute also trades through the TP; the TP takes effect on the next minute.
    bars = _scenario([(100.0, 103.5, 100.0, 102.0), (102.0, 103.2, 102.0, 103.1)])
    _, trades = await _run(bars, _buy_stop_on_first_bar(stop=101.0, sl=99.0, tp=103.0))
    assert len(trades) == 1
    assert trades[0].entry_time == _T0 + _Q
    assert trades[0].exit_price == 103.0
    assert trades[0].exit_time == _T0 + _Q + _M


async def test_no_stop_fills_on_a_1m_bar_starting_before_signal_bar_close() -> None:
    # The signal bucket's last minute trades above the stop; it is replayed before the signal.
    bars = _scenario([(100.0, 100.5, 99.8, 100.2)] * 5 + [(100.2, 101.5, 100.2, 101.2)])
    ones = bars["1m"]
    ones[14] = _bar("1m", _T0 + 14 * _M, 100.0, 102.0, 100.0, 100.0)
    bars["15m"] = [_quarter(_T0 + k * _Q, ones) for k in range(3)]
    _, trades = await _run(bars, _buy_stop_on_first_bar(stop=101.0, sl=95.0, tp=101.1))
    assert len(trades) == 1
    assert trades[0].entry_time == _T0 + _Q + 5 * _M


async def test_bucket_without_1m_bars_fills_by_the_coarse_rule() -> None:
    ones = [_flat("1m", _T0 + i * _M) for i in range(15)]
    quarters = [
        _quarter(_T0, ones),
        _bar("15m", _T0 + _Q, 100.0, 101.5, 98.5, 100.0),
        _flat("15m", _T0 + 2 * _Q),
    ]
    _, trades = await _run({"1m": ones, "15m": quarters}, _buy_stop_on_first_bar(101.0, 99.0))
    assert len(trades) == 1
    assert trades[0].entry_time == _T0 + _Q
    assert trades[0].exit_time == _T0 + _Q
    assert trades[0].exit_price == 99.0


# A smooth 1m walk and its 15m bars, so a stop strategy trades many times.
def _walk(days: int = 3) -> dict[str, list[Bar]]:
    ones: list[Bar] = []
    prev = 100.0
    for i in range(days * 1440):
        close = 100 + 3 * math.sin(2 * math.pi * i / 400) + 0.4 * math.sin(2 * math.pi * i / 13)
        ones.append(
            _bar("1m", _T0 + i * _M, prev, max(prev, close) + 0.05, min(prev, close) - 0.05, close)
        )
        prev = close
    quarters = [_quarter(_T0 + k * _Q, ones) for k in range(days * 96)]
    return {"1m": ones, "15m": quarters}


async def _breakout(event: BarCompletedEvent, broker: PaperBrokerAdapter):
    if await broker.get_positions():
        return None
    return OrderAggregate.create(
        subscription_id=_SUB,
        symbol=_SYM,
        side=OrderSide.BUY,
        order_type=OrderType.STOP_MARKET,
        quantity=1.0,
        stop_price=event.high + 0.05,
        sl_price=event.low - 0.05,
        tp_price=event.high + 0.6,
    )


def _key(t) -> tuple:
    return (t.direction, t.entry_time, t.exit_time, t.entry_price, t.exit_price, t.quantity, t.pnl)


async def test_without_1m_coverage_trades_equal_the_single_stream_run() -> None:
    walk = _walk()
    # 1m bars that start after the run start do not switch the run to 1m fills.
    late = {"1m": [b for b in walk["1m"] if b.datetime > _T0 + _Q], "15m": walk["15m"]}
    coarse = {"15m": walk["15m"]}
    late_result, late_trades = await _run(late, _breakout)
    coarse_result, coarse_trades = await _run(coarse, _breakout)
    assert late_result.config_snapshot["fill_interval"] == "15m"
    assert coarse_result.config_snapshot["fill_interval"] == "15m"
    assert coarse_trades
    assert [_key(t) for t in late_trades] == [_key(t) for t in coarse_trades]


async def test_simulation_clock_never_decreases_in_a_merged_run() -> None:
    walk = _walk()
    # A bucket without 1m bars and 1m bars after the last entry bar.
    gap = _T0 + 40 * _Q
    walk["1m"] = [b for b in walk["1m"] if not gap <= b.datetime < gap + _Q]
    walk["15m"] = walk["15m"][:-2]
    seen: list[BarCompletedEvent] = []
    result, _ = await _run(walk, _breakout, seen=seen)
    assert result.config_snapshot["fill_interval"] == "1m"
    clocks = [e.occurred_at for e in seen]
    assert clocks == sorted(clocks)
    assert any(e.interval == "1m" and e.bar_start == gap for e in seen)
    assert seen[-1].interval == "1m"


async def test_every_trade_exits_at_or_after_its_entry() -> None:
    _, trades = await _run(_walk(), _breakout)
    assert len(trades) > 10
    assert all(t.exit_time >= t.entry_time for t in trades)


async def test_equity_curve_has_one_point_per_entry_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    marks: list[datetime] = []
    original = BacktestReportAppService.mark_to_market

    def spy(self, timestamp: datetime, total_equity: float) -> None:
        marks.append(timestamp)
        original(self, timestamp, total_equity)

    monkeypatch.setattr(BacktestReportAppService, "mark_to_market", spy)
    walk = _walk()
    await _run(walk, _breakout)
    assert marks == [b.datetime for b in walk["15m"]]


async def test_snapshot_records_the_fill_interval() -> None:
    merged, _ = await _run(
        _scenario([(100.0, 100.5, 99.8, 100.2)]), _buy_stop_on_first_bar(101.0, 99.0)
    )
    coarse_bars = _scenario([(100.0, 100.5, 99.8, 100.2)])
    coarse_bars.pop("1m")
    coarse, _ = await _run(coarse_bars, _buy_stop_on_first_bar(101.0, 99.0))
    assert merged.config_snapshot["fill_interval"] == "1m"
    assert coarse.config_snapshot["fill_interval"] == "15m"
