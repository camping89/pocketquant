from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from pocketquant.core.common.exceptions import DomainError
from pocketquant.core.domain.order import OrderSide
from pocketquant.core.domain.strategy.enums import Direction
from pocketquant.core.domain.strategy.services import check_strategy_inputs
from pocketquant.core.domain.strategy.services.hitnrun2_strategy_service import (
    HitNRun2StrategyService,
)
from pocketquant.core.domain.strategy.value_objects import StrategyConfig
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec

# Mirrors the seeded gold spec: a round trip costs 0.035 * 2 + 0.08 = 0.15 in price units.
GOLD = ContractSpec(multiplier=1.0, tick_size=0.001, commission_per_contract=0.035, spread=0.08)

_T0 = datetime(2026, 1, 5, tzinfo=UTC)

TRIGGER = (99.5, 98.9, 99.0)


def _cfg(intervals=("1m",), spec=LINEAR_SPEC, **params) -> StrategyConfig:
    return StrategyConfig(
        id="sub-1",
        name="hitnrun2",
        symbol="XAUUSD:EXNESS",
        intervals=list(intervals),
        parameters={
            "entry_lookback_bars": 2,
            "sl_lookback_bars": 8,
            "tp_lookback_bars": 3,
            **params,
        },
        contract_spec=spec,
    )


async def _strategy(spec=LINEAR_SPEC, **params) -> HitNRun2StrategyService:
    s = HitNRun2StrategyService(_cfg(spec=spec, **params))
    await s.on_start()
    return s


def _bar(high: float, low: float, close: float, i: int) -> dict:
    return {
        "symbol": "XAUUSD:EXNESS",
        "interval": "1m",
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1.0,
        "timestamp": _T0 + timedelta(minutes=i),
    }


async def _warm(
    s: HitNRun2StrategyService,
    deep: float | None = 98.0,
    high3: float | None = None,
    high7: float | None = None,
) -> None:
    for i in range(8):
        high, low = 100.5, 99.5
        if i == 3 and deep is not None:
            low = deep
        if i == 3 and high3 is not None:
            high = high3
        if i == 7 and high7 is not None:
            high = high7
        assert await s.on_bar_completed(_bar(high, low, 100.0, i)) is None


@dataclass(frozen=True)
class _Fill:
    side: OrderSide


def _fill(side: str) -> _Fill:
    return _Fill(OrderSide[side])


async def test_more_than_one_interval_is_rejected():
    with pytest.raises(ValueError):
        HitNRun2StrategyService(_cfg(intervals=("1m", "5m")))


async def test_an_unknown_direction_is_rejected():
    with pytest.raises(ValueError):
        HitNRun2StrategyService(_cfg(direction="up"))


async def test_a_negative_cost_multiple_is_rejected():
    with pytest.raises(ValueError):
        HitNRun2StrategyService(_cfg(min_cost_multiple=-1.0))


async def test_check_strategy_inputs_accepts_one_interval_and_rejects_two():
    assert (
        check_strategy_inputs("hitnrun2", ["1m"], {"min_cost_multiple": 2})
        is HitNRun2StrategyService
    )
    with pytest.raises(DomainError) as exc:
        check_strategy_inputs("hitnrun2", ["1m", "5m"], {})
    assert exc.value.error_code == "INVALID_PARAMETERS"


async def test_the_sl_window_warms_up_first():
    s = await _strategy()
    await _warm(s)
    assert s.snapshot is not None
    assert s.snapshot["decision"] == {"action": "skip", "reason": "warming up"}


async def test_long_entry_on_a_close_below_the_previous_entry_window_low():
    s = await _strategy()
    await _warm(s)
    # The trigger's own low 98.9 is above its close, so a signal also proves the bar is
    # not in its own window.
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG
    assert signal.entry_type == "market"
    assert signal.entry_price == 99.0
    assert signal.stop_loss_price == pytest.approx(98.01)
    assert signal.take_profit_price == pytest.approx(100.98)
    assert signal.entry_logic == "hitnrun2:breakdown"


