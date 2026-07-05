import structlog

from pocketquant.core.domain.brokers.value_objects import AccountBalance
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.risk import PositionCalculatorDomainService, RiskConfig
from pocketquant.core.domain.strategy import Direction, Signal

logger = structlog.get_logger(__name__)


class RiskCheckHandler:
    """Validates trading signals against risk management rules.

    Checks:
    - Max positions limit
    - Max exposure percent
    - Account balance requirements
    """

    def validate(
        self,
        signal: Signal,
        account: AccountBalance,
        position: PositionAggregate | None,
        config: RiskConfig | None = None,
    ) -> tuple[bool, str]:
        """Validate signal against risk rules.

        Args:
            signal: Trading signal to validate
            account: Current account balance
            position: Existing position for this strategy (if any)
            config: Risk configuration (None falls back to default consts)

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        if account.available_balance <= 0:
            return False, "Insufficient balance"

        if signal.direction == Direction.EXIT:
            if position is None or position.is_closed:
                return False, "No position to exit"
            return True, ""

        if signal.direction == Direction.FLAT:
            return False, "Flat signal, no action"

        if position is None or position.is_closed:
            pass
        else:
            if position.side.value == signal.direction.value:
                pass
            else:
                pass

        exposure_check = self._check_exposure(account, position, config)
        if not exposure_check[0]:
            return exposure_check

        return True, ""

    def _check_exposure(
        self,
        account: AccountBalance,
        position: PositionAggregate | None,
        config: RiskConfig | None = None,
    ) -> tuple[bool, str]:
        if position is None or position.is_closed:
            return True, ""

        max_exposure = (
            config.max_exposure_percent
            if config
            else PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT
        )
        current_exposure = position.market_value / account.total_equity

        if current_exposure >= max_exposure:
            return False, (f"Max exposure reached: {current_exposure:.1%} >= {max_exposure:.1%}")

        return True, ""

    def calculate_max_size(
        self,
        account: AccountBalance,
        entry_price: float,
        config: RiskConfig | None = None,
    ) -> float:
        """Calculate maximum position size allowed.

        Args:
            account: Account balance
            entry_price: Expected entry price
            config: Risk configuration (None falls back to default consts)

        Returns:
            Maximum position size in base units
        """
        if entry_price <= 0:
            return 0.0

        max_exposure = (
            config.max_exposure_percent
            if config
            else PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT
        )
        max_value = account.available_balance * max_exposure
        return max_value / entry_price

    def get_risk_summary(
        self,
        account: AccountBalance,
        positions: list[PositionAggregate],
        config: RiskConfig | None = None,
    ) -> dict:
        """Get summary of current risk state.

        Args:
            account: Account balance
            positions: All open positions
            config: Risk configuration (None falls back to default consts)

        Returns:
            Risk summary dictionary
        """
        max_exposure = (
            config.max_exposure_percent
            if config
            else PositionCalculatorDomainService.MAX_EXPOSURE_PERCENT
        )
        risk_per_trade = (
            config.risk_per_trade if config else PositionCalculatorDomainService.RISK_PER_TRADE
        )
        max_positions = config.max_positions if config else 3

        total_exposure = sum(p.market_value for p in positions if not p.is_closed)
        exposure_percent = total_exposure / account.total_equity if account.total_equity > 0 else 0

        return {
            "total_equity": account.total_equity,
            "available_balance": account.available_balance,
            "total_exposure": total_exposure,
            "exposure_percent": exposure_percent,
            "max_exposure_percent": max_exposure,
            "position_count": len([p for p in positions if not p.is_closed]),
            "max_positions": max_positions,
            "risk_per_trade": risk_per_trade,
            "is_within_limits": (
                exposure_percent <= max_exposure and len(positions) <= max_positions
            ),
        }
