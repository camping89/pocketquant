from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services import check_strategy_inputs
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


# Five entry bars with no setup precede the decision bar.
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
    assert [r["interval"] for r in readings[:3]] == ["4h", "1h", "15m"]
    assert [r["name"] for r in readings[:3]] == ["macd_hist_slope", "force_index", "trigger"]
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


# Top bars ten wide whose closes move by at most five, so every true range is 10 and ATR is 10.
def _wide(closes: list[float]) -> list[Bar]:
    return [
        Bar(
            symbol=b.symbol,
            interval=b.interval,
            datetime=b.datetime,
            open=b.close,
            high=b.close + 5,
            low=b.close - 5,
            close=b.close,
            volume=1.0,
        )
        for b in _bars("4h", closes)
    ]


def _with_atr_10(bar: dict) -> dict:
    bar["context"]["4h"] = _wide([b.close for b in bar["context"]["4h"]])
    return bar


def _reading(s: TripleScreenStrategyService, name: str):
    assert s.snapshot is not None
    return next(r["value"] for r in s.snapshot["readings"] if r["name"] == name)


async def _after(
    params: dict, lows_highs: list[tuple[float, float]]
) -> TripleScreenStrategyService:
    s = TripleScreenStrategyService(_cfg(**params))
    await s.on_start()
    for i, (low, high) in enumerate(lows_highs):
        bar = _entry(high, low, (high + low) / 2, _TS + i * _STEP, TOP_FLAT, MID_DIP)
        assert await s.on_bar_completed(bar) is None
    return s


def _long_signal_bar(i: int, high: float = 101.2, low: float = 100.2) -> dict:
    return _with_atr_10(_entry(high, low, 101.0, _TS + i * _STEP, TOP_UP, MID_DIP))


def _short_signal_bar(i: int, high: float = 99.8, low: float = 98.8) -> dict:
    return _with_atr_10(_entry(high, low, 99.0, _TS + i * _STEP, TOP_DOWN, MID_POP))


@pytest.mark.asyncio
async def test_the_stoploss_window_spans_lookback_times_ratio_entry_bars_including_the_signal_bar():  # noqa: E501
    history = [(90.0, 100.5), (95.0, 100.5), (96.0, 100.5), (97.0, 100.5)]
    one = await _after({"stoploss_lookback": 1}, history)
    sig = await one.on_bar_completed(_long_signal_bar(4, low=98.0))
    assert sig is not None and sig.stop_loss_price == 95.0
    two = await _after({"stoploss_lookback": 2}, history)
    sig = await two.on_bar_completed(_long_signal_bar(4, low=98.0))
    assert sig is not None and sig.stop_loss_price == 90.0
    signal_bar_low = await _after({"stoploss_lookback": 1}, [(99.0, 100.5)] * 4)
    sig = await signal_bar_low.on_bar_completed(_long_signal_bar(4, low=98.0))
    assert sig is not None and sig.stop_loss_price == 98.0


@pytest.mark.asyncio
async def test_the_entry_buffer_moves_the_stop_order_by_x_atr_on_both_sides() -> None:
    params = {"entry_type": "stop", "entry_buffer_atr": 0.1}
    s = await _primed(**params)
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED))
    assert sig is not None and sig.entry_price == pytest.approx(101.2 + 1.0)
    s = await _primed(**params)
    sig = await s.on_bar_completed(_short_signal_bar(_PRIMED))
    assert sig is not None and sig.entry_price == pytest.approx(98.8 - 1.0)


@pytest.mark.asyncio
async def test_the_stoploss_buffer_moves_the_swing_stop_outward_by_x_atr_on_both_sides() -> None:
    s = await _primed(stoploss_buffer_atr=0.2)
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED))
    assert sig is not None and sig.stop_loss_price == pytest.approx(99.5 - 2.0)
    s = await _primed(stoploss_buffer_atr=0.2)
    sig = await s.on_bar_completed(_short_signal_bar(_PRIMED))
    assert sig is not None and sig.stop_loss_price == pytest.approx(100.5 + 2.0)


@pytest.mark.asyncio
async def test_the_minimum_stop_widens_a_closer_stop_and_keeps_a_farther_one() -> None:
    s = await _primed(min_stop_atr=0.5)
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED))
    assert sig is not None and sig.stop_loss_price == pytest.approx(101.0 - 5.0)
    assert _reading(s, "swing_stop") == 99.5
    assert _reading(s, "sl") == pytest.approx(96.0)
    s = await _primed(min_stop_atr=0.5)
    sig = await s.on_bar_completed(_short_signal_bar(_PRIMED))
    assert sig is not None and sig.stop_loss_price == pytest.approx(99.0 + 5.0)
    s = await _primed(min_stop_atr=0.1)
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED))
    assert sig is not None and sig.stop_loss_price == 99.5


