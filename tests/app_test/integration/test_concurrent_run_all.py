"""Integration test: two simultaneous POST /run-all calls → exactly N requests, not 2N.

Runs against the stateless bff (HTTP enqueue only — no worker). Relies on the
deterministic ``bt:{sub_id}`` request id + upsert enqueue so the second fan-out
collapses onto the first rather than duplicating compute (the queue replacement
for the old APScheduler replace_existing dedup).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.infrastructure.persistence.mongodb import Database
from pocketquant.infrastructure.persistence.repositories.bar_repository import BarRepository
from pocketquant.infrastructure.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

pytestmark = pytest.mark.integration

_API = "/api/v1/strategies"
_STRATEGY_ID = "hitnrun2"
_SYMBOL = "BTC-USDT:BINANCE"
_INTERVAL = "1h"


def _minimal_bars(n: int = 30) -> list[Bar]:
    base = datetime(2024, 6, 1, tzinfo=UTC)
    price = 50_000.0
    return [
        Bar(
            symbol=_SYMBOL,
            interval=Interval.HOUR_1,
            datetime=base + timedelta(hours=i),
            open=price,
            high=price * 1.001,
            low=price * 0.999,
            close=price,
            volume=5.0,
            tick_count=60,
        )
        for i in range(n)
    ]


@pytest_asyncio.fixture(autouse=True)
async def setup(bff_client):
    """Track symbol + seed bars + clean prior state via bff repos.

    bff is stateless — no StrategyAppService load. run-all enqueue + dedup is a
    pure Mongo path, so only the tracked symbol (add_symbol fail-fast check) and
    a clean subscriptions collection are needed.
    """
    from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
    from pocketquant.infrastructure.persistence.repositories.tracked_symbol_repository import (
        TrackedSymbolRepository,
    )

    container = bff_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    bar_repo: BarRepository = await container.get(BarRepository)
    sub_repo: SubscriptionRepository = await container.get(SubscriptionRepository)
    tracked_repo: TrackedSymbolRepository = await container.get(TrackedSymbolRepository)

    await tracked_repo.upsert(TrackedSymbol(symbol=_SYMBOL))
    await bar_repo.insert_many(_minimal_bars(), source="test")
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    db: Database = await container.get(Database)
    await db.get_collection("backtest_requests").delete_many({"strategy_code": _STRATEGY_ID})

    yield

    await bar_repo._collection().delete_many({"symbol": _SYMBOL, "interval": _INTERVAL})
    await sub_repo._collection().delete_many({"strategy_code": _STRATEGY_ID})
    await db.get_collection("backtest_requests").delete_many({"strategy_code": _STRATEGY_ID})


@pytest.mark.asyncio
async def test_concurrent_run_all_no_duplicate_requests(bff_client):
    """Two simultaneous run-all calls enqueue exactly 1 request per sub, not 2."""
    container = bff_client._transport.app.state.dishka_container  # type: ignore[attr-defined]
    db: Database = await container.get(Database)

    # Add a subscription
    add_r = await bff_client.post(
        f"{_API}/{_STRATEGY_ID}/subscriptions",
        json={"symbol": _SYMBOL, "interval": _INTERVAL},
    )
    assert add_r.status_code == 201, add_r.text
    sub_id = add_r.json()["id"]
    expected_request_id = f"bt:{sub_id}"

    # Both fan-outs must return the same deterministic request id for the sub.
    r1, r2 = await asyncio.gather(
        bff_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests"),
        bff_client.post(f"{_API}/{_STRATEGY_ID}/run-all-backtests"),
    )
    assert r1.status_code == 202, r1.text
    assert r2.status_code == 202, r2.text
    assert expected_request_id in r1.json()["job_ids"]
    assert expected_request_id in r2.json()["job_ids"]

    # Deterministic id + upsert ⇒ exactly one request doc for the sub, regardless
    # of how far the worker has drained it.
    requests = db.get_collection("backtest_requests")
    count = await requests.count_documents({"_id": expected_request_id})
    assert count == 1, f"Expected 1 request doc for {expected_request_id}, got {count}"
