from __future__ import annotations

from typing import TYPE_CHECKING

from pocketquant.core.domain.risk.position_calculation import PositionCalculation

if TYPE_CHECKING:
    from pocketquant.core.domain.risk.value_objects import RiskConfig
    from pocketquant.core.domain.trading import CommissionModel


class PositionCalculatorDomainService:
    RISK_PER_TRADE = 0.02  # phần vốn rủi ro mỗi lệnh, đo trên khoảng entry→SL
    MAX_EXPOSURE_PERCENT = 0.10  # trần notional theo phần vốn (cap gần như luôn thắng)
    DEFAULT_SL_RISK_PERCENT = 0.01  # price-risk dự phòng khi lệnh không có SL

    @staticmethod
    def calculate(
        account_balance: float,
        entry_price: float,
        stop_loss_price: float | None,
        risk_config: RiskConfig | None = None,
        commission_model: CommissionModel | None = None,
    ) -> PositionCalculation:
        cls = PositionCalculatorDomainService
        if account_balance <= 0 or entry_price <= 0:
            return PositionCalculation(0.0, 0.0, 0.0, 0.0)

        risk_per_trade = risk_config.risk_per_trade if risk_config else cls.RISK_PER_TRADE
        max_exposure = risk_config.max_exposure_percent if risk_config else cls.MAX_EXPOSURE_PERCENT

        if stop_loss_price is None:
            price_risk = entry_price * cls.DEFAULT_SL_RISK_PERCENT
        else:
            price_risk = abs(entry_price - stop_loss_price)
        if price_risk == 0:
            return PositionCalculation(0.0, 0.0, 0.0, 0.0)

        risk_amount = account_balance * risk_per_trade
        cap = (account_balance * max_exposure) / entry_price
        size = min(risk_amount / price_risk, cap)
        notional = size * entry_price
        est = commission_model.compute(entry_price, size) if commission_model else 0.0
        return PositionCalculation(
            size=size, notional=notional, risk_amount=risk_amount, est_entry_commission=est
        )