@pytest.mark.asyncio
async def test_the_take_profit_is_the_farther_of_the_swing_level_and_the_risk_reward_floor() -> (
    None
):
    params = {"exit_mode": "sl_tp", "risk_reward": 1.0, "takeprofit_lookback": 1}
    # The 110 high is in the stop-loss window but outside the four-bar take-profit window.
    history = [(99.5, 110.0), (99.5, 100.5), (99.5, 100.5), (99.5, 105.0), (99.5, 100.5)]
    s = await _after(params, history)
    sig = await s.on_bar_completed(_long_signal_bar(len(history)))
    assert sig is not None and sig.take_profit_price == 105.0
    assert _reading(s, "tp") == 105.0
    s = await _after(params, [(99.5, 100.5)] * 5)
    sig = await s.on_bar_completed(_long_signal_bar(5))
    assert sig is not None and sig.take_profit_price == pytest.approx(101.0 + 1.5)
    s = await _after(params, [(95.0, 100.5), (99.5, 100.5), (99.5, 100.5)])
    sig = await s.on_bar_completed(_short_signal_bar(3))
    assert sig is not None and sig.take_profit_price == 95.0


@pytest.mark.asyncio
async def test_takeprofit_lookback_is_ignored_in_strategy_exit_mode() -> None:
    s = await _primed(exit_mode="strategy", takeprofit_lookback=5)
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED))
    assert sig is not None and sig.take_profit_price is None


@pytest.mark.asyncio
async def test_atr_uses_only_closed_top_interval_bars() -> None:
    s = await _primed(entry_type="stop", entry_buffer_atr=0.1)
    # A wide entry bar and the middle interval leave the top-interval ATR at 10.
    sig = await s.on_bar_completed(_long_signal_bar(_PRIMED, high=130.0, low=80.0))
    assert sig is not None and sig.entry_price == pytest.approx(131.0)
    assert _reading(s, "atr") == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_atr_parameters_skip_while_atr_is_warming_up() -> None:
    fast = {"macd_fast": 2, "macd_slow": 5, "macd_signal": 3}
    short_top = [100.0] * 8 + [101.0, 103.0]

    async def decide(**params):
        s = await _primed(**fast, **params)
        sig = await s.on_bar_completed(_entry(101.2, 100.2, 101.0, _ts(), short_top, MID_DIP))
        assert s.snapshot is not None
        return sig, s.snapshot["decision"]

    sig, decision = await decide(min_stop_atr=0.5)
    assert sig is None
    assert decision == {"action": "skip", "reason": "top interval warming up"}
    sig, _ = await decide()
    assert sig is not None and sig.direction == Direction.LONG


def test_the_old_stop_lookback_key_is_rejected_on_submit() -> None:
    with pytest.raises(DomainError):
        check_strategy_inputs("triple_screen", ["15m", "1h", "4h"], {"stop_lookback": 5})


def test_a_negative_nan_or_infinite_atr_parameter_is_rejected() -> None:
    for name in ("entry_buffer_atr", "stoploss_buffer_atr", "min_stop_atr"):
        for bad in (-0.1, math.nan, math.inf):
            with pytest.raises(ValueError, match=name):
                TripleScreenStrategyService(_cfg(**{name: bad}))


def test_stoploss_lookback_zero_is_rejected() -> None:
    with pytest.raises(ValueError, match="stoploss_lookback"):
        TripleScreenStrategyService(_cfg(stoploss_lookback=0))


def test_a_lookback_beyond_the_500_bar_warm_up_is_rejected() -> None:
    TripleScreenStrategyService(_cfg(stoploss_lookback=125, takeprofit_lookback=125))
    for params in ({"stoploss_lookback": 126}, {"takeprofit_lookback": 126}):
        with pytest.raises(ValueError, match="500"):
            TripleScreenStrategyService(_cfg(**params))


def test_a_float_value_is_accepted_for_each_atr_parameter() -> None:
    params = {"entry_buffer_atr": 0.1, "stoploss_buffer_atr": 0.25, "min_stop_atr": 0.5}
    check_strategy_inputs("triple_screen", ["15m", "1h", "4h"], params)
    s = TripleScreenStrategyService(_cfg(**params))
    assert (s.entry_buffer_atr, s.stoploss_buffer_atr, s.min_stop_atr) == (0.1, 0.25, 0.5)
