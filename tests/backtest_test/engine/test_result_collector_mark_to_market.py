"""BacktestReportAppService mark-to-market — read-only equity + persist downsampling.

Pins the invariants Bug #2's fix must preserve:
- ``mark_to_market`` never mutates realized accounting → total_return / cagr /
  max_drawdown / win_rate / profit_factor byte-identical with vs. without MTM.
- Sharpe/Sortino use the per-bar MTM curve when present.
- The persisted equity_curve is capped at 5000 points.

Post-R5 the realized equity curve is broker-sourced: ``on_trade`` and
``finalize`` read ``broker.get_balance().available_balance``. A ``_FakeBroker``
mirrors the broker's realized ledger (initial − Σcommission + Σpnl) so the
collector sees the same balance the real PaperBrokerAdapter would.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_OID, uuid5

import pytest

from pocketquant.core.common.time.simulation import clear_simulation_time, set_simulation_time
from pocketquant.core.domain.backtest import BacktestConfig
from pocketquant.core.domain.brokers.value_objects import AccountBalance, OrderResult
from pocketquant.core.domain.order import OrderSide, OrderStatus
from pocketquant.core.domain.position import TradeClosedEvent
from pocketquant.core.domain.trading import PercentageCommissionModel
from pocketquant.engine.backtest.backtest_report_app_service import (
    _MAX_PERSISTED_EQUITY_POINTS,
    BacktestReportAppService,
)

_T0 = datetime(2024, 1, 5, 10, tzinfo=UTC)

# Collector reads commission from OrderResult (broker single-source).
_COMMISSION = PercentageCommissionModel(bps=10.0)


class _FakeBroker:
    """Minimal IBrokerPort stand-in — only ``get_balance()`` is exercised.

    Tests script ``available_balance`` to mirror the broker's realized ledger
    (initial − Σcommission + Σpnl) as fills/trades are fed to the collector, and
    ``total_equity`` independently to prove MTM swings never leak into the
    realized curve.
    """

    def __init__(self, balance: float) -> None:
        self.available_balance = balance
        self.total_equity = balance

    async def get_balance(self) -> AccountBalance:
        return AccountBalance(
            total_equity=self.total_equity,
            available_balance=self.available_balance,
            currency="USD",
            unrealized_pnl=self.total_equity - self.available_balance,
        )


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
        commission=_COMMISSION.compute(price, qty),
    )


def _long_trade(
    entry_oid: str,
    exit_oid: str,
    *,
    entry_price: float,
    exit_price: float,
    qty: float,
    entry_time: datetime,
    exit_time: datetime,
) -> TradeClosedEvent:
    """A LONG round-trip closure as the broker would emit it (avg-cost)."""
    return TradeClosedEvent(
        symbol="BTCUSDT:OKX",
        direction="LONG",
        entry_order_id=_oid(entry_oid),
        entry_price=entry_price,
        entry_time=entry_time,
        quantity=qty,
        exit_order_id=_oid(exit_oid),
        exit_price=exit_price,
        exit_time=exit_time,
        pnl=(exit_price - entry_price) * qty,
        commission=_COMMISSION.compute(entry_price, qty) + _COMMISSION.compute(exit_price, qty),
    )


@pytest.fixture(autouse=True)
def _reset_sim_time():
    yield
    clear_simulation_time()


async def _round_trip(with_mtm: bool) -> BacktestReportAppService:
    broker = _FakeBroker(10_000.0)
    c = BacktestReportAppService(
        _config(), initial_capital=10_000.0, broker=broker, run_id=_oid("run")  # type: ignore[arg-type]
    )
    set_simulation_time(_T0)
    await c.on_fill(_fill(OrderSide.BUY, 1.0, 100.0, "o1"))
    if with_mtm:
        # Wild swings — must not leak into the realized curve.
        c.mark_to_market(_T0, 10_500.0)
        c.mark_to_market(_T0 + timedelta(minutes=1), 9_800.0)
    set_simulation_time(_T0 + timedelta(hours=1))
    await c.on_fill(_fill(OrderSide.SELL, 1.0, 110.0, "o2"))
    # Broker debited both commissions + credited pnl under its lock BEFORE
    # dispatching the closure (10_000 − 0.1 − 0.11 + 10). Mirror it here.
    broker.available_balance = 10_009.79
    await c.on_trade(
        _long_trade(
            "o1",
            "o2",
            entry_price=100.0,
            exit_price=110.0,
            qty=1.0,
            entry_time=_T0,
            exit_time=_T0 + timedelta(hours=1),
        )
    )
    if with_mtm:
        c.mark_to_market(_T0 + timedelta(hours=1), 10_009.79)
    return c


async def test_mark_to_market_does_not_change_realized_metrics() -> None:
    c_without = await _round_trip(False)
    without = (
        await c_without.finalize(_oid("run"), _T0, _T0 + timedelta(hours=2))
    ).run.metrics
    c_with = await _round_trip(True)
    with_ = (await c_with.finalize(_oid("run"), _T0, _T0 + timedelta(hours=2))).run.metrics

    assert with_.total_return == without.total_return
    assert with_.cagr == without.cagr
    assert with_.max_drawdown == without.max_drawdown
    assert with_.win_rate == without.win_rate
    assert with_.profit_factor == without.profit_factor


async def test_mark_to_market_does_not_touch_realized_equity() -> None:
    c = await _round_trip(True)
    # Realized curve is broker-sourced (available_balance), never the MTM swings.
    assert c._equity_curve[-1].equity == pytest.approx(10_009.79)
    # MTM values live only on the separate mtm curve.
    assert [p.equity for p in c._mtm_curve] == [10_500.0, 9_800.0, 10_009.79]


async def test_sharpe_uses_mtm_curve_when_present() -> None:
    c_without = await _round_trip(False)
    without = (
        await c_without.finalize(_oid("run"), _T0, _T0 + timedelta(hours=2))
    ).run.metrics
    c_with = await _round_trip(True)
    with_ = (await c_with.finalize(_oid("run"), _T0, _T0 + timedelta(hours=2))).run.metrics
    # Different equity series → different Sharpe (MTM swings vs. realized-only).
    assert with_.sharpe_ratio != without.sharpe_ratio


async def test_persisted_equity_curve_capped() -> None:
    broker = _FakeBroker(10_000.0)
    c = BacktestReportAppService(
        _config(), initial_capital=10_000.0, broker=broker, run_id=_oid("run")  # type: ignore[arg-type]
    )
    base = 10_000.0
    # 20k MTM points — well over the 5000 cap.
    for i in range(20_000):
        c.mark_to_market(_T0 + timedelta(minutes=i), base + (i % 7))
    run = (await c.finalize(_oid("run"), _T0, _T0 + timedelta(days=14))).run
    assert len(run.equity_curve) <= _MAX_PERSISTED_EQUITY_POINTS


async def test_persisted_curve_hard_capped_even_with_many_trade_points() -> None:
    """Cap is a hard guarantee: even >5000 trade-carrying points get strided down."""
    broker = _FakeBroker(10_000.0)
    c = BacktestReportAppService(
        _config(), initial_capital=10_000.0, broker=broker, run_id=_oid("run")  # type: ignore[arg-type]
    )
    set_simulation_time(_T0)
    # 8000 round-trips → 8000 trade-carrying equity points (over the cap).
    for i in range(8000):
        entry_time = _T0 + timedelta(minutes=2 * i)
        exit_time = _T0 + timedelta(minutes=2 * i + 1)
        set_simulation_time(entry_time)
        await c.on_fill(_fill(OrderSide.BUY, 1.0, 100.0, f"b{i}"))
        set_simulation_time(exit_time)
        await c.on_fill(_fill(OrderSide.SELL, 1.0, 101.0, f"s{i}"))
        broker.available_balance += 0.8  # each round-trip nudges the realized ledger
        await c.on_trade(
            _long_trade(
                f"b{i}",
                f"s{i}",
                entry_price=100.0,
                exit_price=101.0,
                qty=1.0,
                entry_time=entry_time,
                exit_time=exit_time,
            )
        )
    run = (await c.finalize(_oid("run"), _T0, _T0 + timedelta(days=30))).run
    assert len(run.equity_curve) <= _MAX_PERSISTED_EQUITY_POINTS
