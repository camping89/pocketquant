"""BacktestResultAppService mark-to-market — read-only equity + persist downsampling.

Pins the invariants Bug #2's fix must preserve:
- ``mark_to_market`` never mutates realized accounting → total_return / cagr /
  max_drawdown / win_rate / profit_factor byte-identical with vs. without MTM.
- Sharpe/Sortino use the per-bar MTM curve when present.
- The persisted equity_curve is capped at 5000 points.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.backtest.engine.backtest_result_app_service import (
    _MAX_PERSISTED_EQUITY_POINTS,
    BacktestResultAppService,
)
from pocketquant.backtest.models.backtest_config import BacktestConfig
from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderSide, OrderStatus

_T0 = datetime(2024, 1, 5, 10, tzinfo=UTC)


def _oid(name: str) -> str:
    return str(uuid5(NAMESPACE_OID, name))


def _config() -> BacktestConfig:
    return BacktestConfig(
        strategy_code="s1",
        symbol="BTCUSDT:OKX",
        interval="1m",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 31),
        initial_capital=10_000.0,
        commission_bps=10.0,
    )


def _fill(side: OrderSide, qty: float, price: float, oid: str) -> OrderResult:
    return OrderResult(
        order_id=_oid(oid),
        broker_order_id="b" + oid,
        status=OrderStatus.FILLED,
        filled_quantity=qty,
        filled_price=price,
        side=side,
    )


@pytest.fixture(autouse=True)
def _reset_sim_time():
    yield
    clear_simulation_time()


async def _round_trip(with_mtm: bool) -> BacktestResultAppService:
    c = BacktestResultAppService(_config(), initial_capital=10_000.0, run_id=_oid("run"))
    set_simulation_time(_T0)
    await c.on_fill(_fill(OrderSide.BUY, 1.0, 100.0, "o1"))
    if with_mtm:
        # Wild swings — must not leak into realized accounting.
        c.mark_to_market(_T0, 10_500.0)
        c.mark_to_market(_T0 + timedelta(minutes=1), 9_800.0)
    set_simulation_time(_T0 + timedelta(hours=1))
    await c.on_fill(_fill(OrderSide.SELL, 1.0, 110.0, "o2"))
    if with_mtm:
        c.mark_to_market(_T0 + timedelta(hours=1), 10_009.79)
    return c


async def test_mark_to_market_does_not_change_realized_metrics() -> None:
    without = (await _round_trip(False)).finalize(
        _oid("run"), _T0, _T0 + timedelta(hours=2)
    ).run.metrics
    with_ = (await _round_trip(True)).finalize(
        _oid("run"), _T0, _T0 + timedelta(hours=2)
    ).run.metrics

    assert with_.total_return == without.total_return
    assert with_.cagr == without.cagr
    assert with_.max_drawdown == without.max_drawdown
    assert with_.win_rate == without.win_rate
    assert with_.profit_factor == without.profit_factor


async def test_mark_to_market_does_not_touch_current_equity() -> None:
    c = await _round_trip(True)
    # Realized equity after one +10 round trip minus commission, never the MTM values.
    assert c._current_equity == pytest.approx(10_009.79)


async def test_sharpe_uses_mtm_curve_when_present() -> None:
    without = (await _round_trip(False)).finalize(
        _oid("run"), _T0, _T0 + timedelta(hours=2)
    ).run.metrics
    with_ = (await _round_trip(True)).finalize(
        _oid("run"), _T0, _T0 + timedelta(hours=2)
    ).run.metrics
    # Different equity series → different Sharpe (MTM swings vs. realized-only).
    assert with_.sharpe_ratio != without.sharpe_ratio


async def test_persisted_equity_curve_capped() -> None:
    c = BacktestResultAppService(_config(), initial_capital=10_000.0, run_id=_oid("run"))
    base = 10_000.0
    # 20k MTM points — well over the 5000 cap.
    for i in range(20_000):
        c.mark_to_market(_T0 + timedelta(minutes=i), base + (i % 7))
    run = c.finalize(_oid("run"), _T0, _T0 + timedelta(days=14)).run
    assert len(run.equity_curve) <= _MAX_PERSISTED_EQUITY_POINTS


async def test_persisted_curve_hard_capped_even_with_many_trade_points() -> None:
    """Cap is a hard guarantee: even >5000 trade-carrying points get strided down."""
    c = BacktestResultAppService(_config(), initial_capital=10_000.0, run_id=_oid("run"))
    set_simulation_time(_T0)
    # 8000 round-trips → ~16000 trade-carrying equity points (over the cap).
    for i in range(8000):
        set_simulation_time(_T0 + timedelta(minutes=2 * i))
        await c.on_fill(_fill(OrderSide.BUY, 1.0, 100.0, f"b{i}"))
        set_simulation_time(_T0 + timedelta(minutes=2 * i + 1))
        await c.on_fill(_fill(OrderSide.SELL, 1.0, 101.0, f"s{i}"))
    run = c.finalize(_oid("run"), _T0, _T0 + timedelta(days=30)).run
    assert len(run.equity_curve) <= _MAX_PERSISTED_EQUITY_POINTS
