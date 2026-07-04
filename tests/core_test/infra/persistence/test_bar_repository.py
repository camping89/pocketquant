"""Unit tests for BarRepository — upsert diff-aware cache, insert_many loop, delete_many_by_range.

Covers:
- Cache hit (same OHLCV) → zero DB calls.
- Cache miss + new doc (find_one None) → $setOnInsert created_at, $set OHLCV+updated_at+source.
- Cache miss + existing doc with same OHLCV → no write, cache warmed.
- Cache miss + existing doc with different OHLCV → $set OHLCV+updated_at+source, no $setOnInsert.
- upsert_bar/insert_many without source kwarg raise TypeError.
- insert_many calls upsert_bar once per record, forwards source, is a no-op on empty list,
  and continues past individual upsert failures.
- delete_many_by_range builds correct $in/$gte/$lt filter, uppercases symbol, is a no-op on
  empty interval list, and returns the motor deleted_count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import (
    _BAR_VALUE_CACHE,
    BarRepository,
    _cache_key,
    _cache_value,
)

_START = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
_END = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

_CANONICAL_TFS = [
    Interval.MINUTE_1,
    Interval.MINUTE_5,
    Interval.MINUTE_15,
    Interval.HOUR_1,
    Interval.HOUR_4,
    Interval.DAY_1,
]


@pytest.fixture(autouse=True)
def _reset_cache():
    _BAR_VALUE_CACHE.clear()
    yield
    _BAR_VALUE_CACHE.clear()


def _make_bar(close: float = 1.5) -> Bar:
    return Bar(
        symbol="BTCUSDT",
        interval=Interval.MINUTE_1,
        datetime=datetime(2026, 1, 1, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=close,
        volume=100.0,
        tick_count=1,
    )


def _bars(n: int) -> list[Bar]:
    return [
        Bar(
            symbol="BTCUSDT",
            interval=Interval.MINUTE_1,
            datetime=datetime(2026, 1, 1, 0, i, tzinfo=UTC),
            open=1.0 + i,
            high=2.0 + i,
            low=0.5 + i,
            close=1.5 + i,
            volume=100.0,
            tick_count=1,
        )
        for i in range(n)
    ]


def _make_repo(existing_doc=None) -> tuple[BarRepository, MagicMock]:
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=existing_doc)
    collection.update_one = AsyncMock()

    db = MagicMock()
    db.get_collection.return_value = collection
    return BarRepository(db), collection


def _make_insert_repo() -> BarRepository:
    db = MagicMock()
    db.get_collection.return_value = MagicMock()
    return BarRepository(db)


def _make_delete_repo(deleted_count: int = 42) -> tuple[BarRepository, MagicMock]:
    """Return (repo, mock_collection) with delete_many pre-wired."""
    mock_result = MagicMock()
    mock_result.deleted_count = deleted_count

    mock_collection = MagicMock()
    mock_collection.delete_many = AsyncMock(return_value=mock_result)

    mock_db = MagicMock()
    mock_db.get_collection.return_value = mock_collection

    repo = BarRepository(mock_db)
    return repo, mock_collection


class TestCacheHit:
    @pytest.mark.asyncio
    async def test_same_value_hits_cache_no_db_call(self) -> None:
        bar = _make_bar()
        repo, collection = _make_repo()
        _BAR_VALUE_CACHE[_cache_key(bar)] = _cache_value(bar)

        await repo.upsert_bar(bar, source="rest_sync_1m")

        collection.find_one.assert_not_called()
        collection.update_one.assert_not_called()


class TestCacheMissNewDoc:
    @pytest.mark.asyncio
    async def test_uses_set_on_insert_created_at_and_set_audit_fields(self) -> None:
        bar = _make_bar()
        repo, collection = _make_repo(existing_doc=None)

        await repo.upsert_bar(bar, source="rest_sync_1m")

        args, kwargs = collection.update_one.call_args
        update_ops = args[1]
        assert "$setOnInsert" in update_ops
        assert "created_at" in update_ops["$setOnInsert"]
        assert "_id" in update_ops["$setOnInsert"]
        assert update_ops["$set"]["source"] == "rest_sync_1m"
        assert isinstance(update_ops["$set"]["updated_at"], datetime)
        assert kwargs.get("upsert") is True

    @pytest.mark.asyncio
    async def test_populates_cache_after_insert(self) -> None:
        bar = _make_bar()
        repo, _ = _make_repo(existing_doc=None)
        await repo.upsert_bar(bar, source="rest_sync_1m")
        assert _BAR_VALUE_CACHE.get(_cache_key(bar)) == _cache_value(bar)


class TestCacheMissExistingSameValue:
    @pytest.mark.asyncio
    async def test_no_write_when_db_already_has_same_value(self) -> None:
        bar = _make_bar()
        existing = {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        repo, collection = _make_repo(existing_doc=existing)

        await repo.upsert_bar(bar, source="cascade")

        collection.find_one.assert_called_once()
        collection.update_one.assert_not_called()
        assert _BAR_VALUE_CACHE.get(_cache_key(bar)) == _cache_value(bar)


class TestCacheMissExistingDiffValue:
    @pytest.mark.asyncio
    async def test_writes_only_set_no_set_on_insert(self) -> None:
        new_bar = _make_bar(close=1.7)
        # Existing has a different close — diff-aware update should fire.
        existing = {
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100.0,
        }
        repo, collection = _make_repo(existing_doc=existing)

        await repo.upsert_bar(new_bar, source="cascade")

        args, kwargs = collection.update_one.call_args
        update_ops = args[1]
        assert "$setOnInsert" not in update_ops
        set_payload = update_ops["$set"]
        assert set_payload["close"] == 1.7
        assert set_payload["source"] == "cascade"
        assert "updated_at" in set_payload
        # upsert=False (or absent) since the doc already exists.
        assert not kwargs.get("upsert", False)


class TestRequiredKwarg:
    @pytest.mark.asyncio
    async def test_missing_source_raises_type_error(self) -> None:
        bar = _make_bar()
        repo, _ = _make_repo(existing_doc=None)
        with pytest.raises(TypeError):
            await repo.upsert_bar(bar)  # type: ignore[call-arg]


class TestInsertManyLoop:
    @pytest.mark.asyncio
    async def test_calls_upsert_per_bar_with_same_source(self) -> None:
        repo = _make_insert_repo()
        repo.upsert_bar = AsyncMock()
        records = _bars(3)

        count = await repo.insert_many(records, source="rest_sync_1m")

        assert count == 3
        assert repo.upsert_bar.await_count == 3
        for call in repo.upsert_bar.await_args_list:
            assert call.kwargs.get("source") == "rest_sync_1m"

    @pytest.mark.asyncio
    async def test_empty_list_returns_zero(self) -> None:
        repo = _make_insert_repo()
        repo.upsert_bar = AsyncMock()
        count = await repo.insert_many([], source="rest_sync_1m")
        assert count == 0
        repo.upsert_bar.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_source_raises_type_error(self) -> None:
        repo = _make_insert_repo()
        with pytest.raises(TypeError):
            await repo.insert_many(_bars(1))  # type: ignore[call-arg]

    @pytest.mark.asyncio
    async def test_continues_on_individual_failure(self) -> None:
        repo = _make_insert_repo()
        # 2nd bar raises; loop must not abort.
        call_log: list[Bar] = []

        async def flaky_upsert(bar: Bar, *, source: str) -> None:  # noqa: ARG001
            call_log.append(bar)
            if len(call_log) == 2:
                raise RuntimeError("boom")

        repo.upsert_bar = flaky_upsert  # type: ignore[assignment]
        records = _bars(3)

        count = await repo.insert_many(records, source="rest_sync_1m")
        assert len(call_log) == 3  # all attempted
        assert count == 2  # 2 succeeded


class TestDeleteManyByRangeFilter:
    @pytest.mark.asyncio
    async def test_interval_in_filter_contains_all_canonical_tfs(self) -> None:
        repo, mock_col = _make_delete_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        interval_filter = call_filter["interval"]["$in"]
        expected_values = {tf.value for tf in _CANONICAL_TFS}
        assert set(interval_filter) == expected_values

    @pytest.mark.asyncio
    async def test_date_range_uses_gte_lt(self) -> None:
        repo, mock_col = _make_delete_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        dt_filter = call_filter["datetime"]
        assert dt_filter["$gte"] == _START
        assert dt_filter["$lt"] == _END

    @pytest.mark.asyncio
    async def test_symbol_and_exchange_uppercased(self) -> None:
        repo, mock_col = _make_delete_repo()
        await repo.delete_many_by_range("btcusdt:binance", [Interval.MINUTE_1], _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        assert call_filter["symbol"] == "BTCUSDT:BINANCE"

    @pytest.mark.asyncio
    async def test_single_interval_produces_one_element_in_list(self) -> None:
        repo, mock_col = _make_delete_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", [Interval.HOUR_1], _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        assert call_filter["interval"]["$in"] == [Interval.HOUR_1.value]

    @pytest.mark.asyncio
    async def test_returns_deleted_count_from_motor_result(self) -> None:
        repo, _ = _make_delete_repo(deleted_count=12345)
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)
        assert result == 12345

    @pytest.mark.asyncio
    async def test_zero_deleted_returns_zero(self) -> None:
        repo, _ = _make_delete_repo(deleted_count=0)
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)
        assert result == 0


class TestDeleteManyByRangeEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_intervals_returns_zero_without_db_call(self) -> None:
        """Empty intervals list: no-op — must not call delete_many."""
        repo, mock_col = _make_delete_repo()
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", [], _START, _END)

        assert result == 0
        mock_col.delete_many.assert_not_called()
