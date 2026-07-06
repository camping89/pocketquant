"""LiveMetricsQueryService — trade-derived metrics per subscription (M1).

Covers: aggregate stats from seeded trades, %-return omission, empty-subscription
no-crash, and the drawdown-stays-finite regression (a zero baseline made
``max_drawdown`` divide by a zero running peak → garbage).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.trading import Trade
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.trade_repository import TradeRepository
from pocketquant.engine.live.live_metrics_query_service import LiveMetricsQueryService

pytestmark = pytest.mark.integration

BASELINE = 10_000.0
T0 = datetime(2026, 1, 5, 10, 0, 0)


@pytest.fixture
async def db(settings):
    database = Database()
    await database.connect(settings)
    for coll in ("subscriptions", "trades"):
        await database.get_collection(coll).drop()
    yield database
    await database.disconnect()


def _trade(run_id: str, *, pnl: float, hour: int = 0) -> Trade:
    entry = T0 + timedelta(hours=hour)
    return Trade(
        trade_id=generate_id(),
        run_id=run_id,
        strategy_code="s1",
        symbol="BTC:BIN",
        direction="LONG",
        entry_order_id="o-entry",
        entry_price=100.0,
        entry_time=entry,
        quantity=1.0,
        exit_order_id="o-exit",
        exit_price=100.0 + pnl,
        exit_time=entry + timedelta(minutes=30),
        sl_price=None,
        tp_price=None,
        pnl=pnl,
        commission=0.2,
        duration_seconds=1800.0,
    )


def _service(db: Database) -> LiveMetricsQueryService:
    return LiveMetricsQueryService(TradeRepository(db), baseline=BASELINE)


@pytest.mark.asyncio
async def test_metrics_from_trades(db: Database) -> None:
    sub_id = str(generate_id())
    await TradeRepository(db).save_many(
        [
            _trade(sub_id, pnl=30.0, hour=0),
            _trade(sub_id, pnl=-10.0, hour=1),
            _trade(sub_id, pnl=20.0, hour=2),
        ]
    )
    m = await _service(db).get_metrics(sub_id)

    assert m["total_trades"] == 3
    assert m["winning_trades"] == 2
    assert m["losing_trades"] == 1
    assert m["win_rate"] == pytest.approx(2 / 3)
    assert m["profit_factor"] == pytest.approx(5.0)  # gross_profit 50 / gross_loss 10
    assert m["total_commission"] == pytest.approx(0.6)
    # %-of-capital returns omitted — live subs share one account.
    assert m["total_return"] is None
    assert m["cagr"] is None
    # M1: trade-keyed curve is not bar-annualizable → Sharpe/Sortino report 0.0.
    assert m["sharpe_ratio"] == 0.0
    assert m["sortino_ratio"] == 0.0


@pytest.mark.asyncio
async def test_empty_subscription_returns_zeroed_metrics(db: Database) -> None:
    m = await _service(db).get_metrics(str(generate_id()))
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0.0
    assert m["total_return"] is None


@pytest.mark.asyncio
async def test_drawdown_finite_when_first_trade_loses(db: Database) -> None:
    sub_id = str(generate_id())
    await TradeRepository(db).save_many(
        [_trade(sub_id, pnl=-500.0, hour=0), _trade(sub_id, pnl=100.0, hour=1)]
    )
    m = await _service(db).get_metrics(sub_id)
    # Positive baseline keeps the relative drawdown finite and in [-1, 0].
    assert -1.0 <= m["max_drawdown"] <= 0.0
