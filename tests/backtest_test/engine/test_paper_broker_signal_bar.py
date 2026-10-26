"""Replay stamps each bar event with sim time, so the paper broker does not let the
bar that produced an entry signal close the position it just opened.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.backtest import BacktestConfig
from pocketquant.core.domain.bar import BarCompletedEvent
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.shared import Interval
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.historical_replay_app_service import HistoricalReplayAppService

_SYM = "BTCUSDT:BINANCE"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_T1 = _T0 + timedelta(minutes=1)


@pytest.fixture(autouse=True)
def _clear_sim_time() -> Iterator[None]:
    yield
    clear_simulation_time()


async def _bars() -> AsyncIterator[Bar]:
    # Both bars dip to 97, below the SL of 98.
    for t in (_T0, _T1):
        yield Bar(
            symbol=_SYM,
            interval=Interval.MINUTE_1,
            datetime=t,
            open=100.0,
            high=101.0,
            low=97.0,
            close=100.0,
        )


async def test_replay_signal_bar_does_not_close_its_entry() -> None:
    bus = EventBus()
    broker = PaperBrokerAdapter(initial_balance=1_000_000.0, fill_delay_ms=0, event_bus=bus)
    closed: list[TradeClosedEvent] = []
    await broker.subscribe_trades(lambda t: closed.append(t))

    async def strategy(event: BarCompletedEvent) -> None:
        if event.bar_start == _T0:
            await broker.submit_order(
                OrderAggregate.create(
                    subscription_id="t",
                    symbol=_SYM,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=1.0,
                    price=100.0,
                    sl_price=98.0,
                )
            )

    bus.subscribe(BarCompletedEvent, strategy)
    await broker.connect()  # subscribes after the strategy, as in StrategyAppService
    config = BacktestConfig(
        strategy_code="t", symbol=_SYM, interval="1m", start_date=_T0, end_date=_T1
    )
    await HistoricalReplayAppService(bus).replay(config, _bars())

    assert len(closed) == 1
    assert closed[0].exit_time == _T1
