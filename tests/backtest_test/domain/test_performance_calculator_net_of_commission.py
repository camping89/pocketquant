# Profit factor and win rate must share the balance's basis, which pays commission. A gross
# basis once showed PF 1.14 on a run that lost 3% of its capital.

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from pocketquant.core.domain.trading import EquityPoint, PerformanceCalculatorDomainService, Trade

T0 = datetime(2026, 1, 5, tzinfo=UTC)
CAPITAL = 1_000.0


def _trade(pnl: float, commission: float, hour: int) -> Trade:
    entry = T0 + timedelta(hours=hour)
    return Trade(
        trade_id=uuid4(),
        run_id="r1",
        strategy_code="s1",
        symbol="XAUUSD:EXNESS",
        direction="LONG",
        entry_order_id=None,
        entry_price=100.0,
        entry_time=entry,
        quantity=1.0,
        exit_order_id=None,
        exit_price=100.0 + pnl,
        exit_time=entry + timedelta(minutes=30),
        sl_price=None,
        tp_price=None,
        pnl=pnl,
        commission=commission,
        duration_seconds=1800.0,
    )


def test_profit_factor_and_win_rate_are_net_of_commission() -> None:
    # Gross: wins 10 + 0.5, loss 9 -> PF 1.17. Net: wins 9, losses 1 + 10.5 -> PF 0.78.
    trades = [_trade(10.0, 1.0, 0), _trade(0.5, 1.5, 1), _trade(-9.0, 1.5, 2)]
    final = CAPITAL + sum(t.pnl - t.commission for t in trades)
    metrics = PerformanceCalculatorDomainService.build(
        closed_trades=trades,
        equity_curve=[EquityPoint(T0, CAPITAL, 0.0), EquityPoint(T0, final, 0.0)],
        initial_capital=CAPITAL,
        current_equity=final,
        total_commission=4.0,
        start_date=T0,
        end_date=T0 + timedelta(days=1),
        periods_per_year=None,
    )

    assert metrics.total_return < 0
    assert metrics.profit_factor == pytest.approx(9.0 / 11.5)
    assert metrics.winning_trades == 1
    assert metrics.losing_trades == 2
    assert metrics.avg_win == pytest.approx(9.0)
    assert metrics.avg_loss == pytest.approx(-11.5 / 2)
