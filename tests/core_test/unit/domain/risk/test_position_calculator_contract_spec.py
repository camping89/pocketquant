"""Contract-aware sizing: a futures signal sizes in whole contracts."""

from __future__ import annotations

import pytest

from pocketquant.core.domain.risk import PositionCalculatorDomainService
from pocketquant.core.domain.risk.value_objects import RiskConfig
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec

ES = ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0)
# 1_000_000 at a 100% exposure cap affords 4.4 ES contracts of notional, so the
# per-trade risk budget alone decides the size in these tests.
BALANCE = 1_000_000.0


def test_es_balance_affording_1_7_contracts_sizes_one() -> None:
    # 850 USD at risk; a 10-point stop is 500 USD per contract.
    risk = RiskConfig(risk_per_trade=0.00085, max_exposure_percent=1.0)
    calc = PositionCalculatorDomainService.calculate(
        BALANCE, 4500.0, 4490.0, risk, contract_spec=ES
    )

    assert calc.size == 1.0
    assert calc.notional == pytest.approx(4500.0 * 50.0)


def test_exact_whole_multiple_is_not_floored_away() -> None:
    # 1000 USD at risk is exactly 2 contracts at a 10-point stop.
    risk = RiskConfig(risk_per_trade=0.001, max_exposure_percent=1.0)
    calc = PositionCalculatorDomainService.calculate(
        BALANCE, 4500.0, 4490.0, risk, contract_spec=ES
    )

    assert calc.size == 2.0


def test_sub_one_contract_signal_opens_nothing() -> None:
    # 400 USD at risk is 0.8 of a contract.
    risk = RiskConfig(risk_per_trade=0.0004, max_exposure_percent=1.0)
    calc = PositionCalculatorDomainService.calculate(
        BALANCE, 4500.0, 4490.0, risk, contract_spec=ES
    )

    assert (calc.size, calc.notional, calc.risk_amount, calc.est_entry_commission) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )


def test_linear_spec_matches_the_default_path() -> None:
    args = (10_000.0, 60_000.0, 59_400.0)

    assert PositionCalculatorDomainService.calculate(
        *args, contract_spec=LINEAR_SPEC
    ) == PositionCalculatorDomainService.calculate(*args)


def test_float_division_short_of_a_whole_lot_still_counts_it() -> None:
    # 700 USD at risk over a 2-tick stop is exactly 28 contracts, which float
    # division yields as 27.999999999999996.
    risk = RiskConfig(risk_per_trade=0.00007, max_exposure_percent=1.0)
    calc = PositionCalculatorDomainService.calculate(
        10_000_000.0, 4500.0, 4499.5, risk, contract_spec=ES
    )

    assert calc.size == 28.0