async def test_short_entry_on_a_close_above_the_previous_entry_window_high():
    s = await _strategy()
    await _warm(s, deep=None, high3=102.0)
    signal = await s.on_bar_completed(_bar(101.2, 100.6, 101.0, 8))
    assert signal is not None
    assert signal.direction == Direction.SHORT
    assert signal.stop_loss_price == pytest.approx(102.0)
    assert signal.take_profit_price == pytest.approx(98.98)
    assert signal.entry_logic == "hitnrun2:breakup"


async def test_the_sl_is_the_window_low_capped_at_max_loss_pct():
    s = await _strategy()
    await _warm(s, deep=50.0)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.stop_loss_price == pytest.approx(98.01)

    s = await _strategy()
    await _warm(s, deep=98.7)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.stop_loss_price == pytest.approx(98.7)


async def test_the_tp_takes_the_window_high_above_the_min_profit():
    s = await _strategy()
    await _warm(s, high7=105.0)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.take_profit_price == pytest.approx(105.0)


async def test_direction_long_ignores_a_breakup():
    s = await _strategy(direction="long")
    await _warm(s, deep=None, high3=102.0)
    assert await s.on_bar_completed(_bar(101.2, 100.6, 101.0, 8)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["reason"] == "no breakout"


async def test_one_position_until_the_opposite_fill():
    s = await _strategy()
    await _warm(s)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG
    await s.on_order_filled(_fill("BUY"), 99.0)
    assert await s.on_bar_completed(_bar(99.0, 98.5, 98.6, 9)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["reason"] == "position held"
    await s.on_order_filled(_fill("SELL"), 98.6)
    signal = await s.on_bar_completed(_bar(98.6, 98.2, 98.3, 10))
    assert signal is not None
    assert signal.direction == Direction.LONG


async def test_a_rejected_entry_clears_the_position():
    s = await _strategy()
    await _warm(s)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG
    await s.on_order_rejected("zero position size")
    signal = await s.on_bar_completed(_bar(99.0, 98.5, 98.6, 9))
    assert signal is not None
    assert signal.direction == Direction.LONG


async def test_a_restored_direction_blocks_an_entry():
    s = await _strategy()
    await _warm(s)
    s.restore_direction(Direction.SHORT)
    assert await s.on_bar_completed(_bar(*TRIGGER, 8)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["reason"] == "position held"


async def test_an_entry_whose_nearer_exit_is_under_the_cost_multiple_is_skipped():
    s = await _strategy(spec=GOLD)
    await _warm(s, deep=98.7)
    # The SL distance 0.3 is under 3 x 0.15.
    assert await s.on_bar_completed(_bar(*TRIGGER, 8)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"] == {
        "action": "skip",
        "reason": "nearer exit under the cost multiple",
    }


async def test_an_entry_whose_nearer_exit_covers_the_cost_multiple_is_taken():
    s = await _strategy(spec=GOLD)
    await _warm(s, deep=98.0)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG


async def test_the_cost_comes_from_the_contract_spec():
    s = await _strategy(spec=LINEAR_SPEC)
    await _warm(s, deep=98.7)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG

    s = await _strategy(spec=GOLD, min_cost_multiple=1.0)
    await _warm(s, deep=98.7)
    signal = await s.on_bar_completed(_bar(*TRIGGER, 8))
    assert signal is not None
    assert signal.direction == Direction.LONG


async def test_an_entry_with_its_stop_on_the_wrong_side_is_skipped():
    s = await _strategy(spec=LINEAR_SPEC)
    await _warm(s, deep=None)
    # The SL window low 99.5 is above the close 99.0.
    assert await s.on_bar_completed(_bar(*TRIGGER, 8)) is None
    assert s.snapshot is not None
    assert s.snapshot["decision"]["reason"] == "nearer exit under the cost multiple"
