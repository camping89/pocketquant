"""PercentageCommissionModel — cost is |price*qty|*bps/10000, always ≥ 0."""

import pytest

from pocketquant.core.domain.trading import PercentageCommissionModel


def test_percentage_commission_bps() -> None:
    assert PercentageCommissionModel(bps=4).compute(100.10, 10) == pytest.approx(0.40040)


def test_zero_bps_is_seam() -> None:
    assert PercentageCommissionModel(bps=0).compute(123.45, 67) == 0.0


@pytest.mark.parametrize(
    ("price", "qty"),
    [(-100.0, 10.0), (100.0, -10.0), (-100.0, -10.0)],
)
def test_negative_inputs_yield_nonnegative_cost(price: float, qty: float) -> None:
    assert PercentageCommissionModel(bps=4).compute(price, qty) == pytest.approx(0.4)
