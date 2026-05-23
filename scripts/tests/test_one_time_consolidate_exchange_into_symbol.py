"""Unit tests for the exchange→composite-symbol migration script."""

from unittest.mock import AsyncMock

import pytest
from pymongo import UpdateOne
from scripts.one_time_consolidate_exchange_into_symbol import (
    COMPOSITE_RE,
    SPECS,
    _build_composite,
    _migrate_documents,
)


class TestCompositeRegex:
    def test_accepts_canonical(self) -> None:
        assert COMPOSITE_RE.match("BTCUSDT:BINANCE")

    def test_accepts_alphanumeric(self) -> None:
        assert COMPOSITE_RE.match("ETH-USD:COINBASE")
        assert COMPOSITE_RE.match("BTC_USDT:OKX")
        assert COMPOSITE_RE.match("BTC.USDT:BINANCE")

    def test_rejects_bare_code(self) -> None:
        assert not COMPOSITE_RE.match("BTCUSDT")

    def test_rejects_dash_separator(self) -> None:
        assert not COMPOSITE_RE.match("BTCUSDT-BINANCE")

    def test_rejects_lowercase(self) -> None:
        assert not COMPOSITE_RE.match("btcusdt:binance")

    def test_rejects_empty(self) -> None:
        assert not COMPOSITE_RE.match("")
        assert not COMPOSITE_RE.match(":")
        assert not COMPOSITE_RE.match("BTC:")
        assert not COMPOSITE_RE.match(":BINANCE")


class TestBuildComposite:
    def test_uppercases_both_segments(self) -> None:
        assert _build_composite("btcusdt", "binance") == "BTCUSDT:BINANCE"

    def test_preserves_uppercase(self) -> None:
        assert _build_composite("BTCUSDT", "BINANCE") == "BTCUSDT:BINANCE"

    def test_mixed_case(self) -> None:
        assert _build_composite("EthUsdt", "Coinbase") == "ETHUSDT:COINBASE"


class _FakeCursor:
    """Async context-managerless cursor stub yielding given docs."""

    def __init__(self, docs: list[dict]) -> None:
        self._docs = list(docs)

    def __aiter__(self):  # type: ignore[no-untyped-def]
        async def gen():
            for d in self._docs:
                yield d

        return gen()

    async def close(self) -> None:
        return None


def _make_mock_collection(docs: list[dict], total: int | None = None) -> AsyncMock:
    """Build an AsyncMock collection that returns the given docs from .find()."""
    coll = AsyncMock()
    coll.count_documents = AsyncMock(return_value=total if total is not None else len(docs))
    coll.find = lambda *_a, **_kw: _FakeCursor(docs)  # not a coroutine
    coll.bulk_write = AsyncMock()
    return coll


@pytest.mark.asyncio
async def test_migrate_is_no_op_on_already_composite() -> None:
    """If all docs already match composite shape and no legacy exchange field, skip all."""
    spec = SPECS["bars"]
    docs = [
        {"_id": "1", "symbol": "BTCUSDT:BINANCE", "interval": "1h"},
        {"_id": "2", "symbol": "ETHUSDT:BINANCE", "interval": "1h"},
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=10, dry_run=False
    )

    assert total == 2
    assert skipped == 2
    assert updated == 0
    coll.bulk_write.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_converts_legacy_shape() -> None:
    """Legacy doc with separate (symbol=code, exchange=ex) → queued UpdateOne with composite."""
    spec = SPECS["bars"]
    docs = [
        {"_id": "1", "symbol": "BTCUSDT", "exchange": "BINANCE", "interval": "1h"},
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=10, dry_run=False
    )

    assert total == 1
    assert skipped == 0
    assert updated == 1
    coll.bulk_write.assert_awaited_once()

    # Inspect the UpdateOne queued
    (batch_arg,), _kwargs = coll.bulk_write.await_args
    assert len(batch_arg) == 1
    assert isinstance(batch_arg[0], UpdateOne)


@pytest.mark.asyncio
async def test_migrate_unsets_residual_exchange_when_already_composite() -> None:
    """Doc already composite but still carries legacy `exchange` field → emit $unset only."""
    spec = SPECS["bars"]
    docs = [
        {"_id": "1", "symbol": "BTCUSDT:BINANCE", "exchange": "BINANCE", "interval": "1h"},
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=10, dry_run=False
    )

    assert total == 1
    assert skipped == 0
    assert updated == 1
    coll.bulk_write.assert_awaited_once()


@pytest.mark.asyncio
async def test_migrate_skips_incomplete_doc() -> None:
    """Doc missing both composite and (code, exchange) pair → skipped with WARN log."""
    spec = SPECS["bars"]
    docs = [
        {"_id": "1", "symbol": "BTCUSDT", "interval": "1h"},  # no exchange
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=10, dry_run=False
    )

    assert total == 1
    assert skipped == 1
    assert updated == 0
    coll.bulk_write.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_dry_run_does_not_write() -> None:
    """dry_run=True must NOT call bulk_write even when changes are queued."""
    spec = SPECS["bars"]
    docs = [
        {"_id": "1", "symbol": "BTCUSDT", "exchange": "BINANCE", "interval": "1h"},
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=10, dry_run=True
    )

    assert total == 1
    assert updated == 1  # would have updated
    coll.bulk_write.assert_not_called()


@pytest.mark.asyncio
async def test_migrate_batches_at_size_limit() -> None:
    """Once queue reaches batch_size, bulk_write is flushed; remaining docs in next batch."""
    spec = SPECS["bars"]
    docs = [
        {"_id": str(i), "symbol": "BTCUSDT", "exchange": "BINANCE", "interval": "1h"}
        for i in range(7)
    ]
    coll = _make_mock_collection(docs)

    total, skipped, updated = await _migrate_documents(
        coll, spec, batch_size=3, dry_run=False
    )

    assert total == 7
    assert updated == 7
    # 7 docs, batch=3 → flushes at 3, 6 (mid-loop), and final flush of 1 remaining
    assert coll.bulk_write.await_count == 3
