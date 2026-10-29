"""BarRepository writes decide from Mongo alone, so another process's delete is written over."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def databases(settings):
    first, second = Database(), Database()
    await first.connect(settings)
    await second.connect(settings)
    await first.get_collection(BarRepository._collection_name).drop()
    yield first, second
    await first.disconnect()
    await second.disconnect()


async def test_a_bar_deleted_by_another_process_is_written_again(databases) -> None:
    first, second = databases
    repo = BarRepository(first)
    bar = Bar(
        symbol="SHARED:EXNESS",
        interval=Interval.MINUTE_1,
        datetime=datetime(2026, 10, 13, 10, 0, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=10.0,
        tick_count=3,
    )
    await repo.upsert_bar(bar, source="test")

    other = second.get_collection(BarRepository._collection_name)
    await other.delete_many({"symbol": bar.symbol.upper()})
    await repo.upsert_bar(bar, source="test")

    assert await other.count_documents({"symbol": bar.symbol.upper()}) == 1
