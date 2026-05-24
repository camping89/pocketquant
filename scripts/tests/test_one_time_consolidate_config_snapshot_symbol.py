"""Unit tests for ``one_time_consolidate_config_snapshot_symbol``.

Use mongomock-backed AsyncMongoClient-style stubs to exercise migration logic
without spinning up a real Mongo. The script depends only on
``find/count_documents/bulk_write`` so a minimal in-memory fake covers it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scripts.one_time_consolidate_config_snapshot_symbol import _migrate, _residual_count


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def __aiter__(self) -> "_FakeCursor":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)

    async def close(self) -> None:
        return None


class _FakeCollection:
    """Minimal async fake supporting the subset used by the migration script."""

    name = "fake"

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = {d["_id"]: d for d in docs}

    async def count_documents(self, filt: dict[str, Any]) -> int:
        return sum(1 for _ in self._matching(filt))

    def find(self, filt: dict[str, Any], **_kwargs: Any) -> _FakeCursor:
        return _FakeCursor(list(self._matching(filt)))

    async def bulk_write(self, ops: list[Any], ordered: bool = True) -> None:  # noqa: ARG002
        for op in ops:
            filt = op._filter  # pymongo UpdateOne stores private fields
            update = op._doc
            self._apply(filt, update)

    def _matching(self, filt: dict[str, Any]):
        for doc in self._docs.values():
            if self._match(doc, filt):
                yield doc

    def _match(self, doc: dict[str, Any], filt: dict[str, Any]) -> bool:
        for key, expected in filt.items():
            value = self._lookup(doc, key)
            if isinstance(expected, dict) and "$exists" in expected:
                if expected["$exists"] != (value is not None):
                    return False
            else:
                if value != expected:
                    return False
        return True

    @staticmethod
    def _lookup(doc: dict[str, Any], dotted: str) -> Any:
        cur: Any = doc
        for part in dotted.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
            if cur is None:
                return None
        return cur

    def _apply(self, filt: dict[str, Any], update: dict[str, Any]) -> None:
        doc_id = filt["_id"]
        doc = self._docs.get(doc_id)
        if doc is None:
            return
        for key, value in update.get("$set", {}).items():
            self._set_dotted(doc, key, value)
        for key in update.get("$unset", {}):
            self._unset_dotted(doc, key)

    @staticmethod
    def _set_dotted(doc: dict[str, Any], dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        cur = doc
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = value

    @staticmethod
    def _unset_dotted(doc: dict[str, Any], dotted: str) -> None:
        parts = dotted.split(".")
        cur = doc
        for part in parts[:-1]:
            cur = cur.get(part)
            if not isinstance(cur, dict):
                return
        cur.pop(parts[-1], None)


def _async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


def test_legacy_doc_gets_composite_symbol():
    coll = _FakeCollection(
        [{"_id": "a", "config_snapshot": {"symbol": "BTCUSDT", "exchange": "BINANCE"}}]
    )
    result = _async(_migrate(coll, batch_size=10, dry_run=False))
    assert result.updated == 1
    assert result.skipped == 0
    doc = coll._docs["a"]
    assert doc["config_snapshot"]["symbol"] == "BTCUSDT:BINANCE"
    assert "exchange" not in doc["config_snapshot"]


def test_already_composite_skipped():
    coll = _FakeCollection(
        [{"_id": "a", "config_snapshot": {"symbol": "BTCUSDT:BINANCE"}}]
    )
    result = _async(_migrate(coll, batch_size=10, dry_run=False))
    assert result.updated == 0
    assert result.skipped == 1
    assert coll._docs["a"]["config_snapshot"]["symbol"] == "BTCUSDT:BINANCE"


def test_already_composite_but_stale_exchange_field_cleared():
    coll = _FakeCollection(
        [
            {
                "_id": "a",
                "config_snapshot": {
                    "symbol": "BTCUSDT:BINANCE",
                    "exchange": "BINANCE",  # leftover from partial migration
                },
            }
        ]
    )
    result = _async(_migrate(coll, batch_size=10, dry_run=False))
    assert result.updated == 1
    assert result.skipped == 0
    assert "exchange" not in coll._docs["a"]["config_snapshot"]


def test_uppercases_lowercase_inputs():
    coll = _FakeCollection(
        [{"_id": "a", "config_snapshot": {"symbol": "btcusdt", "exchange": "binance"}}]
    )
    _async(_migrate(coll, batch_size=10, dry_run=False))
    assert coll._docs["a"]["config_snapshot"]["symbol"] == "BTCUSDT:BINANCE"


def test_missing_symbol_or_exchange_skipped_with_warning(capsys):
    coll = _FakeCollection(
        [{"_id": "a", "config_snapshot": {"symbol": "BTCUSDT"}}]
    )
    result = _async(_migrate(coll, batch_size=10, dry_run=False))
    assert result.updated == 0
    assert result.skipped == 1
    assert "missing config_snapshot symbol or exchange" in capsys.readouterr().err


def test_non_dict_config_snapshot_skipped():
    coll = _FakeCollection([{"_id": "a", "config_snapshot": None}])
    result = _async(_migrate(coll, batch_size=10, dry_run=False))
    assert result.skipped == 1
    assert result.updated == 0


def test_dry_run_does_not_persist():
    coll = _FakeCollection(
        [{"_id": "a", "config_snapshot": {"symbol": "BTCUSDT", "exchange": "BINANCE"}}]
    )
    result = _async(_migrate(coll, batch_size=10, dry_run=True))
    # Counter still increments to give an accurate "would-update" preview,
    # but the document is left untouched.
    assert result.updated == 1
    assert coll._docs["a"]["config_snapshot"]["symbol"] == "BTCUSDT"
    assert coll._docs["a"]["config_snapshot"]["exchange"] == "BINANCE"


def test_residual_count_reports_legacy_exchange_field():
    coll = _FakeCollection(
        [
            {"_id": "a", "config_snapshot": {"symbol": "X:Y"}},
            {"_id": "b", "config_snapshot": {"symbol": "X:Y", "exchange": "Y"}},
        ]
    )
    assert _async(_residual_count(coll)) == 1


def test_batch_boundary_flushes_remainder():
    docs = [
        {"_id": f"d{i}", "config_snapshot": {"symbol": "BTCUSDT", "exchange": "BINANCE"}}
        for i in range(5)
    ]
    coll = _FakeCollection(docs)
    result = _async(_migrate(coll, batch_size=2, dry_run=False))
    assert result.updated == 5
    for d in docs:
        assert coll._docs[d["_id"]]["config_snapshot"]["symbol"] == "BTCUSDT:BINANCE"
