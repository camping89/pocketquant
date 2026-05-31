"""Unit tests for Bar entity audit fields (updated_at, source).

Covers:
- to_mongo() does NOT serialize updated_at / source (repository is single writer).
- from_mongo() parses updated_at + source when present.
- from_mongo() handles legacy docs missing audit fields (both → None).
- to_dict() includes updated_at + source for API surface.
- SOURCE_* constants exist with expected string values.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pocketquant.core.domain.bar.entities import (
    SOURCE_BULK_SYNC,
    SOURCE_CASCADE,
    SOURCE_ONE_TIME_LEGACY,
    SOURCE_REST_BACKFILL,
    SOURCE_REST_REPAIR,
    SOURCE_REST_SYNC_1M,
    SOURCE_TRACKED_SYMBOL_BACKFILL,
    Bar,
)
from pocketquant.core.domain.shared.enums import Interval


def _build_bar(**overrides):
    base = dict(
        symbol="BTCUSDT",
        exchange="BINANCE",
        interval=Interval.MINUTE_1,
        datetime=datetime(2026, 1, 1, tzinfo=UTC),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
        tick_count=1,
    )
    base.update(overrides)
    return Bar(**base)


class TestToMongoAuditFields:
    def test_to_mongo_excludes_updated_at(self) -> None:
        bar = _build_bar(updated_at=datetime(2026, 2, 1, tzinfo=UTC))
        doc = bar.to_mongo()
        assert "updated_at" not in doc

    def test_to_mongo_excludes_source(self) -> None:
        bar = _build_bar(source="rest_sync_1m")
        doc = bar.to_mongo()
        assert "source" not in doc

    def test_to_mongo_still_includes_created_at(self) -> None:
        bar = _build_bar()
        doc = bar.to_mongo()
        assert "created_at" in doc


class TestFromMongoAuditFields:
    def test_parses_updated_at_when_present(self) -> None:
        doc = {
            "_id": "11111111-1111-1111-1111-111111111111",
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "interval": "1m",
            "datetime": datetime(2026, 1, 1, tzinfo=UTC),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100.0,
            "tick_count": 1,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
            "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
            "source": "rest_sync_1m",
        }
        bar = Bar.from_mongo(doc)
        assert bar.updated_at == datetime(2026, 2, 1, tzinfo=UTC)
        assert bar.source == "rest_sync_1m"

    def test_handles_legacy_doc_missing_audit_fields(self) -> None:
        doc = {
            "_id": "22222222-2222-2222-2222-222222222222",
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "interval": "1m",
            "datetime": datetime(2026, 1, 1, tzinfo=UTC),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100.0,
            "tick_count": 1,
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }
        bar = Bar.from_mongo(doc)
        assert bar.updated_at is None
        assert bar.source is None


class TestToDictAuditFields:
    def test_includes_audit_fields(self) -> None:
        ts = datetime(2026, 2, 1, tzinfo=UTC)
        bar = _build_bar(updated_at=ts, source="cascade")
        d = bar.to_dict()
        assert d["updated_at"] == ts.isoformat()
        assert d["source"] == "cascade"

    def test_serializes_none_audit_fields(self) -> None:
        bar = _build_bar()
        d = bar.to_dict()
        assert d["updated_at"] is None
        assert d["source"] is None


class TestSourceConstants:
    def test_constants_have_expected_string_values(self) -> None:
        assert SOURCE_REST_SYNC_1M == "rest_sync_1m"
        assert SOURCE_REST_BACKFILL == "rest_backfill"
        assert SOURCE_REST_REPAIR == "rest_repair"
        assert SOURCE_CASCADE == "cascade"
        assert SOURCE_TRACKED_SYMBOL_BACKFILL == "tracked_symbol_backfill"
        assert SOURCE_BULK_SYNC == "bulk_sync_api"
        assert SOURCE_ONE_TIME_LEGACY == "one_time_legacy"
