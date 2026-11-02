# The unique index on (strategy_code, symbol, intervals_key) is the only duplicate guard:
# ids are random uuid7, so two adds of one interval set carry different ids yet still
# collide at the DB layer.

from __future__ import annotations

import asyncio
from dataclasses import replace
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


def _make_sub(strategy_code: str, symbol: str, *intervals: Interval, **overrides) -> Subscription:
    return Subscription(
        id=generate_id(),
        strategy_code=strategy_code,
        symbol=symbol.upper(),
        intervals=intervals,
        created_at=datetime.now(UTC),
        **overrides,
    )


# Tests


@pytest.mark.asyncio
async def test_add_get_delete_round_trip(repo):
    sub = _make_sub(
        "strat-1", "BTC-USDT:BINANCE", Interval.HOUR_1, Interval.HOUR_4, parameters={"min_bars": 2}
    )
    await repo.add(sub)

    fetched = await repo.get(str(sub.id))
    assert fetched is not None
    assert fetched.id == sub.id
    assert fetched.strategy_code == sub.strategy_code
    assert fetched.symbol == sub.symbol
    assert fetched.intervals == sub.intervals
    assert fetched.parameters == {"min_bars": 2}

    deleted = await repo.delete(str(sub.id))
    assert deleted == 1

    assert await repo.get(str(sub.id)) is None


@pytest.mark.asyncio
async def test_add_same_triple_different_id_raises(repo):
    first = _make_sub("strat-dup", "ETH-USDT:OKX", Interval.MINUTE_5)
    second = _make_sub("strat-dup", "ETH-USDT:OKX", Interval.MINUTE_5)
    assert first.id != second.id

    await repo.add(first)
    with pytest.raises(SubscriptionAlreadyExistsError):
        await repo.add(second)


@pytest.mark.asyncio
async def test_concurrent_add_same_triple_one_doc_one_error(repo):
    a = _make_sub("strat-race", "BTC-USDT:BINANCE", Interval.MINUTE_5)
    b = _make_sub("strat-race", "BTC-USDT:BINANCE", Interval.MINUTE_5)

    results = await asyncio.gather(repo.add(a), repo.add(b), return_exceptions=True)

    errors = [r for r in results if isinstance(r, SubscriptionAlreadyExistsError)]
    assert len(errors) == 1
    stored = await repo.list_by_strategy_code("strat-race")
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_dedup_intervals_unique_index_exists(repo):
    coll = repo._collection()
    info = await coll.index_information()
    idx = info["ix_subscriptions_dedup_intervals"]
    assert idx.get("unique") is True
    assert idx["key"] == [("strategy_code", 1), ("symbol", 1), ("intervals_key", 1)]


@pytest.mark.asyncio
async def test_two_interval_sets_sharing_the_entry_interval_coexist(repo):
    await repo.add(_make_sub("strat-sets", "BTC-USDT:BINANCE", Interval.MINUTE_15, Interval.HOUR_1))
    await repo.add(_make_sub("strat-sets", "BTC-USDT:BINANCE", Interval.MINUTE_15, Interval.HOUR_4))
    assert len(await repo.list_by_strategy_code("strat-sets")) == 2


@pytest.mark.asyncio
async def test_update_config_changes_only_a_stopped_subscription(repo):
    stopped = _make_sub("strat-edit", "BTC-USDT:BINANCE", Interval.MINUTE_15)
    running = _make_sub("strat-edit", "ETH-USDT:BINANCE", Interval.MINUTE_15)
    running = replace(running, desired_state="running")
    await repo.add(stopped)
    await repo.add(running)

    new_config = {"intervals": (Interval.MINUTE_15, Interval.HOUR_1), "parameters": {"min_bars": 2}}
    assert await repo.update_config(replace(stopped, **new_config)) == 1
    fetched = await repo.get(str(stopped.id))
    assert fetched is not None
    assert fetched.intervals == (Interval.MINUTE_15, Interval.HOUR_1)
    assert fetched.parameters == {"min_bars": 2}

    assert await repo.update_config(replace(running, **new_config)) == 0
    unchanged = await repo.get(str(running.id))
    assert unchanged is not None
    assert unchanged.intervals == (Interval.MINUTE_15,)
    assert unchanged.parameters == {}


@pytest.mark.asyncio
async def test_update_config_onto_an_existing_set_conflicts(repo):
    taken = _make_sub("strat-clash", "BTC-USDT:BINANCE", Interval.MINUTE_15, Interval.HOUR_1)
    other = _make_sub("strat-clash", "BTC-USDT:BINANCE", Interval.MINUTE_15)
    await repo.add(taken)
    await repo.add(other)
    with pytest.raises(SubscriptionAlreadyExistsError):
        await repo.update_config(replace(other, intervals=taken.intervals))


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
async def test_update_desired_state_idempotent_reset_still_matches(repo):
    # Re-setting an already-running sub is a no-op write (modified_count == 0) but
    # the sub exists; the return must stay 1 so start/stop don't report not-found.
    sub = _make_sub("strat-idem", "BTC-USDT:BINANCE", Interval.HOUR_1)
    await repo.add(sub)
    assert await repo.update_desired_state(str(sub.id), "running") == 1
    assert await repo.update_desired_state(str(sub.id), "running") == 1


@pytest.mark.asyncio
async def test_request_action_sets_only_when_none(repo):
    sub = _make_sub("probe", "BTCUSDT:BINANCE", Interval.MINUTE_5)
    await repo.add(sub)

    assert await repo.request_action(str(sub.id), "close") == 1
    assert await repo.request_action(str(sub.id), "cancel") == 0

    stored = await repo.get(str(sub.id))
    assert stored is not None
    assert stored.manual_action == "close"


@pytest.mark.asyncio
async def test_clear_action_clears_only_the_same_value(repo):
    sub = _make_sub("probe", "BTCUSDT:BINANCE", Interval.MINUTE_5)
    await repo.add(sub)
    await repo.request_action(str(sub.id), "close")

    assert await repo.clear_action(str(sub.id), "cancel", "accepted") == 0

    stored = await repo.get(str(sub.id))
    assert stored is not None
    assert stored.manual_action == "close"


@pytest.mark.asyncio
async def test_clear_action_records_the_outcome(repo):
    sub = _make_sub("probe", "BTCUSDT:BINANCE", Interval.MINUTE_5)
    await repo.add(sub)
    await repo.request_action(str(sub.id), "close")

    assert await repo.clear_action(str(sub.id), "close", "rejected:close_failed") == 1

    stored = await repo.get(str(sub.id))
    assert stored is not None
    assert stored.manual_action is None
    assert stored.manual_action_outcome is not None
    assert stored.manual_action_outcome["action"] == "close"
    assert stored.manual_action_outcome["outcome"] == "rejected:close_failed"
    assert isinstance(stored.manual_action_outcome["at"], datetime)
