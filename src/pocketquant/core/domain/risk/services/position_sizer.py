"""Position sizing service - pure domain calculation."""

from pocketquant.core.domain.risk.value_objects import RiskConfig, RiskModel


class PositionSizer:
    """Pure domain service for calculating position sizes.

    No I/O, no external dependencies. Takes values, returns size.
    """

    @staticmethod
    def calculate_size(
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None,
        risk_config: RiskConfig,
    ) -> float:
        """Calculate position size based on risk model.

        Args:
            account_balance: Total account equity
            entry_price: Expected entry price
            stop_loss_price: Stop loss price (required for percent_risk)
            risk_config: Risk configuration

        Returns:
            Position size in base units
        """
        if account_balance <= 0:
            return 0.0
        if entry_price <= 0:
            return 0.0

        if risk_config.model == RiskModel.PERCENT_RISK:
            return PositionSizer._percent_risk_size(
                account_balance, entry_price, stop_loss_price, risk_config
            )
        elif risk_config.model == RiskModel.KELLY:
            return PositionSizer._kelly_size(account_balance, entry_price, risk_config)
        elif risk_config.model == RiskModel.FIXED:
            return PositionSizer._fixed_size(account_balance, entry_price, risk_config)
        else:
            return 0.0

    @staticmethod
    def _percent_risk_size(
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None,
        risk_config: RiskConfig,
    ) -> float:
        """Calculate size based on fixed percentage risk.

        Size = (Account * Risk%) / |Entry - StopLoss|
        """
        if stop_loss_price is None:
            # Without stop loss, use 1% of entry as default risk
            price_risk = entry_price * 0.01
        else:
            price_risk = abs(entry_price - stop_loss_price)

        if price_risk == 0:
            return 0.0

        risk_amount = account_balance * risk_config.risk_per_trade
        size = risk_amount / price_risk

        max_size = (account_balance * risk_config.max_exposure_percent) / entry_price
        return min(size, max_size)

    @staticmethod
    def _kelly_size(
        account_balance: float,
        entry_price: float,
        risk_config: RiskConfig,
    ) -> float:
        """Calculate size using Kelly criterion.

        Simplified: uses risk_per_trade as kelly fraction.
        Full Kelly would need win_rate and win/loss ratio.
        """
        # Half-Kelly for safety
        kelly_fraction = risk_config.risk_per_trade * 0.5
        size = (account_balance * kelly_fraction) / entry_price

        max_size = (account_balance * risk_config.max_exposure_percent) / entry_price
        return min(size, max_size)

    @staticmethod
    def _fixed_size(
        account_balance: float,
        entry_price: float,
        risk_config: RiskConfig,
    ) -> float:
        """Calculate fixed size per trade.

        Uses max_exposure_percent as the fixed allocation.
        """
        size = (account_balance * risk_config.max_exposure_percent) / entry_price
        return size

    @staticmethod
    def validate_size(
        size: float,
        entry_price: float,
        account_balance: float,
        risk_config: RiskConfig,
    ) -> tuple[bool, str]:
        """Validate that a position size is within risk limits.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if size <= 0:
            return False, "Position size must be positive"

        position_value = size * entry_price
        exposure = position_value / account_balance

        if exposure > risk_config.max_exposure_percent:
            return False, (
                f"Exposure {exposure:.1%} exceeds max {risk_config.max_exposure_percent:.1%}"
            )

        return True, ""
