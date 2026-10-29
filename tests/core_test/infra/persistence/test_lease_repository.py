"""LeaseRepository against a real Mongo: one winner, renewal, expiry and release."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
import structlog

from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories import lease_repository as lease_module
from pocketquant.core.infra.persistence.repositories.lease_repository import LeaseRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def repo(settings, monkeypatch: pytest.MonkeyPatch):
    # A module logger cached by an earlier test ignores capture_logs; rebind a fresh one.
    monkeypatch.setattr(lease_module, "logger", structlog.get_logger("test.lease_repository"))
    db = Database()
    await db.connect(settings)
    await db.get_collection(LeaseRepository._collection_name).drop()
    r = LeaseRepository(db)
    await r.ensure_indexes()
    yield r
    await db.disconnect()


async def test_two_contenders_one_acquires(repo: LeaseRepository) -> None:
    results = await asyncio.gather(repo.acquire("trader", "a", 30), repo.acquire("trader", "b", 30))

    assert sum(r is not None for r in results) == 1
    assert await repo._collection().count_documents({"name": "trader"}) == 1


async def test_holder_renews_with_a_later_expiry(repo: LeaseRepository) -> None:
    first = await repo.acquire("trader", "a", 30)
    second = await repo.acquire("trader", "a", 30)

    assert first is not None and second is not None
    assert second > first


async def test_expired_lease_goes_to_the_other_owner(repo: LeaseRepository) -> None:
    await repo.acquire("trader", "a", 0.2)
    await asyncio.sleep(0.3)

    assert await repo.acquire("trader", "b", 30) is not None
    doc = await repo.get("trader")
    assert doc is not None and doc["owner"] == "b"


async def test_release_sets_released_at_and_lets_the_other_in(repo: LeaseRepository) -> None:
    await repo.acquire("trader", "a", 30)

    with structlog.testing.capture_logs() as logs:
        await repo.release("trader", "a")

    released = [e for e in logs if e["event"] == "lease.released"]
    assert [(e["name"], e["owner"]) for e in released] == [("trader", "a")]
    doc = await repo.get("trader")
    assert doc is not None and doc["released_at"] is not None
    assert await repo.acquire("trader", "b", 30) is not None


async def test_release_by_a_non_owner_changes_nothing(repo: LeaseRepository) -> None:
    await repo.acquire("trader", "a", 30)

    with structlog.testing.capture_logs() as logs:
        await repo.release("trader", "b")

    assert [e for e in logs if e["event"] == "lease.released"] == []
    assert await repo.acquire("trader", "b", 30) is None


async def test_document_has_uuid7_id_and_unique_name_index(repo: LeaseRepository) -> None:
    await repo.acquire("trader", "a", 30)

    doc = await repo.get("trader")
    assert doc is not None and UUID(doc["_id"]).version == 7
    indexes = await repo._collection().index_information()
    assert indexes["ux_leases_name"]["unique"] is True
