"""OkxOrderMapper.to_order_result — fee → commission (abs, cost ≥ 0)."""

from pocketquant.core.infra.brokers.okx.websocket.okx_order_mapper import OkxOrderMapper


def _data(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "state": "filled",
        "accFillSz": "10",
        "avgPx": "100",
        "sCode": "0",
    }
    base.update(over)
    return base


def test_negative_fee_becomes_positive_cost() -> None:
    assert OkxOrderMapper.to_order_result(_data(fee="-0.42")).commission == 0.42


def test_positive_rebate_fee_kept_as_cost() -> None:
    # Maker rebate (positive) is abs()'d to a cost — accepted simplification for R3.
    assert OkxOrderMapper.to_order_result(_data(fee="0.05")).commission == 0.05


def test_missing_fee_defaults_zero() -> None:
    assert OkxOrderMapper.to_order_result(_data()).commission == 0.0


def test_empty_fee_does_not_raise() -> None:
    assert OkxOrderMapper.to_order_result(_data(fee="")).commission == 0.0
