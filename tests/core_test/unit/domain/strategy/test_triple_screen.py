from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services.triple_screen_strategy_service import (
    TripleScreenStrategyService,
)
from pocketquant.core.domain.strategy.value_objects import StrategyConfig

_T0 = datetime(2026, 1, 5, tzinfo=UTC)

TOP_UP = [100.0] * 58 + [101.0, 103.0]
TOP_DOWN = [100.0] * 58 + [99.0, 97.0]
TOP_FLAT = [100.0] * 60
MID_DIP = [100.0] * 10 + [99.0]
MID_POP = [100.0] * 10 + [101.0]


def _cfg(intervals=("15m", "1h", "4h"), **params) -> StrategyConfig:
    return StrategyConfig(
        id="sub-1",
        name="triple_screen",
        symbol="XAUUSD:EXNESS",
        intervals=list(intervals),
        parameters=params,
    )


def _bars(interval: str, closes: list[float], volume: float = 1.0, t0: datetime = _T0) -> list[Bar]:
    step = timedelta(seconds=INTERVAL_SECONDS[interval])
    return [
        Bar(
            symbol="XAUUSD:EXNESS",
            interval=Interval(interval),
            datetime=t0 + i * step,
            open=c,
            high=c,
            low=c,
            close=c,
            volume=volume,
        )
        for i, c in enumerate(closes)
    ]


def _entry(
    high: float, low: float, close: float, ts: datetime, top=TOP_FLAT, middle=MID_DIP
) -> dict:
    return {
        "symbol": "XAUUSD:EXNESS",
        "interval": "15m",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
        "timestamp": ts,
        "context": {"4h": _bars("4h", top), "1h": _bars("1h", middle)},
    }


def _fill(side: str) -> SimpleNamespace:
    return SimpleNamespace(side=OrderSide[side])


_TS = _T0 + timedelta(days=20)
_STEP = timedelta(minutes=15)
_PRIMED = 5


# Five entry bars with no setup fill the stop lookback before the decision bar.
async def _primed(**params) -> TripleScreenStrategyService:
    s = TripleScreenStrategyService(_cfg(**params))
    await s.on_start()
    for i in range(_PRIMED):
        assert await s.on_bar_completed(_entry(100.5, 99.5, 100.0, _TS + i * _STEP)) is None
    return s


def _ts(i: int = 0) -> datetime:
    return _TS + (_PRIMED + i) * _STEP


async def _long_market(s: TripleScreenStrategyService, i: int = 0):
    return await s.on_bar_completed(_entry(101.2, 100.2, 101.0, _ts(i), TOP_UP, MID_DIP))


def test_two_intervals_are_rejected() -> None:
    with pytest.raises(ValueError):
        TripleScreenStrategyService(_cfg(intervals=("15m", "1h")))


def test_an_unknown_entry_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        TripleScreenStrategyService(_cfg(entry_type="limit"))


def test_an_unknown_exit_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        TripleScreenStrategyService(_cfg(exit_mode="trailing"))


@pytest.mark.asyncio
async def test_the_top_interval_warming_up_skips() -> None:
    s = await _primed()
    bar = _entry(101.2, 100.2, 101.0, _ts(), [100.0] * 30, MID_DIP)
    assert await s.on_bar_completed(bar) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["action"] == "skip"


@pytest.mark.asyncio
async def test_market_long_when_the_tide_rises_and_force_is_below_zero() -> None:
    s = await _primed()
    sig = await _long_market(s)
    assert sig is not None
    assert sig.direction == Direction.LONG
    assert sig.entry_type == "market"
    assert sig.stop_loss_price is not None and sig.take_profit_price is not None
    assert sig.stop_loss_price < 101.0 < sig.take_profit_price


@pytest.mark.asyncio
async def test_market_short_mirrors_the_long() -> None:
    s = await _primed()
    sig = await s.on_bar_completed(_entry(99.8, 98.8, 99.0, _ts(), TOP_DOWN, MID_POP))
    assert sig is not None
    assert sig.direction == Direction.SHORT
    assert sig.stop_loss_price is not None and sig.take_profit_price is not None
    assert sig.take_profit_price < 99.0 < sig.stop_loss_price


@pytest.mark.asyncio
async def test_a_stop_entry_rests_at_the_entry_bar_high() -> None:
    s = await _primed(entry_type="stop")
    bar = _entry(101.2, 100.2, 101.0, _ts(), TOP_UP, MID_DIP)
    sig = await s.on_bar_completed(bar)
    assert sig is not None
    assert sig.entry_type == "stop"
    assert sig.entry_price == bar["high"]


@pytest.mark.asyncio
async def test_the_stop_is_sent_again_each_bar_while_the_setup_holds() -> None:
    s = await _primed(entry_type="stop")
    prices = []
    for i, high in enumerate((101.2, 101.0, 101.0)):
        sig = await s.on_bar_completed(_entry(high, 100.2, 100.8, _ts(i), TOP_UP, MID_DIP))
        assert sig is not None and sig.entry_type == "stop"
        prices.append(sig.entry_price)
    assert prices == [101.2, 101.0, 101.0]


