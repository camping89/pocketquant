"""Risk check handler - validates signals against risk limits."""

import structlog

from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.concepts.risk import RiskConfig
from pocketquant.core.concepts.strategy import Direction, Signal
from pocketquant.core.infrastructure.brokers.models import AccountBalance

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
        config: RiskConfig,
    ) -> tuple[bool, str]:
        """Validate signal against risk rules.

        Args:
            signal: Trading signal to validate
            account: Current account balance
            position: Existing position for this strategy (if any)
            config: Risk configuration

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        # Check if we have enough balance
        if account.available_balance <= 0:
            return False, "Insufficient balance"

        # Check exit signals - always allowed
        if signal.direction == Direction.EXIT:
            if position is None or position.is_closed:
                return False, "No position to exit"
            return True, ""

        # Check FLAT signals - nothing to do
        if signal.direction == Direction.FLAT:
            return False, "Flat signal, no action"

        # Check max positions for new entries
        if position is None or position.is_closed:
            # This is a new position
            # Note: In a multi-strategy setup, we'd check total positions
            pass
        else:
            # Already have a position
            if position.side.value == signal.direction.value:
                # Adding to position - check if allowed
                pass
            else:
                # Reversing position - this is an exit + new entry
                pass

        # Check exposure limits
        exposure_check = self._check_exposure(account, position, config)
        if not exposure_check[0]:
            return exposure_check

        return True, ""

    def _check_exposure(
        self,
        account: AccountBalance,
        position: PositionAggregate | None,
        config: RiskConfig,
    ) -> tuple[bool, str]:
        """Check if current exposure is within limits."""
        if position is None or position.is_closed:
            return True, ""

        current_exposure = position.market_value / account.total_equity

        if current_exposure >= config.max_exposure_percent:
            return False, (
                f"Max exposure reached: {current_exposure:.1%} >= {config.max_exposure_percent:.1%}"
            )

        return True, ""

    def calculate_max_size(
        self,
        account: AccountBalance,
        entry_price: float,
        config: RiskConfig,
    ) -> float:
        """Calculate maximum position size allowed.

        Args:
            account: Account balance
            entry_price: Expected entry price
            config: Risk configuration

        Returns:
            Maximum position size in base units
        """
        if entry_price <= 0:
            return 0.0

        max_value = account.available_balance * config.max_exposure_percent
        return max_value / entry_price

    def get_risk_summary(
        self,
        account: AccountBalance,
        positions: list[PositionAggregate],
        config: RiskConfig,
    ) -> dict:
        """Get summary of current risk state.

        Args:
            account: Account balance
            positions: All open positions
            config: Risk configuration

        Returns:
            Risk summary dictionary
        """
        total_exposure = sum(p.market_value for p in positions if not p.is_closed)
        exposure_percent = total_exposure / account.total_equity if account.total_equity > 0 else 0

        return {
            "total_equity": account.total_equity,
            "available_balance": account.available_balance,
            "total_exposure": total_exposure,
            "exposure_percent": exposure_percent,
            "max_exposure_percent": config.max_exposure_percent,
            "position_count": len([p for p in positions if not p.is_closed]),
            "max_positions": config.max_positions,
            "risk_per_trade": config.risk_per_trade,
            "is_within_limits": (
                exposure_percent <= config.max_exposure_percent
                and len(positions) <= config.max_positions
            ),
        }
