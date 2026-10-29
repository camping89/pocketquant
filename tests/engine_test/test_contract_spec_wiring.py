# A lot-sized CFD subscription must size on its lot grid, fill on a broker that prices PnL
# with the XAUUSD contract size, and persist a position mirror whose PnL matches the
# broker's. Crypto keeps one shared linear paper broker.

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.order import OrderAggregate, OrderFilledEvent, OrderSide
from pocketquant.core.domain.position import PositionAggregate
from pocketquant.core.domain.risk.value_objects import RiskConfig
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy.value_objects import Direction, Signal, StrategyConfig
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.symbol import LINEAR_SPEC, ContractSpec
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.engine.backtest.backtest_sandbox_app_service import (
    Continuous24x7CalendarFactory,
    NoClosedTrades,
    NoStoredBars,
)
from pocketquant.engine.execution.position_app_service import PositionAppService
from pocketquant.engine.live.strategy_reconcile_app_service import StrategyReconcileAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

XAUUSD_SYMBOL = "XAUUSD:EXNESS"
# 100 oz per lot in 0.01-lot steps; the per-lot fee exercises the per-contract model.
XAUUSD = ContractSpec(multiplier=100.0, tick_size=0.001, lot_step=0.01, commission_per_contract=2.5)
NOW = datetime(2026, 9, 23, 14, tzinfo=UTC)


# Only XAUUSD is seeded.
class _FakeLookup:
    async def contract_spec(self, composite: str) -> ContractSpec:
        return XAUUSD if composite == XAUUSD_SYMBOL else LINEAR_SPEC


class _RecordingOrderService:
    def __init__(self) -> None:
        self.orders: list[OrderAggregate] = []

    async def submit(
        self, order: OrderAggregate, broker: object, *, deadline: object = None
    ) -> object:
        self.orders.append(order)
        return await broker.submit_order(order)  # type: ignore[attr-defined]


class _NoPositions:
    def get(self, strategy_id: str) -> None:
        return None

    async def drop(self, strategy_id: str) -> None:
        return None


class _AllowAll:
    def validate(self, *args: object) -> tuple[bool, str]:
        return True, ""


def _engine(order_service: _RecordingOrderService | None = None) -> StrategyAppService:
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=BrokerFactory(EventBus(), safeguards_repository=AsyncMock()),
        order_app_service=order_service or _RecordingOrderService(),  # type: ignore[arg-type]
        position_app_service=_NoPositions(),  # type: ignore[arg-type]
        risk_check_handler=_AllowAll(),  # type: ignore[arg-type]
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
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
async def test_a_contract_subscription_gets_its_own_spec_priced_broker() -> None:
    engine = _engine()
    await engine.load_strategy(_config("btc", "BTCUSDT:BINANCE", LINEAR_SPEC))
    await engine.load_strategy(_config("eth", "ETHUSDT:BINANCE", LINEAR_SPEC))
    await engine.load_strategy(_config("xau", XAUUSD_SYMBOL, XAUUSD))

    btc, eth, xau = (engine._brokers[s] for s in ("btc", "eth", "xau"))
    assert btc is eth  # crypto still shares one paper account
    assert xau is not btc
    assert isinstance(xau, PaperBrokerAdapter)
    assert xau._contract_spec == XAUUSD
    # Trade forwarding is wired once per broker, not once per subscription.
    for broker in (btc, xau):
        assert broker._trade_callbacks.count(engine._forward_trade_to_bus) == 1  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_contract_signal_floors_to_the_lot_step_and_realizes_in_usd() -> None:
    orders = _RecordingOrderService()
    engine = _engine(orders)
    # 1234 USD at risk against a 10.00 stop is 123.4 oz, 1.234 lots, floored to 1.23.
    risk = RiskConfig(risk_per_trade=0.001234, max_exposure_percent=1.0)
    await engine.load_strategy(_config("xau", XAUUSD_SYMBOL, XAUUSD, risk))
    strategy = engine._strategies["xau"]
    broker = engine._brokers["xau"]

    entry = Signal(
        symbol=XAUUSD_SYMBOL,
        direction=Direction.LONG,
        confidence=1.0,
        timestamp=NOW,
        subscription_id="xau",
        stop_loss_price=2640.0,
    )
    await engine._process_signal(strategy, entry, BarCompletedEvent(close=2650.0), NOW, NOW)

    assert orders.orders[0].quantity == 1.23
    exit_order = OrderAggregate.create(
        subscription_id="xau",
        symbol=XAUUSD_SYMBOL,
        side=OrderSide.SELL,
        order_type=orders.orders[0].order_type,
        quantity=1.23,
        price=2660.0,
    )
    await broker.submit_order(exit_order)
    # 10.00 x 100 oz x 1.23 lots, less 2.50 a lot in and out.
    balance = await broker.get_balance()
    assert balance.available_balance == pytest.approx(1_000_000.0 + 1230.0 - 6.15)


