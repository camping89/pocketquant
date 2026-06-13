"""Integration tests for SubscriptionRepository — CRUD, bulk ops, triple dedup.

Dedup contract: the unique compound index on (strategy_code, symbol, interval)
is the ONLY duplicate guard — ids are random uuid7, so two adds of the same
triple carry different ids yet still collide at the DB layer.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from pocketquant.core.common.uuid import generate_id
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.subscription import (
    Subscription,
    SubscriptionAlreadyExistsError,
)
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.subscription_repository import (
    SubscriptionRepository,
)

pytestmark = pytest.mark.integration


# Fixtures


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(SubscriptionRepository._collection_name).drop()
    r = SubscriptionRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


# Helpers


def _make_sub(strategy_code: str, symbol: str, interval: Interval) -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code=strategy_code,
        symbol=symbol.upper(),
        interval=interval,
        created_at=datetime.now(UTC),
    )


# Tests


@pytest.mark.asyncio
async def test_add_get_delete_round_trip(repo):
    sub = _make_sub("strat-1", "BTC-USDT:BINANCE", Interval.HOUR_1)
    await repo.add(sub)

    fetched = await repo.get(str(sub.id))
    assert fetched is not None
    assert fetched.id == sub.id
    assert fetched.strategy_code == sub.strategy_code
    assert fetched.symbol == sub.symbol
    assert fetched.interval == sub.interval

    deleted = await repo.delete(str(sub.id))
    assert deleted == 1

    assert await repo.get(str(sub.id)) is None


@pytest.mark.asyncio
async def test_add_same_triple_different_id_raises(repo):
    """Two subs with the SAME triple but DIFFERENT uuid7 ids must collide —
    proves dedup moved from the hash PK to the compound unique index."""
    first = _make_sub("strat-dup", "ETH-USDT:OKX", Interval.MINUTE_5)
    second = _make_sub("strat-dup", "ETH-USDT:OKX", Interval.MINUTE_5)
    assert first.id != second.id

    await repo.add(first)
    with pytest.raises(SubscriptionAlreadyExistsError):
        await repo.add(second)


@pytest.mark.asyncio
async def test_concurrent_add_same_triple_one_doc_one_error(repo):
    """Race two adds of the same triple: exactly one lands, one raises —
    DB-enforced, no codepath pre-check involved."""
    a = _make_sub("strat-race", "BTC-USDT:BINANCE", Interval.MINUTE_5)
    b = _make_sub("strat-race", "BTC-USDT:BINANCE", Interval.MINUTE_5)

    results = await asyncio.gather(repo.add(a), repo.add(b), return_exceptions=True)

    errors = [r for r in results if isinstance(r, SubscriptionAlreadyExistsError)]
    assert len(errors) == 1
    stored = await repo.list_by_strategy_code("strat-race")
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_dedup_triple_unique_index_exists(repo):
    coll = repo._collection()
    info = await coll.index_information()
    idx = info["ix_subscriptions_dedup_triple"]
    assert idx.get("unique") is True
    assert idx["key"] == [("strategy_code", 1), ("symbol", 1), ("interval", 1)]


@pytest.mark.asyncio
async def test_list_by_strategy_code_filters_correctly(repo):
    sub_a1 = _make_sub("strat-a", "BTC-USDT:BINANCE", Interval.HOUR_1)
    sub_a2 = _make_sub("strat-a", "ETH-USDT:BINANCE", Interval.HOUR_1)
    sub_b1 = _make_sub("strat-b", "SOL-USDT:OKX", Interval.MINUTE_15)

    await repo.add(sub_a1)
    await repo.add(sub_a2)
    await repo.add(sub_b1)

    results_a = await repo.list_by_strategy_code("strat-a")
    ids_a = {s.id for s in results_a}
    assert ids_a == {sub_a1.id, sub_a2.id}

    results_b = await repo.list_by_strategy_code("strat-b")
    assert len(results_b) == 1
    assert results_b[0].id == sub_b1.id

    # Non-existent strategy returns empty list
    assert await repo.list_by_strategy_code("strat-c") == []


@pytest.mark.asyncio
async def test_update_desired_state_persists_and_leaves_actual(repo):
    sub = _make_sub("strat-desired", "BTC-USDT:BINANCE", Interval.HOUR_1)
    await repo.add(sub)

    modified = await repo.update_desired_state(str(sub.id), "running")
    assert modified == 1

    fetched = await repo.get(str(sub.id))
    assert fetched is not None
    assert fetched.desired_state == "running"
    assert fetched.actual_state == "stopped"  # untouched


@pytest.mark.asyncio
async def test_update_actual_state_persists(repo):
    sub = _make_sub("strat-actual", "ETH-USDT:BINANCE", Interval.HOUR_1)
    await repo.add(sub)

    modified = await repo.update_actual_state(str(sub.id), "running")
    assert modified == 1

    fetched = await repo.get(str(sub.id))
    assert fetched is not None
    assert fetched.actual_state == "running"
    assert fetched.desired_state == "stopped"


@pytest.mark.asyncio
async def test_update_desired_state_missing_sub_returns_zero(repo):
    assert await repo.update_desired_state("does-not-exist", "running") == 0


@pytest.mark.asyncio
async def test_delete_by_strategy_code_bulk(repo):
    sub_a1 = _make_sub("strat-bulk-a", "BTC-USDT:BINANCE", Interval.HOUR_1)
    sub_a2 = _make_sub("strat-bulk-a", "ETH-USDT:BINANCE", Interval.HOUR_1)
    sub_a3 = _make_sub("strat-bulk-a", "SOL-USDT:BINANCE", Interval.HOUR_1)
    sub_b1 = _make_sub("strat-bulk-b", "XRP-USDT:OKX", Interval.DAY_1)

    for sub in (sub_a1, sub_a2, sub_a3, sub_b1):
        await repo.add(sub)

    deleted = await repo.delete_by_strategy_code("strat-bulk-a")
    assert deleted == 3

    assert await repo.list_by_strategy_code("strat-bulk-a") == []
    remaining = await repo.list_by_strategy_code("strat-bulk-b")
    assert len(remaining) == 1
    assert remaining[0].id == sub_b1.id
