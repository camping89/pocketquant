from __future__ import annotations

import pytest

from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import DomainError, NotFoundError
from pocketquant.core.domain.strategy.services import check_strategy_inputs
from tests.strategy_doubles import ScriptedStrategy

pytestmark = pytest.mark.usefixtures("probe_registry")


def _assert_invalid(code: str, intervals: list[str], parameters: dict, error_code: str) -> None:
    with pytest.raises(DomainError) as exc_info:
        check_strategy_inputs(code, intervals, parameters)
    assert exc_info.value.error_code == error_code
    assert exc_info.value.status_code == 422


def test_an_unknown_code_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        check_strategy_inputs("nope", ["15m"], {})


def test_an_empty_list_is_invalid() -> None:
    _assert_invalid("probe", [], {}, "INVALID_INTERVALS")


def test_an_unsorted_list_is_invalid() -> None:
    _assert_invalid("probe", ["1h", "15m"], {}, "INVALID_INTERVALS")


def test_a_duplicate_interval_is_invalid() -> None:
    _assert_invalid("probe", ["15m", "15m"], {}, "INVALID_INTERVALS")


def test_an_unknown_interval_is_invalid() -> None:
    _assert_invalid("probe", ["15m", "2h"], {}, "INVALID_INTERVALS")


def test_a_higher_interval_must_be_a_multiple_of_the_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(INTERVAL_SECONDS, "1h", 3500)
    _assert_invalid("probe", ["15m", "1h"], {}, "INVALID_INTERVALS")


def test_an_unknown_parameter_is_invalid() -> None:
    _assert_invalid("probe", ["15m"], {"x": 1}, "INVALID_PARAMETERS")


def test_a_value_the_strategy_refuses_is_invalid() -> None:
    _assert_invalid("probe", ["15m"], {"min_bars": -1}, "INVALID_PARAMETERS")


@pytest.mark.parametrize("parameters", [{"min_bars": "3"}, {"min_bars": True}, {"min_bars": 2.5}])
def test_a_value_of_the_wrong_type_is_invalid(parameters: dict) -> None:
    _assert_invalid("probe", ["15m"], parameters, "INVALID_PARAMETERS")


def test_a_float_default_takes_an_int_but_not_a_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ScriptedStrategy, "DEFAULTS", {"min_bars": 0, "ratio": 1.0})
    assert check_strategy_inputs("probe", ["15m"], {"ratio": 2}) is ScriptedStrategy
    _assert_invalid("probe", ["15m"], {"ratio": True}, "INVALID_PARAMETERS")


def test_valid_inputs_return_the_class() -> None:
    assert check_strategy_inputs("probe", ["15m", "1h", "4h"], {"min_bars": 3}) is ScriptedStrategy
