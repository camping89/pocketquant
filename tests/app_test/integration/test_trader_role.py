"""The trader role on a real Mongo: standby while another holds the lease, takeover after
a release or an expiry, and exit after a lost renewal."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import structlog

from pocketquant.app import roles
from pocketquant.app.di import create_container
from pocketquant.app.main_extensions import stop_reconcile_loop
from pocketquant.core.common.uuid import generate_id_str
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository
from pocketquant.engine.market_data.app_services.bar_app_service import BarAppService
from pocketquant.engine.strategy.strategy_app_service import StrategyAppService

pytestmark = pytest.mark.integration


async def _wait_for(check: Callable[[], bool], timeout_s: float) -> bool:
    for _ in range(int(timeout_s / 0.05)):
        if check():
            return True
        await asyncio.sleep(0.05)
    return check()


@pytest.fixture
async def trader(settings, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(roles, "logger", structlog.get_logger("test.trader_role"))
    container = create_container(settings)
    db = await container.get(Database)
    for name in ("leases", "orders", "positions", "trades"):
        await db.get_collection(name).drop()
    repo = await container.get(LeaseRepository)
    await repo.ensure_indexes()
    leases = db.get_collection("leases")
    await leases.insert_one(
        {
            "_id": generate_id_str(),
            "name": "trader",
            "owner": "other:1",
            "expires_at": datetime.now(UTC) + timedelta(seconds=60),
        }
    )
    app = SimpleNamespace(state=SimpleNamespace(lease_state={}))
    ctx = SimpleNamespace(
        container=container,
        db=db,
        leases=leases,
        repo=repo,
        app=app,
        engine=await container.get(StrategyAppService),
        bars=await container.get(BarAppService),
    )

    def start() -> None:
        roles.start_trader_lease(container, app, "me:1")  # type: ignore[arg-type]

    await roles.start_trader_standby(container, time.monotonic())
    ctx.start = start
    try:
        yield ctx
    finally:
        task = getattr(app.state, "trader_lease_task", None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await stop_reconcile_loop(app)  # type: ignore[arg-type]
        await container.close()


def _held(ctx: SimpleNamespace) -> Callable[[], bool]:
    return lambda: ctx.app.state.lease_state.get("trader") == "held"


async def test_standby_trader_does_not_trade(trader: SimpleNamespace) -> None:
    trader.start()
    await asyncio.sleep(1.0)

    assert trader.app.state.lease_state["trader"] == "standby"
    assert trader.engine.trading_until is None
    assert trader.bars.publishes_current is False
    assert getattr(trader.app.state, "reconcile_task", None) is None
    for name in ("orders", "positions", "trades"):
        assert await trader.db.get_collection(name).count_documents({}) == 0


def _events(logs: list[Any], *names: str) -> list[Any]:
    return [e for e in logs if e["event"] in names]


async def test_trader_takes_over_after_release_and_logs_both_takeover_events(
    trader: SimpleNamespace,
) -> None:
    with structlog.testing.capture_logs() as logs:
        trader.start()
        await asyncio.sleep(0.2)
        await trader.repo.release("trader", "other:1")
        assert await _wait_for(_held(trader), 2.0)

    doc = await trader.repo.get("trader")
    assert doc is not None
    assert trader.engine.trading_until is not None
    assert abs((doc["expires_at"] - trader.engine.trading_until).total_seconds() - 5.0) < 0.01
    assert not trader.app.state.reconcile_task.done()
    assert trader.bars.publishes_current is True
    acquired, takeover, complete = _events(
        logs, "lease.acquired", "trader.takeover", "trader.takeover_complete"
    )
    assert acquired["event"] == "lease.acquired"
    assert takeover["event"] == "trader.takeover"
    assert isinstance(takeover["handover_gap_ms"], int) and takeover["handover_gap_ms"] >= 0
    assert complete["event"] == "trader.takeover_complete"
    assert isinstance(complete["takeover_ms"], int) and complete["takeover_ms"] >= 0


async def test_takeover_after_a_lost_holder_logs_an_empty_gap(trader: SimpleNamespace) -> None:
    await trader.leases.update_one(
        {"name": "trader"}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )
    with structlog.testing.capture_logs() as logs:
        trader.start()
        assert await _wait_for(_held(trader), 2.0)

    takeover, complete = _events(logs, "trader.takeover", "trader.takeover_complete")
    assert takeover["event"] == "trader.takeover"
    assert takeover["handover_gap_ms"] is None
    assert complete["event"] == "trader.takeover_complete"


async def test_lost_renewal_stops_trading_and_signals_exit(
    trader: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    kills: list[tuple[int, int]] = []
    monkeypatch.setattr(roles, "LEASE_RENEW_S", 0.1)
    monkeypatch.setattr(roles.os, "kill", lambda pid, sig: kills.append((pid, sig)))
    await trader.repo.release("trader", "other:1")
    trader.start()
    assert await _wait_for(_held(trader), 2.0)

    await trader.leases.update_one(
        {"name": "trader"},
        {"$set": {"owner": "thief:1", "expires_at": datetime.now(UTC) + timedelta(seconds=60)}},
    )

    assert await _wait_for(lambda: bool(kills), 1.0)
    assert trader.engine.trading_until is None
    assert trader.bars.publishes_current is False
    assert trader.engine.is_running is False
    assert kills == [(os.getpid(), signal.SIGTERM)]
