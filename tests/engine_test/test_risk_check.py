"""RiskCheckHandler accepts only entry signals and never divides by zero equity."""

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


@pytest.mark.parametrize("direction", [Direction.EXIT, Direction.FLAT])
def test_exit_and_flat_signals_are_rejected(direction: Direction) -> None:
    valid, reason = RiskCheckHandler().validate(_signal(direction), _ACCOUNT, _position())

    assert valid is False
    assert direction.value in reason


def test_zero_equity_with_an_open_position_is_rejected() -> None:
    account = AccountBalance(total_equity=0.0, available_balance=100.0)

    valid, _ = RiskCheckHandler().validate(_signal(Direction.LONG), account, _position())

    assert valid is False