@pytest.mark.asyncio
async def test_reconcile_loads_a_contract_subscription_with_its_spec() -> None:
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
        for symbol in (XAUUSD_SYMBOL, "BTCUSDT:BINANCE")
    ]
    recon = StrategyReconcileAppService(
        None,  # type: ignore[arg-type]
        _Engine(),  # type: ignore[arg-type]
        symbol_lookup=_FakeLookup(),  # type: ignore[arg-type]
    )
    await recon._ensure_instances(subs)

    assert {c.symbol: c.contract_spec for c in loaded} == {
        XAUUSD_SYMBOL: XAUUSD,
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

    for side, price in ((OrderSide.BUY, 2650.00), (OrderSide.SELL, 2650.25)):
        await service._on_order_filled(
            OrderFilledEvent(
                order_id=str(generate_id()),
                subscription_id="xau",
                symbol=XAUUSD_SYMBOL,
                side=side,
                filled_quantity=2.0,
                filled_price=price,
            )
        )

    closed = repo.saved[-1]
    assert closed.is_closed
    assert closed.multiplier == 100.0
    assert closed.realized_pnl == pytest.approx(50.0)
    assert PositionAggregate.from_mongo(closed.to_mongo()).multiplier == 100.0


@pytest.mark.asyncio
async def test_unloading_the_last_subscription_retires_its_paper_account() -> None:
    engine = _engine()
    await engine.load_strategy(_config("btc", "BTCUSDT:BINANCE", LINEAR_SPEC))
    first = engine._brokers["btc"]
    await engine.unload_strategy("btc")

    await engine.load_strategy(_config("eth", "ETHUSDT:BINANCE", LINEAR_SPEC))

    assert engine._brokers["eth"] is not first


@pytest.mark.asyncio
async def test_reconcile_gives_futures_paper_subscriptions_the_futures_risk() -> None:
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
            strategy_code="engulfing",
            symbol=symbol,
            interval=Interval.MINUTE_15,
            created_at=NOW,
        )
        for symbol in (XAUUSD_SYMBOL, "BTCUSDT:BINANCE")
    ]
    recon = StrategyReconcileAppService(
        None,  # type: ignore[arg-type]
        _Engine(),  # type: ignore[arg-type]
        symbol_lookup=_FakeLookup(),  # type: ignore[arg-type]
        futures_paper_risk=RiskConfig(leverage=20),
    )
    await recon._ensure_instances(subs)

    assert {c.symbol: c.risk for c in loaded} == {
        XAUUSD_SYMBOL: RiskConfig(leverage=20),
        "BTCUSDT:BINANCE": RiskConfig(),
    }


def _two_balance_engine(futures_balance: float | None, orders=None) -> StrategyAppService:
    return StrategyAppService(
        event_bus=EventBus(),
        broker_factory=BrokerFactory(EventBus(), safeguards_repository=AsyncMock()),
        order_app_service=orders or _RecordingOrderService(),  # type: ignore[arg-type]
        position_app_service=_NoPositions(),  # type: ignore[arg-type]
        risk_check_handler=_AllowAll(),  # type: ignore[arg-type]
        bar_repository=NoStoredBars(),  # type: ignore[arg-type]
        calendar_factory=Continuous24x7CalendarFactory(),  # type: ignore[arg-type]
        trade_repository=NoClosedTrades(),  # type: ignore[arg-type]
        default_broker_config={
            "initial_balance": 10_000.0,
            "futures_initial_balance": futures_balance,
        },
    )


@pytest.mark.parametrize(
    ("futures_balance", "xau_balance"), [(200_000.0, 200_000.0), (None, 10_000.0)]
)
@pytest.mark.asyncio
async def test_futures_paper_account_starts_at_the_futures_balance(
    futures_balance: float | None, xau_balance: float
) -> None:
    engine = _two_balance_engine(futures_balance)
    await engine.load_strategy(_config("btc", "BTCUSDT:BINANCE", LINEAR_SPEC))
    await engine.load_strategy(_config("xau", XAUUSD_SYMBOL, XAUUSD))

    assert (await engine._brokers["btc"].get_balance()).available_balance == 10_000.0
    assert (await engine._brokers["xau"].get_balance()).available_balance == xau_balance


@pytest.mark.parametrize(
    ("futures_balance", "leverage", "lots"),
    [(200_000.0, 20.0, 1.5), (None, 1.0, None)],
)
@pytest.mark.asyncio
async def test_futures_paper_settings_let_an_xauusd_signal_open_lots(
    futures_balance: float | None, leverage: float, lots: float | None
) -> None:
    # The leveraged cap, 200,000 x 10 % x 20 = 400,000 USD, is 1.509 lots at
    # 2650, floored to 1.50, and binds before the 2 % risk over a 20.00 stop
    # (2.00 lots). The 10,000 crypto balance sizes the same signal to zero.
    orders = _RecordingOrderService()
    engine = _two_balance_engine(futures_balance, orders)
    await engine.load_strategy(_config("xau", XAUUSD_SYMBOL, XAUUSD, RiskConfig(leverage=leverage)))
    signal = Signal(
        symbol=XAUUSD_SYMBOL,
        direction=Direction.LONG,
        confidence=1.0,
        timestamp=NOW,
        subscription_id="xau",
        stop_loss_price=2630.0,
    )
    await engine._process_signal(
        engine._strategies["xau"], signal, BarCompletedEvent(close=2650.0), NOW, NOW
    )

    assert [o.quantity for o in orders.orders] == ([lots] if lots else [])
