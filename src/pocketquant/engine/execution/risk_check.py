import structlog

from pocketquant.core.domain.brokers.value_objects import AccountBalance
from pocketquant.core.domain.position import PositionAggregate, PositionSide
from pocketquant.core.domain.risk import PositionCalculatorDomainService, RiskConfig
from pocketquant.core.domain.strategy import Direction, Signal

logger = structlog.get_logger(__name__)


class RiskCheckHandler:
    # EXIT passes only with an open position; the engine closes it through the broker,
    # never through an order. FLAT and other non-entry directions are rejected because the
    # order path maps them to SELL. A subscription holds one position: an opposite entry
    # against it is rejected, and so is a stop entry, which the paper broker would refuse at
    # every touch. A same-side market entry adds to it, within the exposure cap.
    def validate(
        self,
        signal: Signal,
        account: AccountBalance,
        position: PositionAggregate | None,
        config: RiskConfig | None = None,
    ) -> tuple[bool, str]:
        if signal.direction is Direction.EXIT:
            if position is None or position.is_closed:
                return False, "no open position"
            return True, ""

        if account.available_balance <= 0:
            return False, "Insufficient balance"

        if signal.direction not in (Direction.LONG, Direction.SHORT):
            return False, f"Unsupported signal direction: {signal.direction.value}"

        if position is None or position.is_closed:
            return True, ""

        if (signal.direction == Direction.LONG) != (position.side == PositionSide.LONG):
            return False, "opposite position open"

        if signal.entry_type == "stop":
            return False, "position open"

        if account.total_equity <= 0:
            return False, "No account equity"

        max_exposure = (
            config.max_exposure_percent
            if config
            else PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT
        )
        current_exposure = position.market_value / account.total_equity
        if current_exposure >= max_exposure:
            return False, f"Max exposure reached: {current_exposure:.1%} >= {max_exposure:.1%}"

        return True, ""
