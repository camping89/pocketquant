from pocketquant.core.common.constants import INTERVAL_SECONDS
from pocketquant.core.common.exceptions import DomainError, NotFoundError
from pocketquant.core.domain.strategy.services.triple_screen_strategy_service import (
    TripleScreenStrategyService,
)
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.strategy.value_objects import StrategyConfig

STRATEGY_REGISTRY: dict[str, type[IStrategyService]] = {
    "triple_screen": TripleScreenStrategyService,
}


def _invalid(message: str, error_code: str) -> DomainError:
    return DomainError(message, error_code=error_code, status_code=422)


# bool is a subclass of int, so isinstance alone would let True pass as a count.
def _type_matches(default: object, value: object) -> bool:
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, int | float)
    return isinstance(value, type(default))


def check_strategy_inputs(
    strategy_code: str, intervals: list[str], parameters: dict
) -> type[IStrategyService]:
    cls = STRATEGY_REGISTRY.get(strategy_code)
    if cls is None:
        raise NotFoundError(f"Strategy template '{strategy_code}' not found in registry.")

    # Never sorted: an unsorted list is a client error, and silently sorting would change
    # which interval is the entry.
    if not intervals:
        raise _invalid("intervals must not be empty", "INVALID_INTERVALS")
    unknown = [i for i in intervals if i not in INTERVAL_SECONDS]
    if unknown:
        raise _invalid(f"unknown intervals {unknown}", "INVALID_INTERVALS")
    seconds = [INTERVAL_SECONDS[i] for i in intervals]
    if any(lower >= higher for lower, higher in zip(seconds, seconds[1:], strict=False)):
        raise _invalid(f"intervals {intervals} must be strictly ascending", "INVALID_INTERVALS")
    if any(s % seconds[0] for s in seconds[1:]):
        raise _invalid(
            f"every interval in {intervals} must be a multiple of the entry interval",
            "INVALID_INTERVALS",
        )

    unknown_keys = sorted(set(parameters) - set(cls.DEFAULTS))
    if unknown_keys:
        raise _invalid(f"unknown parameters {unknown_keys}", "INVALID_PARAMETERS")
    # A wrong type would otherwise reach the trader, failing on every bar, or surface here
    # as a TypeError, which the api renders as a 500.
    for key, value in parameters.items():
        if not _type_matches(cls.DEFAULTS[key], value):
            raise _invalid(
                f"parameter {key!r} must be {type(cls.DEFAULTS[key]).__name__}",
                "INVALID_PARAMETERS",
            )
    try:
        cls(
            StrategyConfig(
                id="check",
                name=strategy_code,
                symbol="CHECK",
                intervals=list(intervals),
                parameters=dict(parameters),
            )
        )
    except (ValueError, TypeError) as exc:
        raise _invalid(str(exc), "INVALID_PARAMETERS") from None
    return cls


__all__ = ["STRATEGY_REGISTRY", "TripleScreenStrategyService", "check_strategy_inputs"]
