"""Integration tests for StrategySubscriptionRepository — CRUD + bulk ops."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.mongodb import Database
from pocketquant.trading.domain.subscription import (
    StrategySubscription,
    SubscriptionAlreadyExistsError,
)
from pocketquant.trading.persistence.strategy_subscription_repository import (
    StrategySubscriptionRepository,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(StrategySubscriptionRepository._collection_name).drop()
    r = StrategySubscriptionRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sub(strategy_id: str, symbol: str, exchange: str, interval: Interval) -> StrategySubscription:
    sub_id = StrategySubscription.deterministic_id(strategy_id, symbol, exchange, interval)
    return StrategySubscription(
        id=sub_id,
        strategy_id=strategy_id,
        symbol=symbol.upper(),
        exchange=exchange.upper(),
        interval=interval,
        created_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_get_delete_round_trip(repo):
    sub = _make_sub("strat-1", "BTC-USDT", "BINANCE", Interval.HOUR_1)
    await repo.add(sub)

    fetched = await repo.get(sub.id)
    assert fetched is not None
    assert fetched.id == sub.id
    assert fetched.strategy_id == sub.strategy_id
    assert fetched.symbol == sub.symbol
    assert fetched.exchange == sub.exchange
    assert fetched.interval == sub.interval

    deleted = await repo.delete(sub.id)
    assert deleted == 1

    assert await repo.get(sub.id) is None


@pytest.mark.asyncio
async def test_add_duplicate_raises(repo):
    sub = _make_sub("strat-dup", "ETH-USDT", "OKX", Interval.MINUTE_5)
    await repo.add(sub)

    with pytest.raises(SubscriptionAlreadyExistsError):
        await repo.add(sub)


@pytest.mark.asyncio
async def test_list_by_strategy_filters_correctly(repo):
    sub_a1 = _make_sub("strat-a", "BTC-USDT", "BINANCE", Interval.HOUR_1)
    sub_a2 = _make_sub("strat-a", "ETH-USDT", "BINANCE", Interval.HOUR_1)
    sub_b1 = _make_sub("strat-b", "SOL-USDT", "OKX", Interval.MINUTE_15)

    await repo.add(sub_a1)
    await repo.add(sub_a2)
    await repo.add(sub_b1)

    results_a = await repo.list_by_strategy("strat-a")
    ids_a = {s.id for s in results_a}
    assert ids_a == {sub_a1.id, sub_a2.id}

    results_b = await repo.list_by_strategy("strat-b")
    assert len(results_b) == 1
    assert results_b[0].id == sub_b1.id

    # Non-existent strategy returns empty list
    assert await repo.list_by_strategy("strat-c") == []


@pytest.mark.asyncio
async def test_delete_by_strategy_bulk(repo):
    sub_a1 = _make_sub("strat-bulk-a", "BTC-USDT", "BINANCE", Interval.HOUR_1)
    sub_a2 = _make_sub("strat-bulk-a", "ETH-USDT", "BINANCE", Interval.HOUR_1)
    sub_a3 = _make_sub("strat-bulk-a", "SOL-USDT", "BINANCE", Interval.HOUR_1)
    sub_b1 = _make_sub("strat-bulk-b", "XRP-USDT", "OKX", Interval.DAY_1)

    for sub in (sub_a1, sub_a2, sub_a3, sub_b1):
        await repo.add(sub)

    deleted = await repo.delete_by_strategy("strat-bulk-a")
    assert deleted == 3

    assert await repo.list_by_strategy("strat-bulk-a") == []
    remaining = await repo.list_by_strategy("strat-bulk-b")
    assert len(remaining) == 1
    assert remaining[0].id == sub_b1.id
