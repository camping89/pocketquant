# Leverage scales the exposure cap, so a small leveraged account reaches the minimum lot.

from __future__ import annotations

import pytest

from pocketquant.core.domain.risk import PositionCalculatorDomainService
from pocketquant.core.domain.risk.value_objects import RiskConfig

BALANCE = 250.0
EXNESS_RISK = RiskConfig(leverage=1000, risk_per_trade=0.10)
# One minimum lot (0.01) in units: gold has 100 oz per lot, EURUSD 100 000.
GOLD_MIN_UNITS = 1.0
EURUSD_MIN_UNITS = 1000.0


@pytest.mark.parametrize(
    ("entry", "stop", "min_units"),
    [(4180.0, 4160.0, GOLD_MIN_UNITS), (1.12, 1.118, EURUSD_MIN_UNITS)],
)
def test_leveraged_risk_reaches_the_minimum_lot(
    entry: float, stop: float, min_units: float
) -> None:
    leveraged = PositionCalculatorDomainService.calculate(BALANCE, entry, stop, EXNESS_RISK)
    unleveraged = PositionCalculatorDomainService.calculate(BALANCE, entry, stop, RiskConfig())

    assert leveraged.size >= min_units
    assert unleveraged.size < min_units


def test_leverage_one_keeps_the_unleveraged_size() -> None:
    # 200 USD at risk over a 10 USD stop is 20 units; the 10% cap of 10 000 at 100 is 10.
    calc = PositionCalculatorDomainService.calculate(
        10_000.0, 100.0, 90.0, RiskConfig(leverage=1.0)
    )

    assert calc.size == 10.0
    assert calc == PositionCalculatorDomainService.calculate(10_000.0, 100.0, 90.0)


def test_leverage_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="leverage"):
        RiskConfig(leverage=0.5)
