"""Tests for MongoDB datetime normalization in domain entities."""

from datetime import UTC, datetime

from pocketquant.core.domain.bar.entities import Bar
from pocketquant.core.domain.shared.enums import Interval
from pocketquant.core.domain.sync_status.entities import SyncStatus


def test_bar_from_mongo_coerces_naive_datetimes_to_utc():
    bar = Bar.from_mongo(
        {
            "_id": "019d75b6-6ac7-774e-a5cf-dcd5e8f0749e",
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "interval": "1d",
            "datetime": datetime(2026, 4, 10, 0, 0, 0),
            "created_at": datetime(2026, 4, 10, 0, 1, 0),
        }
    )

    assert bar.interval == Interval.DAY_1
    assert bar.datetime == datetime(2026, 4, 10, 0, 0, 0, tzinfo=UTC)
    assert bar.created_at == datetime(2026, 4, 10, 0, 1, 0, tzinfo=UTC)


def test_sync_status_from_mongo_coerces_naive_datetimes_to_utc():
    status = SyncStatus.from_mongo(
        {
            "_id": "019d75b6-6ac8-7220-90a6-49043c6be99d",
            "symbol": "BTCUSDT",
            "exchange": "BINANCE",
            "interval": "1d",
            "status": "completed",
            "last_sync_at": datetime(2026, 4, 10, 0, 2, 0),
            "last_bar_at": datetime(2026, 4, 10, 0, 0, 0),
        }
    )

    assert status.last_sync_at == datetime(2026, 4, 10, 0, 2, 0, tzinfo=UTC)
    assert status.last_bar_at == datetime(2026, 4, 10, 0, 0, 0, tzinfo=UTC)
