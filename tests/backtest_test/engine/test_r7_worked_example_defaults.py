"""R7 worked-example verify — design §6 on the real shared sim engine.

Drives ``PaperBrokerAdapter`` directly (same engine backing backtest + paper) with
the R7 defaults: initial_balance and currency come from the adapter defaults
(10 000 / USD) so the test also pins those; commission bps=4 and slippage 0.001 are
the §6 scenario values. Asserts the exact §6 arithmetic plus the structural
invariants (per-fill commission formula, net = gross − Σ fee, balance identity).
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.time.simulation import clear_simulation_time
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderSide, OrderType
from pocketquant.core.domain.position.events import TradeClosedEvent
from pocketquant.core.domain.trading import PercentageCommissionModel
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter

SYMBOL = "BTC:BIN"
QTY = 10.0
COMMISSION_BPS = 4.0  # R7 default
COMMISSION_FRACTION = COMMISSION_BPS / 10_000  # 0.0004


@pytest.fixture(autouse=True)
def reset_sim() -> Generator[None]:
    clear_simulation_time()
    yield
    clear_simulation_time()


@pytest.fixture
async def broker() -> PaperBrokerAdapter:
    # initial_balance + currency omitted → exercise the R7 adapter defaults (10 000 / USD).
    b = PaperBrokerAdapter(
        slippage_percent=0.001,
        fill_delay_ms=0,
        event_bus=EventBus(),
        commission_model=PercentageCommissionModel(bps=COMMISSION_BPS),
    )
    await b.connect()
    return b


async def _market(broker: PaperBrokerAdapter, side: OrderSide) -> OrderResult:
    order = OrderAggregate.create(
        subscription_id="s",
        symbol=SYMBOL,
        side=side,
        order_type=OrderType.MARKET,
        quantity=QTY,
    )
    return await broker.submit_order(order)


@pytest.mark.asyncio
async def test_worked_example_defaults_match_design_section_6(broker: PaperBrokerAdapter) -> None:
    trades: list[TradeClosedEvent] = []
    await broker.subscribe_trades(lambda t: trades.append(t))

    broker.set_current_price(SYMBOL, 100.0)
    entry = await _market(broker, OrderSide.BUY)

    # entry-fee-only debit under the futures model (no notional cash move on open).
    after_entry = await broker.get_balance()

    broker.set_current_price(SYMBOL, 104.0)
    exit_ = await _market(broker, OrderSide.SELL)
    final = await broker.get_balance()

    assert entry.filled_price is not None
    assert exit_.filled_price is not None

    # --- exact §6 arithmetic (abs tol 1e-2) ---
    assert entry.filled_price == pytest.approx(100.10, abs=1e-2)
    assert entry.commission == pytest.approx(0.4004, abs=1e-2)
    assert exit_.filled_price == pytest.approx(103.896, abs=1e-2)
    assert exit_.commission == pytest.approx(0.415584, abs=1e-2)

    assert len(trades) == 1
    gross_pnl = trades[0].pnl
    assert gross_pnl == pytest.approx(37.96, abs=1e-2)

    assert final.available_balance == pytest.approx(10037.144, abs=1e-2)
    assert final.total_equity == pytest.approx(10037.144, abs=1e-2)
    assert final.currency == "USD"

    # --- structural invariants (independent of the pinned numbers) ---
    assert entry.commission == pytest.approx(entry.filled_price * QTY * COMMISSION_FRACTION)
    assert exit_.commission == pytest.approx(exit_.filled_price * QTY * COMMISSION_FRACTION)

    after_entry_available = after_entry.available_balance
    assert after_entry_available == pytest.approx(10_000.0 - entry.commission, abs=1e-9)

    total_commission = entry.commission + exit_.commission
    net_pnl = gross_pnl - total_commission
    assert final.available_balance == pytest.approx(10_000.0 + net_pnl, abs=1e-9)
    # TradeClosedEvent bundles entry+exit commission for the closed chunk.
    assert trades[0].commission == pytest.approx(total_commission, abs=1e-9)
