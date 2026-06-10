"""Unit tests for BarRepository.delete_many_by_range — mock MongoDB collection.

Covers:
- Correct $in filter for multiple intervals
- Correct $gte/$lt date range in delete filter
- Empty interval list is a no-op (returns 0, no DB call)
- Single interval produces $in list with one element
- Composite symbol is uppercased in the filter
- Returns actual deleted_count from motor result
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.infra.persistence.repositories.bar_repository import BarRepository

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


def _make_repo(deleted_count: int = 42) -> tuple[BarRepository, MagicMock]:
    """Return (repo, mock_collection) with delete_many pre-wired."""
    mock_result = MagicMock()
    mock_result.deleted_count = deleted_count

    mock_collection = MagicMock()
    mock_collection.delete_many = AsyncMock(return_value=mock_result)

    mock_db = MagicMock()
    mock_db.get_collection.return_value = mock_collection

    repo = BarRepository(mock_db)
    return repo, mock_collection


class TestDeleteManyByRangeFilter:
    @pytest.mark.asyncio
    async def test_interval_in_filter_contains_all_canonical_tfs(self) -> None:
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        interval_filter = call_filter["interval"]["$in"]
        expected_values = {tf.value for tf in _CANONICAL_TFS}
        assert set(interval_filter) == expected_values

    @pytest.mark.asyncio
    async def test_date_range_uses_gte_lt(self) -> None:
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        dt_filter = call_filter["datetime"]
        assert dt_filter["$gte"] == _START
        assert dt_filter["$lt"] == _END

    @pytest.mark.asyncio
    async def test_symbol_and_exchange_uppercased(self) -> None:
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("btcusdt:binance", [Interval.MINUTE_1], _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        assert call_filter["symbol"] == "BTCUSDT:BINANCE"

    @pytest.mark.asyncio
    async def test_single_interval_produces_one_element_in_list(self) -> None:
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", [Interval.HOUR_1], _START, _END)

        call_filter = mock_col.delete_many.call_args.args[0]
        assert call_filter["interval"]["$in"] == [Interval.HOUR_1.value]

    @pytest.mark.asyncio
    async def test_returns_deleted_count_from_motor_result(self) -> None:
        repo, _ = _make_repo(deleted_count=12345)
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)
        assert result == 12345

    @pytest.mark.asyncio
    async def test_zero_deleted_returns_zero(self) -> None:
        repo, _ = _make_repo(deleted_count=0)
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)
        assert result == 0


class TestDeleteManyByRangeEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_intervals_returns_zero_without_db_call(self) -> None:
        """Empty intervals list: no-op — must not call delete_many."""
        repo, mock_col = _make_repo()
        result = await repo.delete_many_by_range("BTCUSDT:BINANCE", [], _START, _END)

        assert result == 0
        mock_col.delete_many.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_many_called_exactly_once_per_call(self) -> None:
        """Single call to delete_many_by_range issues exactly one DB round-trip."""
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("BTCUSDT:BINANCE", _CANONICAL_TFS, _START, _END)

        assert mock_col.delete_many.await_count == 1

    @pytest.mark.asyncio
    async def test_interval_values_are_strings_not_enum_objects(self) -> None:
        """$in list must contain string values (e.g. '1m'), not Interval enum objects."""
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range(
            "BTCUSDT:BINANCE", [Interval.MINUTE_1, Interval.DAY_1], _START, _END
        )

        call_filter = mock_col.delete_many.call_args.args[0]
        for val in call_filter["interval"]["$in"]:
            assert isinstance(val, str), f"Expected str, got {type(val)}: {val!r}"

    @pytest.mark.asyncio
    async def test_narrow_time_window(self) -> None:
        """A 1-minute window does not alter the filter structure."""
        start = datetime(2026, 5, 8, 10, 0, 0, tzinfo=UTC)
        end = start + timedelta(minutes=1)
        repo, mock_col = _make_repo()
        await repo.delete_many_by_range("ETHUSDT:BINANCE", [Interval.MINUTE_1], start, end)

        call_filter = mock_col.delete_many.call_args.args[0]
        assert call_filter["datetime"]["$gte"] == start
        assert call_filter["datetime"]["$lt"] == end
        assert call_filter["symbol"] == "ETHUSDT:BINANCE"
