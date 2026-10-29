"""DELETE /tracked-symbols/{symbol} empties every collection and cache key of the symbol.

Seeds the same shape of data for two symbols against real Mongo + Redis, deletes
one through the HTTP route, and checks the other symbol is left untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.app.middleware.admin_auth_middleware import verify_admin_token
from pocketquant.core.common.uuid import generate_id, generate_id_str
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import Subscription
from pocketquant.core.domain.tracked_symbol.entities import TrackedSymbol
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.redis import Cache
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)
from pocketquant.core.infra.persistence.repositories.tracked_symbol_repository import (
    TrackedSymbolRepository,
)

pytestmark = pytest.mark.integration

_GONE = "CASCADEA:BINANCE"
_KEPT = "CASCADEB:BINANCE"
_SYMBOL_COLLECTIONS = (
    "tracked_symbols",
    "symbols",
    "bars",
    "sync_status",
    "subscriptions",
    "backtest_runs",
    "backtest_orders",
    "backtest_trades",
    "orders",
    "positions",
    "trades",
)


def _cache_keys(symbol: str) -> list[str]:
    return [
        f"quote:latest:{symbol}",
        f"bar:current:{symbol}:1m",
        f"bar:current:{symbol}:1d",
        f"ohlcv:{symbol}:1h:500",
        f"data_lag:{symbol}",
    ]


def _symbol_query(symbol: str) -> dict:
    return {"$or": [{"symbol": symbol}, {"config_snapshot.symbol": symbol}]}


async def _seed(container, symbol: str) -> None:
    db = await container.get(Database)
    await (await container.get(TrackedSymbolRepository)).upsert(TrackedSymbol(symbol=symbol))
    bar_repo = await container.get(BarRepository)
    for minute in range(3):
        await bar_repo.upsert_bar(
            Bar(
                symbol=symbol,
                interval=Interval.MINUTE_1,
                datetime=datetime(2026, 1, 1, 0, minute, tzinfo=UTC),
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=10.0,
            ),
            source="test",
        )
    await (await container.get(SubscriptionRepository)).add(
        Subscription(
            id=generate_id(),
            strategy_code="cascade-test",
            symbol=symbol,
            interval=Interval.HOUR_1,
            created_at=datetime.now(UTC),
            desired_state="running",
            actual_state="running",
        )
    )
    run_id = generate_id_str()
    for name, docs in {
        "symbols": [{"symbol": symbol}],
        "sync_status": [{"symbol": symbol, "interval": "1m"}, {"symbol": symbol, "interval": "1h"}],
        "backtest_runs": [
            {"symbol": symbol, "strategy_code": "cascade-test", "status": "finished"},
            {"config_snapshot": {"symbol": symbol}, "strategy_code": "cascade-test"},
        ],
        "backtest_orders": [{"run_id": run_id, "symbol": symbol}] * 2,
        "backtest_trades": [{"run_id": run_id, "symbol": symbol}],
        "orders": [{"symbol": symbol, "status": "filled"}],
        "positions": [{"symbol": symbol, "is_closed": True}],
        "trades": [{"run_id": generate_id_str(), "symbol": symbol}] * 2,
    }.items():
        await db.get_collection(name).insert_many([{"_id": generate_id_str(), **d} for d in docs])
    cache = await container.get(Cache)
    for key in _cache_keys(symbol):
        await cache.set(key, {"v": 1}, ttl=600)


async def _clean(container) -> None:
    db = await container.get(Database)
    for symbol in (_GONE, _KEPT):
        for name in _SYMBOL_COLLECTIONS:
            await db.get_collection(name).delete_many(_symbol_query(symbol))
        await (await container.get(Cache)).delete_pattern(f"*{symbol}*")
    await db.get_collection("job_history").delete_many({"job_id": "cascade-test"})


@pytest.fixture
async def container(app_client):
    app = app_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[verify_admin_token] = lambda: None
    c = app.state.dishka_container
    await _clean(c)
    yield c
    await _clean(c)


async def _counts(container, symbol: str) -> dict[str, int]:
    db = await container.get(Database)
    counts = {
        name: await db.get_collection(name).count_documents(_symbol_query(symbol))
        for name in _SYMBOL_COLLECTIONS
    }
    counts["job_history"] = await db.get_collection("job_history").count_documents(
        {"details.symbol": symbol}
    )
    cache = await container.get(Cache)
    counts["cache_keys"] = sum([await cache.exists(k) for k in _cache_keys(symbol)])
    return counts


@pytest.mark.asyncio
async def test_delete_cascades_all_symbol_data_and_spares_other_symbols(app_client, container):
    await _seed(container, _GONE)
    await _seed(container, _KEPT)
    await (
        (await container.get(Database))
        .get_collection("job_history")
        .insert_many(
            [
                {
                    "_id": generate_id_str(),
                    "job_id": "cascade-test",
                    "details": [{"symbol": _GONE}, {"symbol": _KEPT}],
                },
                {
                    "_id": generate_id_str(),
                    "job_id": "cascade-test",
                    "details": [{"symbol": _GONE}],
                },
            ]
        )
    )
    kept_before = await _counts(container, _KEPT)

    r = await app_client.delete(f"/api/v1/market-data/tracked-symbols/{_GONE.replace(':', '%3A')}")

    assert r.status_code == 200, r.text
    assert r.json() == {
        "symbol": _GONE,
        "status": "removed",
        "deleted": {
            "tracked_symbols": 1,
            "subscriptions": 1,
            "symbols": 1,
            "bars": 3,
            "sync_status": 2,
            "backtest_orders": 2,
            "backtest_trades": 1,
            "backtest_runs": 2,
            "orders": 1,
            "positions": 1,
            "trades": 2,
            "job_history_runs": 2,
            "cache_keys": 5,
        },
    }
    assert set((await _counts(container, _GONE)).values()) == {0}
    assert await _counts(container, _KEPT) == kept_before
    assert all(v > 0 for v in kept_before.values())
    assert (
        await (await container.get(Database))
        .get_collection("job_history")
        .count_documents({"job_id": "cascade-test"})
        == 2
    )

    again = await app_client.delete(
        f"/api/v1/market-data/tracked-symbols/{_GONE.replace(':', '%3A')}"
    )
    assert again.status_code == 200, again.text
    assert set(again.json()["deleted"].values()) == {0}
