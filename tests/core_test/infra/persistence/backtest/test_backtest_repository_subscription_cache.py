"""Subscription cache-slot semantics on backtest_runs — field-keyed, uuid7 _id.

Cache docs are keyed by the ``subscription_id`` FIELD (unique sparse index),
not by ``_id``. The doc ``_id`` is a uuid7 allocated once when the slot is
first inserted and stays stable across overwrites; single-run docs never
carry ``subscription_id`` so they live outside the slot index entirely.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from pymongo.errors import DuplicateKeyError

from pocketquant.core.common.uuid import UUID, generate_id, generate_id_str
from pocketquant.core.domain.backtest import BacktestMetrics, BacktestResult, EquityPoint
from pocketquant.core.infra.persistence.mongodb import Database
from pocketquant.core.infra.persistence.repositories.backtest_repository import (
    BacktestRepository,
)

NOW = datetime(2026, 1, 5, 10, 0, 0)
SUB_ID = "eef73dffbd77a20b"  # legacy 16-hex subscription id shape (pre Phase-6)


def _result(equity: float = 10_000.0) -> BacktestResult:
    return BacktestResult(
        id=generate_id(),
        strategy_code="s1",
        config_snapshot={"symbol": "BTC:BIN", "interval": "1m"},
        metrics=BacktestMetrics.empty(),
        equity_curve=[EquityPoint(timestamp=NOW, equity=equity, drawdown=0.0)],
        started_at=NOW,
        completed_at=NOW,
        status="completed",
    )


@pytest.mark.asyncio
async def test_save_for_subscription_keeps_one_doc_with_stable_uuid_slot_id(
    database: Database,
) -> None:
    repo = BacktestRepository(database)
    await repo.ensure_indexes()

    await repo.save_for_subscription(SUB_ID, _result(equity=1.0))
    coll = database.get_collection("backtest_runs")
    first = await coll.find_one({"subscription_id": SUB_ID})
    assert first is not None
    assert UUID(first["_id"]).version == 7  # slot _id is uuid7, NOT the sub id
    assert first["_id"] != SUB_ID

    await repo.save_for_subscription(SUB_ID, _result(equity=2.0))
    docs = await coll.find({"subscription_id": SUB_ID}).to_list(length=10)
    assert len(docs) == 1  # still exactly one cache doc per subscription
    assert docs[0]["_id"] == first["_id"]  # slot identity survives overwrite
    assert docs[0]["equity_curve"][0]["equity"] == 2.0  # content = latest save


@pytest.mark.asyncio
async def test_save_for_subscription_does_not_mutate_result_id(database: Database) -> None:
    repo = BacktestRepository(database)
    result = _result()
    engine_run_id = result.id
    await repo.save_for_subscription(SUB_ID, result)
    assert result.id == engine_run_id  # no more result.id = sub_id override


@pytest.mark.asyncio
async def test_find_by_subscription_returns_latest_cache_content(database: Database) -> None:
    repo = BacktestRepository(database)
    saved = _result(equity=3.5)
    await repo.save_for_subscription(SUB_ID, saved)

    fetched = await repo.find_by_subscription(SUB_ID)
    assert fetched is not None
    assert isinstance(fetched.id, UUID)
    assert fetched.strategy_code == saved.strategy_code
    assert fetched.equity_curve[0].equity == 3.5

    assert await repo.find_by_subscription("no-such-sub") is None


@pytest.mark.asyncio
async def test_upsert_status_then_full_save_share_one_slot(database: Database) -> None:
    repo = BacktestRepository(database)
    coll = database.get_collection("backtest_runs")

    await repo.upsert_status(SUB_ID, strategy_code="s1", status="running")
    status_doc = await coll.find_one({"subscription_id": SUB_ID})
    assert status_doc is not None
    assert UUID(status_doc["_id"]).version == 7
    assert status_doc["status"] == "running"

    await repo.save_for_subscription(SUB_ID, _result())
    docs = await coll.find({"subscription_id": SUB_ID}).to_list(length=10)
    assert len(docs) == 1
    assert docs[0]["_id"] == status_doc["_id"]
    assert docs[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_single_run_and_cache_docs_are_independent(database: Database) -> None:
    repo = BacktestRepository(database)
    coll = database.get_collection("backtest_runs")

    single = _result()
    await repo.save(single)
    await repo.save_for_subscription(SUB_ID, _result())

    assert await coll.count_documents({}) == 2
    single_doc = await coll.find_one({"_id": str(single.id)})
    assert single_doc is not None
    assert "subscription_id" not in single_doc  # single-run docs stay out of the slot index


@pytest.mark.asyncio
async def test_subscription_statuses_keyed_by_sub_id(database: Database) -> None:
    """FE status badges look up by sub_id — keying by slot _id would break them."""
    repo = BacktestRepository(database)
    other_sub = "abc123def4567890"
    await repo.upsert_status(SUB_ID, strategy_code="s1", status="completed")
    await repo.upsert_status(other_sub, strategy_code="s1", status="failed", error_msg="boom")

    out = await repo.get_subscription_statuses([SUB_ID, other_sub, "missing"])
    assert set(out) == {SUB_ID, other_sub}
    assert out[SUB_ID]["status"] == "completed"
    assert out[other_sub]["status"] == "failed"
    assert out[other_sub]["error_msg"] == "boom"

    one = await repo.get_subscription_status(SUB_ID)
    assert one is not None and one["status"] == "completed"


@pytest.mark.asyncio
async def test_find_doc_by_subscription_returns_raw_doc(database: Database) -> None:
    repo = BacktestRepository(database)
    await repo.upsert_status(SUB_ID, strategy_code="s1", status="running")

    doc = await repo.find_doc_by_subscription(SUB_ID)
    assert doc is not None
    assert doc["subscription_id"] == SUB_ID
    assert doc["status"] == "running"
    assert "_id" not in doc and UUID(doc["id"]).version == 7


@pytest.mark.asyncio
async def test_delete_by_subscription_removes_only_cache_doc(database: Database) -> None:
    repo = BacktestRepository(database)
    single = _result()
    await repo.save(single)
    await repo.save_for_subscription(SUB_ID, _result())

    assert await repo.delete_by_subscription(SUB_ID) == 1
    assert await repo.find_by_subscription(SUB_ID) is None
    assert await repo.get(str(single.id)) is not None  # single-run doc untouched


@pytest.mark.asyncio
async def test_unique_index_rejects_second_doc_for_same_subscription(
    database: Database,
) -> None:
    repo = BacktestRepository(database)
    await repo.ensure_indexes()
    coll = database.get_collection("backtest_runs")

    await coll.insert_one({"_id": generate_id_str(), "subscription_id": SUB_ID})
    with pytest.raises(DuplicateKeyError):
        await coll.insert_one({"_id": generate_id_str(), "subscription_id": SUB_ID})