@pytest.mark.asyncio
async def test_exit_when_the_setup_is_gone_with_a_stop_armed() -> None:
    s = await _primed(entry_type="stop")
    assert await _long_market(s) is not None
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_FLAT))
    assert sig is not None
    assert sig.direction == Direction.EXIT


@pytest.mark.asyncio
async def test_a_fresh_start_holds_no_stop() -> None:
    s = await _primed(entry_type="stop")
    assert await _long_market(s) is not None
    await s.on_start()
    assert await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_FLAT)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["reason"] == "no setup"
    sig = await _long_market(s, 2)
    assert sig is not None
    assert sig.entry_type == "stop"


@pytest.mark.asyncio
async def test_a_fill_while_flat_takes_the_side_of_the_fill() -> None:
    s = await _primed(entry_type="stop", exit_mode="strategy")
    await s.on_order_filled(_fill("BUY"), 101.0)
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(), TOP_DOWN))
    assert sig is not None
    assert sig.direction == Direction.EXIT


@pytest.mark.asyncio
async def test_strategy_mode_sets_no_take_profit_and_exits_on_a_tide_flip() -> None:
    s = await _primed(exit_mode="strategy")
    sig = await _long_market(s)
    assert sig is not None
    assert sig.take_profit_price is None
    await s.on_order_filled(_fill("BUY"), 101.0)
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_DOWN))
    assert sig is not None
    assert sig.direction == Direction.EXIT


@pytest.mark.asyncio
async def test_sl_tp_mode_holds_a_position_on_a_tide_flip() -> None:
    s = await _primed(exit_mode="sl_tp")
    assert await _long_market(s) is not None
    await s.on_order_filled(_fill("BUY"), 101.0)
    assert await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_DOWN)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["action"] == "hold"


@pytest.mark.asyncio
async def test_a_rejected_exit_keeps_the_position_and_exits_again() -> None:
    s = await _primed(exit_mode="strategy")
    await s.on_order_filled(_fill("BUY"), 101.0)
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(), TOP_DOWN))
    assert sig is not None and sig.direction == Direction.EXIT
    await s.on_order_rejected("inflight")
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_DOWN))
    assert sig is not None and sig.direction == Direction.EXIT


@pytest.mark.asyncio
async def test_a_rejected_setup_gone_exit_is_sent_again() -> None:
    s = await _primed(entry_type="stop")
    assert await _long_market(s) is not None
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_FLAT))
    assert sig is not None and sig.direction == Direction.EXIT
    await s.on_order_rejected("inflight")
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(2), TOP_FLAT))
    assert sig is not None and sig.direction == Direction.EXIT


@pytest.mark.asyncio
async def test_a_rejected_market_entry_clears_the_position() -> None:
    s = await _primed(exit_mode="strategy")
    assert await _long_market(s) is not None
    await s.on_order_rejected("zero position size")
    sig = await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(1), TOP_DOWN))
    assert sig is None or sig.direction != Direction.EXIT


@pytest.mark.asyncio
async def test_the_snapshot_reports_three_readings_and_a_decision() -> None:
    s = await _primed()
    await _long_market(s)
    assert s.snapshot is not None
    readings = s.snapshot["readings"]
    assert [r["interval"] for r in readings] == ["4h", "1h", "15m"]
    assert [r["name"] for r in readings] == ["macd_hist_slope", "force_index", "trigger"]
    assert all("value" in r and "ok" in r for r in readings)
    assert {"action", "reason"} <= set(s.snapshot["decision"])


@pytest.mark.asyncio
async def test_a_leaked_current_bucket_changes_the_decision() -> None:
    # The entry bar opens a new 4h bucket, so the newest closed 4h bar is the previous one.
    bucket = _T0 + timedelta(days=30)
    top_a = _bars("4h", TOP_UP, t0=bucket - 60 * timedelta(hours=4))
    leaked = Bar(
        symbol="XAUUSD:EXNESS",
        interval=Interval.HOUR_4,
        datetime=bucket,
        open=90.0,
        high=90.0,
        low=90.0,
        close=90.0,
        volume=1.0,
    )
    middle = _bars("1h", MID_DIP, t0=bucket - 11 * timedelta(hours=1))

    decisions = []
    for top in (top_a, [*top_a, leaked]):
        s = await _primed()
        bar = _entry(101.2, 100.2, 101.0, bucket)
        bar["context"] = {"4h": top, "1h": middle}
        sig = await s.on_bar_completed(bar)
        decisions.append(sig.direction if sig else None)
    assert decisions[0] == Direction.LONG
    assert decisions[1] != Direction.LONG


@pytest.mark.asyncio
async def test_the_tide_reading_is_computed_from_the_given_bars_only() -> None:
    s = await _primed()
    await s.on_bar_completed(_entry(101.0, 100.0, 100.5, _ts(), TOP_FLAT))
    assert s.snapshot is not None
    assert s.snapshot["readings"][0]["value"] == 0.0
