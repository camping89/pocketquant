"""Characterization test pinning SyncStatusRepository atomic counter semantics.

``bump_empty_fetch``/``reset_empty_fetch`` are pure atomic ``$inc``/``$set`` ops:
the repo holds no bump-vs-reset policy — that decision belongs to the sync caller.
The two invariants pinned here:

  1. ``bump_empty_fetch`` increments by exactly 1 per call; ``reset_empty_fetch``
     zeroes it.
  2. The ``$inc`` is atomic — concurrent bumps on the same (symbol, interval)
     never lose an increment.

DB-backed (testcontainers Mongo) → marked integration.
"""

from __future__ import annotations

import asyncio

import pytest

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.sync_status_repository import (
    SyncStatusRepository,
)

pytestmark = pytest.mark.integration

_SYMBOL = "BTCUSDT:BINANCE"
_INTERVAL = Interval.MINUTE_15


@pytest.fixture
async def repo(settings):
    db = Database()
    await db.connect(settings)
    await db.get_collection(SyncStatusRepository._collection_name).drop()
    r = SyncStatusRepository(db)
    await r.ensure_indexes()
    # Seed the (symbol, interval) doc so counter ops target an existing row.
    await r.upsert(_SYMBOL, _INTERVAL, "completed")
    yield r
    await db.disconnect()


@pytest.mark.asyncio
async def test_bump_increments_by_one_each_call(repo) -> None:
    assert await repo.bump_empty_fetch(_SYMBOL, _INTERVAL) == 1
    assert await repo.bump_empty_fetch(_SYMBOL, _INTERVAL) == 2
    doc = await repo.find_one(_SYMBOL, _INTERVAL)
    assert doc is not None
    assert doc.consecutive_empty_fetches == 2


@pytest.mark.asyncio
async def test_reset_zeroes_counter(repo) -> None:
    await repo.bump_empty_fetch(_SYMBOL, _INTERVAL)
    await repo.bump_empty_fetch(_SYMBOL, _INTERVAL)
    await repo.reset_empty_fetch(_SYMBOL, _INTERVAL)
    doc = await repo.find_one(_SYMBOL, _INTERVAL)
    assert doc is not None
    assert doc.consecutive_empty_fetches == 0


@pytest.mark.asyncio
async def test_concurrent_bumps_do_not_lose_increments(repo) -> None:
    """20 concurrent $inc bumps must land exactly 20 — atomic, no lost updates."""
    n = 20
    await asyncio.gather(*(repo.bump_empty_fetch(_SYMBOL, _INTERVAL) for _ in range(n)))
    doc = await repo.find_one(_SYMBOL, _INTERVAL)
    assert doc is not None
    assert doc.consecutive_empty_fetches == n
