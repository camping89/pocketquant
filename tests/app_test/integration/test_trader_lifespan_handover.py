"""Two traders through the real lifespan: SIGTERM mid-open drains at a real 1m boundary,
releases after the delayed ACK, and the standby trader takes over within seconds.

Runs 20-80 s of real time: the lease uses the wall clock, so no simulated time here.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import structlog
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from pocketquant.app import roles
from pocketquant.app.di import create_container
from pocketquant.core.common.messaging import EventBus
from pocketquant.core.common.uuid import generate_id
from pocketquant.core.config import get_settings
from pocketquant.core.domain.bar.events import BarCompletedEvent
from pocketquant.core.domain.brokers.value_objects import OrderResult
from pocketquant.core.domain.order import OrderAggregate, OrderStatus
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.strategy import Direction, Signal
from pocketquant.core.domain.strategy.services import STRATEGY_REGISTRY
from pocketquant.core.domain.strategy.strategy_service_interface import IStrategyService
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.infra.brokers.broker_factory import BrokerFactory
from pocketquant.core.infra.brokers.paper.paper_broker_adapter import PaperBrokerAdapter
from pocketquant.core.infra.market_data.routing_realtime_quote_adapter import (
    RoutingRealtimeQuoteAdapter,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

pytestmark = pytest.mark.integration

_SYM = "BTCUSDT:BINANCE"


class _AlwaysLong(IStrategyService):
    async def on_bar_completed(self, bar: dict) -> Signal | None:
        return Signal(
            symbol=bar["symbol"],
            direction=Direction.LONG,
            confidence=1.0,
            timestamp=bar["timestamp"],
            subscription_id=self.id,
            stop_loss_price=bar["close"] * 0.95,
        )


class SlowAsyncFillBroker(PaperBrokerAdapter):
    """A venue-like paper broker whose open is ACKed only at ``ack_at``."""

    fills_async = True
    ack_at: datetime | None = None
    acked_at: datetime | None = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.sent: set[str] = set()

    @property
    def inflight_count(self) -> int:
        return len(self.sent)

    async def submit_order(
        self, order: OrderAggregate, *, deadline: datetime | None = None
    ) -> OrderResult:
        self.sent.add(str(order.id))
        if self.ack_at is not None:
            await asyncio.sleep(max(0.0, (self.ack_at - datetime.now(UTC)).total_seconds()))
        self.acked_at = datetime.now(UTC)
        self.sent.discard(str(order.id))
        return OrderResult(
            order_id=str(order.id),
            broker_order_id="op1",
            status=OrderStatus.SUBMITTED,
            submitted_at=self.acked_at,
        )


async def _wait_for(check: Callable[[], bool], timeout_s: float) -> bool:
    for _ in range(int(timeout_s / 0.05)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return check()


def _env(monkeypatch: pytest.MonkeyPatch, settings) -> None:  # noqa: ANN001
    """``pocketquant.app.main`` builds its app at import from the environment."""
    for name in (
        "app_name",
        "app_version",
        "environment",
        "mongodb_url",
        "mongodb_database",
        "mongodb_min_pool_size",
        "mongodb_max_pool_size",
        "redis_url",
        "redis_cache_ttl",
        "log_level",
        "log_format",
    ):
        monkeypatch.setenv(name.upper(), str(getattr(settings, name)))
    get_settings.cache_clear()


async def _never_connect(self) -> None:  # noqa: ANN001
    await asyncio.Event().wait()


async def test_sigterm_mid_open_drains_releases_and_the_next_trader_takes_over(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(monkeypatch, settings)
    main = importlib.import_module("pocketquant.app.main")
    trader_settings = settings.model_copy(update={"app_roles": "trader"})
    monkeypatch.setattr(main, "get_settings", lambda: trader_settings)
    # The UTC guard has its own tests; a dev machine may not run in UTC.
    monkeypatch.setattr(main, "assert_utc_runtime", lambda: None)
    monkeypatch.setattr(RoutingRealtimeQuoteAdapter, "run_forever", _never_connect)
    brokers: list[SlowAsyncFillBroker] = []

    def create(self, broker_type: str, config: dict) -> SlowAsyncFillBroker:  # noqa: ANN001
        broker = SlowAsyncFillBroker(fill_delay_ms=0, event_bus=self._event_bus)
        brokers.append(broker)
        return broker

    monkeypatch.setattr(BrokerFactory, "create", create)
    monkeypatch.setitem(STRATEGY_REGISTRY, "hitnrun2", _AlwaysLong)
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(roles, "logger", structlog.get_logger("test.trader_handover"))

    db = Database()
    await db.connect(settings)
    for name in ("leases", "orders", "positions", "trades", "subscriptions", "bars"):
        await db.get_collection(name).drop()
    subs = SubscriptionRepository(db)
    await subs.ensure_indexes()
    sub = Subscription(
        id=generate_id(),
        strategy_code="hitnrun2",
        symbol=_SYM,
        interval=Interval.MINUTE_1,
        created_at=datetime.now(UTC),
        desired_state="running",
        actual_state="stopped",
    )
    await subs.add(sub)

    apps: list[FastAPI] = []
    for _ in range(2):
        app = FastAPI(lifespan=main.lifespan)
        setup_dishka(create_container(trader_settings), app)
        main.register_routes(app, trader_settings)
        apps.append(app)
    app_a, app_b = apps
    cm_b = None

    with structlog.testing.capture_logs() as logs:
        try:
            monkeypatch.setattr(main.socket, "gethostname", lambda: "trader-a")
            cm_a = main.lifespan(app_a)
            await cm_a.__aenter__()
            assert await _wait_for(lambda: app_a.state.lease_state.get("trader") == "held", 5.0)
            monkeypatch.setattr(main.socket, "gethostname", lambda: "trader-b")
            cm_b = main.lifespan(app_b)
            await cm_b.__aenter__()
            assert await _wait_for(lambda: app_b.state.lease_state.get("trader") == "standby", 5.0)

            now = datetime.now(UTC)
            boundary = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            if (boundary - now).total_seconds() < 4:
                boundary += timedelta(minutes=1)
            await asyncio.sleep((boundary - timedelta(seconds=3) - now).total_seconds())
            for broker in brokers:
                broker.ack_at = boundary + timedelta(seconds=5)
            container_a = app_a.state.dishka_container
            engine_a = await container_a.get(StrategyAppService)
            bar_end = datetime.now(UTC) - timedelta(seconds=1)
            await (await container_a.get(EventBus)).publish(
                BarCompletedEvent(
                    symbol=_SYM,
                    interval="1m",
                    bar_start=bar_end - timedelta(minutes=1),
                    open=100.0,
                    high=100.0,
                    low=100.0,
                    close=100.0,
                    volume=1.0,
                    tick_count=1,
                    bar_end=bar_end,
                    closed_at=bar_end,
                    closed_by="timer",
                )
            )
            await asyncio.sleep(0.2)
            assert engine_a.inflight_count() >= 1

            # uvicorn runs lifespan shutdown on SIGTERM after its graceful wait.
            stop = asyncio.create_task(cm_a.__aexit__(None, None, None))
            await asyncio.wait_for(stop, 75.0)

            [released] = [e for e in logs if e["event"] == "trader.lease_released"]
            assert released["inflight"] == 0
            assert 5.0 <= released["offset_s"] <= 6.5
            assert [e for e in logs if e["event"] == "trader.drain_timeout"] == []
            acked = [b.acked_at for b in brokers if b.acked_at is not None]
            assert len(acked) == 1

            assert await _wait_for(lambda: app_b.state.lease_state.get("trader") == "held", 3.0)
            doc = await (await app_b.state.dishka_container.get(LeaseRepository)).get("trader")
            assert doc is not None and doc["owner"].startswith("trader-b:")
            # Mongo keeps milliseconds.
            assert (
                acked[0].replace(microsecond=acked[0].microsecond // 1000 * 1000)
                <= doc["released_at"]
            )
            assert (doc["renewed_at"] - doc["released_at"]).total_seconds() <= 3.0
            after = logs[logs.index(released) :]
            takeover, complete = [
                e for e in after if e["event"] in ("trader.takeover", "trader.takeover_complete")
            ]
            assert takeover["event"] == "trader.takeover"
            assert isinstance(takeover["handover_gap_ms"], int)
            assert complete["event"] == "trader.takeover_complete"
            assert isinstance(complete["takeover_ms"], int)

            transport = ASGITransport(app=app_b)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                health = (await client.get("/health")).json()
            assert health["lease"] == "held"
            assert 0 <= health["lease_renewed_age_s"] < 11
        finally:
            if cm_b is not None:
                # Skip a second real-boundary drain: B's lease simply expires.
                app_b.state.lease_state["trader"] = "lost"
                await cm_b.__aexit__(None, None, None)
            for name in ("leases", "orders", "positions", "subscriptions"):
                await db.get_collection(name).drop()
            await db.disconnect()
