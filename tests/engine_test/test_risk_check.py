from datetime import UTC, datetime

import pytest

from pocketquant.core.domain.brokers.value_objects import AccountBalance
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.strategy import Direction, Signal
from pocketquant.engine.execution.risk_check import RiskCheckHandler


def _signal(direction: Direction) -> Signal:
    return Signal(
        symbol="BTCUSDT:BINANCE",
        direction=direction,
        confidence=1.0,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        subscription_id="s1",
    )


def _position() -> PositionAggregate:
    return PositionAggregate.open(
        subscription_id="s1",
        symbol="BTCUSDT:BINANCE",
        side=PositionSide.LONG,
        entry_price=100.0,
        quantity=1.0,
    )


_ACCOUNT = AccountBalance(total_equity=10_000.0, available_balance=10_000.0)


@pytest.mark.parametrize("direction", [Direction.LONG, Direction.SHORT])
def test_an_entry_signal_passes(direction: Direction) -> None:
    assert RiskCheckHandler().validate(_signal(direction), _ACCOUNT, None) == (True, "")


def test_an_exit_with_an_open_position_passes() -> None:
    assert RiskCheckHandler().validate(_signal(Direction.EXIT), _ACCOUNT, _position()) == (
        True,
        "",
    )


def test_an_exit_without_a_position_is_rejected() -> None:
    assert RiskCheckHandler().validate(_signal(Direction.EXIT), _ACCOUNT, None) == (
        False,
        "no open position",
    )


def test_an_exit_passes_with_zero_balance() -> None:
    account = AccountBalance(total_equity=0.0, available_balance=0.0)

    assert RiskCheckHandler().validate(_signal(Direction.EXIT), account, _position()) == (
        True,
        "",
    )


def test_a_flat_signal_is_rejected() -> None:
    valid, reason = RiskCheckHandler().validate(_signal(Direction.FLAT), _ACCOUNT, _position())

    assert valid is False
    assert Direction.FLAT.value in reason


def test_zero_equity_with_an_open_position_is_rejected() -> None:
    account = AccountBalance(total_equity=0.0, available_balance=100.0)

    valid, _ = RiskCheckHandler().validate(_signal(Direction.LONG), account, _position())

    assert valid is False


@pytest.mark.parametrize(
    ("side", "direction"),
    [(PositionSide.LONG, Direction.SHORT), (PositionSide.SHORT, Direction.LONG)],
)
def test_an_opposite_entry_is_rejected(side: PositionSide, direction: Direction) -> None:
    position = PositionAggregate.open(
        subscription_id="s1", symbol="BTCUSDT:BINANCE", side=side, entry_price=100.0, quantity=1.0
    )

    result = RiskCheckHandler().validate(_signal(direction), _ACCOUNT, position)

    assert result == (False, "opposite position open")


def test_a_same_side_entry_still_reaches_the_exposure_check() -> None:
    assert RiskCheckHandler().validate(_signal(Direction.LONG), _ACCOUNT, _position()) == (
        True,
        "",
    )


def test_a_stop_entry_against_an_open_position_is_rejected() -> None:
    stop = Signal(
        symbol="BTCUSDT:BINANCE",
        direction=Direction.LONG,
        confidence=1.0,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        subscription_id="s1",
        entry_price=101.0,
        entry_type="stop",
    )

    assert RiskCheckHandler().validate(stop, _ACCOUNT, _position()) == (False, "position open")
