import structlog

from pocketquant.core.domain.brokers.value_objects import AccountBalance
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.risk import PositionCalculatorDomainService, RiskConfig
from pocketquant.core.domain.strategy import Direction, Signal

logger = structlog.get_logger(__name__)


class RiskCheckHandler:
    """Validates an entry signal against the balance and the exposure cap."""

    def validate(
        self,
        signal: Signal,
        account: AccountBalance,
        position: PositionAggregate | None,
        config: RiskConfig | None = None,
    ) -> tuple[bool, str]:
        """Return (is_valid, rejection_reason).

        Only LONG and SHORT open an order: the order path maps every other
        direction to SELL, so EXIT and FLAT are rejected here.
        """
        if account.available_balance <= 0:
            return False, "Insufficient balance"

        if signal.direction not in (Direction.LONG, Direction.SHORT):
            return False, f"Unsupported signal direction: {signal.direction.value}"

        if position is None or position.is_closed:
            return True, ""

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
