"""The symbol's contract spec reaches every live-path consumer.

A futures subscription must size in whole contracts, fill on a broker that
prices PnL with the ES multiplier, and persist a position mirror whose PnL
matches the broker's. Crypto keeps one shared linear paper broker.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.order import OrderAggregate, OrderFilledEvent, OrderSide
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.risk.value_objects import RiskConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.live.strategy_reconcile_app_service import StrategyReconcileAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

ES_SYMBOL = "ES1!:CME_MINI"
ES = ContractSpec(multiplier=50.0, tick_size=0.25, lot_step=1.0, commission_per_contract=2.5)
NOW = datetime(2026, 9, 23, 14, tzinfo=UTC)


class _FakeLookup:
    """Stands in for SymbolLookupHelper: only ES is seeded."""

    async def contract_spec(self, composite: str) -> ContractSpec:
        return ES if composite == ES_SYMBOL else LINEAR_SPEC


class _RecordingOrderService:
    def __init__(self) -> None:
        self.orders: list[OrderAggregate] = []

    async def submit(self, order: OrderAggregate, broker: object) -> object:
        self.orders.append(order)
        return await broker.submit_order(order)  # type: ignore[attr-defined]


class _NoPositions:
    def get(self, strategy_id: str) -> None:
        return None


class _AllowAll:
    def validate(self, *args: object) -> tuple[bool, str]:
        return True, ""


def _engine(order_service: _RecordingOrderService | None = None) -> StrategyAppService:
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=BrokerFactory(EventBus()),
        order_app_service=order_service or _RecordingOrderService(),  # type: ignore[arg-type]
        position_app_service=_NoPositions(),  # type: ignore[arg-type]
        risk_check_handler=_AllowAll(),  # type: ignore[arg-type]
        default_broker_config={"initial_balance": 1_000_000.0},
    )


def _config(sid: str, symbol: str, spec: ContractSpec, risk: RiskConfig | None = None):
    return StrategyConfig(
        id=sid,
        name=sid,
        symbol=symbol,
        interval="1m",
        risk=risk or RiskConfig(),
        contract_spec=spec,
    )


@pytest.mark.asyncio
async def test_futures_subscription_gets_its_own_spec_priced_broker() -> None:
    engine = _engine()
    await engine.load_strategy(_config("btc", "BTCUSDT:BINANCE", LINEAR_SPEC))
    await engine.load_strategy(_config("eth", "ETHUSDT:BINANCE", LINEAR_SPEC))
    await engine.load_strategy(_config("es", ES_SYMBOL, ES))

    btc, eth, es = (engine._brokers[s] for s in ("btc", "eth", "es"))
    assert btc is eth  # crypto still shares one paper account
    assert es is not btc
    assert isinstance(es, PaperBrokerAdapter)
    assert es._contract_spec == ES
    # Trade forwarding is wired once per broker, not once per subscription.
    for broker in (btc, es):
        assert broker._trade_callbacks.count(engine._forward_trade_to_bus) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_futures_signal_sizes_whole_contracts_and_realizes_in_usd() -> None:
    orders = _RecordingOrderService()
    engine = _engine(orders)
    # 850 USD at risk against a 10-point stop is 1.7 contracts.
    risk = RiskConfig(risk_per_trade=0.00085, max_exposure_percent=1.0)
    await engine.load_strategy(_config("es", ES_SYMBOL, ES, risk))
    strategy = engine._strategies["es"]
    broker = engine._brokers["es"]

    entry = Signal(
        symbol=ES_SYMBOL,
        direction=Direction.LONG,
        confidence=1.0,
        timestamp=NOW,
        subscription_id="es",
        stop_loss_price=4490.0,
    )
    await engine._process_signal(strategy, entry, 4500.0)

    assert orders.orders[0].quantity == 1.0
    exit_order = OrderAggregate.create(
        subscription_id="es",
        symbol=ES_SYMBOL,
        side=OrderSide.SELL,
        order_type=orders.orders[0].order_type,
        quantity=1.0,
        price=4510.0,
    )
    await broker.submit_order(exit_order)
    # 10 points x 50 x 1 contract, less 2.50 in and 2.50 out.
    balance = await broker.get_balance()
    assert balance.available_balance == pytest.approx(1_000_000.0 + 500.0 - 5.0)


@pytest.mark.asyncio
async def test_reconcile_loads_a_futures_subscription_with_its_spec() -> None:
    loaded: list[StrategyConfig] = []

    class _Engine:
        def get_strategy(self, sub_id: str) -> None:
            return None

        async def load_strategy(self, config: StrategyConfig, strategy_class=None) -> str:
            loaded.append(config)
            return config.id

    subs = [
        Subscription(
            id=generate_id(),
            strategy_code="hitnrun2",
            symbol=symbol,
            interval=Interval.MINUTE_5,
            created_at=NOW,
        )
        for symbol in (ES_SYMBOL, "BTCUSDT:BINANCE")
    ]
    recon = StrategyReconcileAppService(
        None,  # type: ignore[arg-type]
        _Engine(),  # type: ignore[arg-type]
        symbol_lookup=_FakeLookup(),  # type: ignore[arg-type]
    )
    await recon._ensure_instances(subs)

    assert {c.symbol: c.contract_spec for c in loaded} == {
        ES_SYMBOL: ES,
        "BTCUSDT:BINANCE": LINEAR_SPEC,
    }


class _MemoryPositionRepo:
    def __init__(self) -> None:
        self.saved: list[PositionAggregate] = []

    async def save(self, position: PositionAggregate) -> None:
        self.saved.append(position)


@pytest.mark.asyncio
async def test_position_mirror_reports_contract_scaled_pnl() -> None:
    bus = EventBus()
    repo = _MemoryPositionRepo()
    service = PositionAppService(bus, repo, _FakeLookup())  # type: ignore[arg-type]

    for side, price in ((OrderSide.BUY, 4500.00), (OrderSide.SELL, 4500.25)):
        await service._on_order_filled(
            OrderFilledEvent(
                order_id=str(generate_id()),
                subscription_id="es",
                symbol=ES_SYMBOL,
                side=side,
                filled_quantity=2.0,
                filled_price=price,
            )
        )

    closed = repo.saved[-1]
    assert closed.is_closed
    assert closed.multiplier == 50.0
    assert closed.realized_pnl == pytest.approx(25.0)
    assert PositionAggregate.from_mongo(closed.to_mongo()).multiplier == 50.0


@pytest.mark.asyncio
async def test_unloading_the_last_subscription_retires_its_paper_account() -> None:
    engine = _engine()
    await engine.load_strategy(_config("btc", "BTCUSDT:BINANCE", LINEAR_SPEC))
    first = engine._brokers["btc"]
    await engine.unload_strategy("btc")

    await engine.load_strategy(_config("eth", "ETHUSDT:BINANCE", LINEAR_SPEC))

    assert engine._brokers["eth"] is not first
