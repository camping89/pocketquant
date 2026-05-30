"""Unit tests for BarRepository.upsert_bar — diff-aware cache + source label.

Covers:
- Cache hit (same OHLCV) → zero DB calls.
- Cache miss + new doc (find_one returns None) → $setOnInsert created_at, $set OHLCV+updated_at+source.
- Cache miss + existing doc with same OHLCV → no write, cache warmed.
- Cache miss + existing doc with different OHLCV → $set OHLCV+updated_at+source, no $setOnInsert.
- upsert_bar without source kwarg raises TypeError.
- $set payload always carries the source string verbatim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.persistence.repositories.bar_repository import (
    _BAR_VALUE_CACHE,
    BarRepository,
    _cache_key,
    _cache_value,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    _BAR_VALUE_CACHE.clear()
    yield
    _BAR_VALUE_CACHE.clear()


def _make_bar(close: float = 1.5) -> Bar:
    return Bar(
        symbol="BTCUSDT",
        exchange="BINANCE",
        interval=Interval.MINUTE_1,
        datetime=datetime(2026, 1, 1, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=close,
        volume=100.0,
        tick_count=1,
    )


def _make_repo(existing_doc=None) -> tuple[BarRepository, MagicMock]:
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=existing_doc)
    collection.update_one = AsyncMock()

    db = MagicMock()
    db.get_collection.return_value = collection
    return BarRepository(db), collection


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
    async def test_uses_setOnInsert_created_at_and_set_audit_fields(self) -> None:
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
    async def test_writes_only_set_no_setOnInsert(self) -> None:
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
