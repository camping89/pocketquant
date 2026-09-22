"""The backtest report annualizes on the symbol's calendar, not on the interval.

The interval table answers for a market that never closes. A CME 1h series has
about 5848 bars a year, not 8760, and Sharpe scales by the square root of that,
so reading the wrong source overstates a futures Sharpe by roughly 22%.

Every other backtest test runs on crypto, where the two sources agree exactly —
which is why the wrong source would otherwise go unnoticed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.core.domain.backtest import BacktestConfig
from pocketquant.core.domain.brokers.value_objects import AccountBalance
from pocketquant.core.domain.market_data.continuous_24x7_calendar import Continuous24x7Calendar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.calendars.cme_globex_calendar_adapter import CmeGlobexCalendarAdapter
from pocketquant.engine.backtest.backtest_report_app_service import BacktestReportAppService

_T0 = datetime(2026, 6, 10, 14, 0, tzinfo=UTC)


def _config(interval: str) -> BacktestConfig:
    return BacktestConfig(
        strategy_code="s1",
        symbol="ES1!:CME_MINI",
        interval=interval,
        start_date=datetime(2026, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 6, 30, tzinfo=UTC),
        initial_capital=10_000.0,
    )


async def _periods_passed_to_metrics(calendar, interval: str) -> float | None:
    broker = AsyncMock()
    broker.get_balance = AsyncMock(
        return_value=AccountBalance(
            total_equity=10_000.0,
            available_balance=10_000.0,
            currency="USD",
            unrealized_pnl=0.0,
        )
    )
    collector = BacktestReportAppService(
        _config(interval),
        initial_capital=10_000.0,
        broker=broker,
        calendar=calendar,
    )

    with patch(
        "pocketquant.engine.backtest.backtest_report_app_service"
        ".PerformanceCalculatorDomainService.build"
    ) as build:
        await collector.finalize(str(uuid5(NAMESPACE_OID, "run-1")), _T0, _T0)

    return build.call_args.kwargs["periods_per_year"]


@pytest.mark.asyncio
async def test_a_session_symbol_annualizes_on_its_sessions() -> None:
    periods = await _periods_passed_to_metrics(CmeGlobexCalendarAdapter(), "1h")

    assert periods == 5_848.0
    # Emphatically not the 24/7 answer for the same interval.
    assert periods != Interval.HOUR_1.periods_per_year


@pytest.mark.asyncio
async def test_a_continuous_symbol_keeps_the_interval_answer() -> None:
    periods = await _periods_passed_to_metrics(Continuous24x7Calendar(), "1h")

    assert periods == Interval.HOUR_1.periods_per_year == 8_760


@pytest.mark.asyncio
async def test_an_unknown_interval_still_skips_annualization() -> None:
    periods = await _periods_passed_to_metrics(Continuous24x7Calendar(), "3m")

    assert periods is None
